import os
import string
import secrets
import datetime
import calendar
import re
import random
import requests
import json
import logging
import difflib
import threading
import uuid
import time
import markdown as md_lib
import bleach
from pywebpush import webpush, WebPushException
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate 
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename 
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from PIL import Image, ImageOps, UnidentifiedImageError

# NEW: 导入通义千问 SDK
import dashscope
from http import HTTPStatus

# --- 1. 配置区域 ---
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'recipes.db')
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app_env = os.environ.get('APP_ENV', 'development').lower()
secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    if app_env == 'production':
        raise RuntimeError('生产环境必须设置 SECRET_KEY')
    secret_key = 'development-only-change-before-production'
    logging.warning('正在使用仅限开发环境的 SECRET_KEY')
app.config['SECRET_KEY'] = secret_key
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
app.config['ALLOW_REGISTRATION'] = os.environ.get('ALLOW_REGISTRATION', 'false').lower() == 'true'
app.config['RELATIONSHIP_START_DATE'] = os.environ.get('RELATIONSHIP_START_DATE', '2024-05-01')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_SECURE'] = app.config['SESSION_COOKIE_SECURE']
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
SYSTEM_RECIPE_USERNAME = 'GitHub how to cook'

# --- NEW: 通义千问 API Key 配置 ---
# 请在这里填入您的阿里云 DashScope API Key
app.config['DASHSCOPE_API_KEY'] = os.environ.get('DASHSCOPE_API_KEY', '')

# --- Web Push VAPID 配置 ---
# 注意: py_vapid 的 Vapid.from_string() 会把输入当 base64 解码，
# 不能包含 PEM 头尾标记（-----BEGIN/END...-----），否则解码失败导致推送静默失败。
# 所以这里直接用纯 base64（DER 编码）格式。
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_CLAIMS = {"sub": os.environ.get('VAPID_SUBJECT', 'mailto:admin@example.com')}

# --- NEW: 关键修复！增加 SQLite 等待时间与连接池容错 ---
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 30},
    'pool_recycle': 280,
    'pool_pre_ping': True
}

db = SQLAlchemy(app)
migrate = Migrate(app, db) 
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login' 
login_manager.login_message = '您需要先登录才能访问此页面。'
login_manager.login_message_category = 'error'

# 本地题库 (AI 失败时的兜底)
QUESTIONS_POOL = [
    "最近一周，对方做过哪件小事让你觉得被照顾到了？",
    "这个周末只安排一件放松的事，你最想和对方做什么？",
    "最近有没有一件你希望对方主动帮忙的小事？",
    "我们最近哪顿饭让你最想再吃一次？",
    "最近哪个普通瞬间让你觉得两个人一起生活真好？",
    "这周有什么事你想让对方多听一会儿，先不急着给建议？",
    "最近我们的相处节奏里，有什么值得继续保持？",
    "下次只有半天空闲，你想和对方怎么度过？",
    "最近你最想从对方那里得到怎样的安慰或支持？",
    "这周你观察到对方有什么小变化？",
    "最近有什么小期待，说出来会更容易实现？",
    "如果给这周留下一个画面，你会选哪个瞬间？",
    "最近家里哪件小事调整一下，会让我们都更舒服？",
    "最近有什么好吃的，值得我们一起去尝试？",
    "今天你最希望对方理解你的哪一种感受？",
]

QUESTION_THEME_KEYWORDS = {
    'work': ('工作', '加班', '下班', '项目', '方案', '盯盘', '策略', '客户', '会议', '疲惫', '很累'),
    'support': ('安慰', '支持', '吐槽', '拥抱', '抱抱', '情绪', '冷静', '复盘', '倾听', '多听', '理解', '沟通', '陪伴', '照顾', '帮忙', '回应', '被重视'),
    'distance': ('异地', '见面', '视频', '语音', '联络', '距离'),
    'home': ('家里', '家务', '住处', '房间', '收纳', '洗衣', '生活细节', '小窝'),
    'future': ('结婚', '领证', '婚礼', '未来', '以后', '住哪里', '小目标'),
    'food': ('吃', '饭', '餐', '菜', '美食', '餐厅'),
    'leisure': ('周末', '空闲', '放松', '电影', '游戏', '散步', '旅行'),
    'memory': ('回忆', '记得', '第一次', '瞬间', '画面'),
    'growth': ('变化', '进步', '成长', '习惯', '保持'),
}

QUESTION_THEME_LABELS = {
    'work': '工作与压力', 'support': '情绪安抚与沟通', 'distance': '异地与联络',
    'home': '居家生活', 'future': '未来计划', 'food': '饮食', 'leisure': '休闲活动',
    'memory': '共同回忆', 'growth': '变化与成长',
}

# 这些活动来自个人职业或技能，除非双方都明确共享，否则会让题目只适合一人回答。
QUESTION_ROLE_SPECIFIC_TERMS = ('盯盘', '自动化策略', '跑方案', '赶方案', '写方案', '开庭', '写代码', '调接口', '做交易')

QUESTION_FEEDBACK_REASONS = {
    'too_abstract': '太空泛', 'too_complex': '太绕了', 'repetitive': '重复了',
    'not_for_us': '不适合我们', 'too_sensitive': '太敏感', 'not_today': '今天不想聊这个'
}

LOGIN_FAILURES = {}
LOGIN_FAILURE_LOCK = threading.Lock()


def utcnow():
    """Return naive UTC for SQLite while avoiding datetime.utcnow deprecation."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

def _extract_json(text):
    """Extract a JSON object even when a model wraps it in a markdown fence."""
    text = (text or '').strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.I)
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except (TypeError, ValueError):
        return None


def _question_theme(question):
    """Return the strongest coarse theme so rephrasing cannot bypass diversity checks."""
    text = re.sub(r'\s+', '', question or '')
    scored = []
    for order, (theme, keywords) in enumerate(QUESTION_THEME_KEYWORDS.items()):
        score = sum(1 for keyword in keywords if keyword in text)
        if score:
            scored.append((score, -order, theme))
    return max(scored)[2] if scored else None


def _question_themes(question):
    text = re.sub(r'\s+', '', question or '')
    return {
        theme for theme, keywords in QUESTION_THEME_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    }


def _question_repeats_recent_theme(question, recent_questions):
    """Cool down a theme used very recently or repeatedly in the recent window."""
    themes = _question_themes(question)
    if not themes:
        return False
    recent_theme_sets = [_question_themes(old) for old in recent_questions[:8]]
    return any(
        any(theme in recent for recent in recent_theme_sets[:3])
        or sum(theme in recent for recent in recent_theme_sets) >= 2
        for theme in themes
    )


def _question_is_acceptable(question, recent_questions):
    question = re.sub(r'\s+', '', (question or '').strip())
    if not 15 <= len(question) <= 45 or not question.endswith(('？', '?')):
        return False
    banned = ('回到过去', '中了彩票', '中了一千万', '世界末日', '拥有超能力', '童年的影子', '评价现在的你')
    if any(term in question for term in banned):
        return False
    # 同一道题会原样展示给两个人，单数第一人称会让“我”指向不明。
    if '我' in question.replace('我们', '') or any(term in question for term in QUESTION_ROLE_SPECIFIC_TERMS):
        return False
    # 连续的二选一题既容易套路化，也常把双方锁进不对等角色。
    if '还是' in question:
        return False
    if question.count('？') + question.count('?') > 1 or question.count('，') > 3:
        return False
    for old in recent_questions:
        ratio = difflib.SequenceMatcher(None, question, re.sub(r'\s+', '', old)).ratio()
        if ratio >= 0.64:
            return False
    if _question_repeats_recent_theme(question, recent_questions):
        return False
    return True


def _compact_question_history(limit=10):
    questions = DailyQuestion.query.order_by(DailyQuestion.id.desc()).limit(limit).all()
    compact = []
    for question in questions:
        answer_count = DailyAnswer.query.filter_by(question_id=question.id).count()
        like_count = QuestionLike.query.filter_by(question_id=question.id).count()
        feedback = QuestionFeedback.query.filter_by(question_id=question.id).all()
        codes = [item.reason or item.feedback_type for item in feedback]
        if answer_count >= 2:
            codes.append('both_answered')
        if like_count:
            codes.append('liked')
        compact.append({'q': question.content, 'f': sorted(set(codes))})
    return compact


def generate_question_from_ai():
    """Generate a few compact candidates in one request and filter locally."""
    history = _compact_question_history(10)
    recent_questions = [item['q'] for item in history]
    profile = CoupleAIProfile.query.first()
    profile_summary = profile.summary[:1200] if profile and profile.summary else '暂无档案，从真实、具体的近期生活小事切入。'
    recent_themes = [
        '、'.join(QUESTION_THEME_LABELS[theme] for theme in QUESTION_THEME_KEYWORDS if theme in _question_themes(item['q'])) or '其他'
        for item in history
    ]
    api_key = app.config.get('DASHSCOPE_API_KEY')
    if not api_key:
        return None, {'reason': 'api_key_missing'}

    prompt_text = f"""你在为一对长期相处的情侣挑选一道“双方分别回答同一句话”的问题。
硬性要求：
1. 同一句问题原样展示给两个人，交换双方身份后仍然完全成立；统一用“对方、彼此、两个人”，不要使用单数第一人称“我、我的、让我、给我”。
2. 双方都能从自己的经历和感受出发回答；不要指定只属于一人的职业、爱好、日程或家庭角色。情侣档案只用于理解氛围，除非明确属于双方，否则不要把个人细节写进题目。
3. 15到45个汉字，一次只问一件事，优先开放式问法；不要用“还是”制造二选一。
4. 8个候选必须来自彼此不同的生活主题；避开下方主题序列最前面的3题所涉及的主题，以及10题内重复出现的主题。换一种说法但主题相同也算重复。
5. 真实具体、自然、轻深结合；避免作文题、强行煽情、复杂脑洞、陈旧假设和未经证实的共同经历。
情侣档案摘要：{profile_summary}
最近10题及反馈（紧凑JSON）：{json.dumps(history, ensure_ascii=False, separators=(',', ':'))}
最近题目的主题序列（从近到远）：{json.dumps(recent_themes, ensure_ascii=False)}
生成8个候选并逐题自检“双方是否都适合回答”。只返回JSON：
{{"candidates":[{{"question":"...？","theme":"主题名","both_answerable":true,"natural":1到10,"desire":1到10,"freshness":1到10}}]}}
"""
    data = {
        'model': 'qwen3.7-flash-2026-07-15',
        'messages': [{'role': 'user', 'content': prompt_text}],
        'temperature': 0.9,
        'top_p': 0.9
    }
    try:
        response = requests.post(
            'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json=data, timeout=120
        )
        response.raise_for_status()
        raw = response.json()['choices'][0]['message']['content']
        parsed = _extract_json(raw) or {}
        candidates = parsed.get('candidates', [])[:8]
        valid = []
        for item in candidates:
            question = str(item.get('question', '')).strip().replace('"', '')
            both_answerable = item.get('both_answerable') in (True, 1, 'true', 'True')
            if both_answerable and _question_is_acceptable(question, recent_questions):
                score = (
                    float(item.get('natural', 0))
                    + float(item.get('desire', 0))
                    + float(item.get('freshness', 0))
                )
                valid.append((score, question))
        if valid:
            valid.sort(reverse=True)
            return valid[0][1], {'candidate_count': len(candidates), 'valid_count': len(valid)}
        return None, {'reason': 'all_candidates_filtered', 'candidate_count': len(candidates)}
    except Exception as exc:
        app.logger.warning('AI question generation failed: %s', exc)
        return None, {'reason': type(exc).__name__}


def choose_fallback_question():
    recent = [q.content for q in DailyQuestion.query.order_by(DailyQuestion.id.desc()).limit(10).all()]
    choices = [q for q in QUESTIONS_POOL if _question_is_acceptable(q, recent)]
    safe_pool = [q for q in QUESTIONS_POOL if _question_is_acceptable(q, [])]
    return random.choice(choices or safe_pool)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- 2. 数据库模型 ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    recipes = db.relationship('Recipe', backref='author', lazy=True, cascade="all, delete-orphan")
    invite_code = db.Column(db.String(6), unique=True, nullable=True) 
    push_subscription = db.Column(db.Text, nullable=True)  # Web Push 订阅 JSON
    ai_context_consent = db.Column(db.Boolean, nullable=False, default=False)
    partner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) 
    partner = db.relationship('User', remote_side=[id], primaryjoin=partner_id == id, uselist=False, lazy=True)
    journal_entries = db.relationship('JournalEntry', backref='author', lazy=True)
    memories = db.relationship('Memory', backref='author', lazy=True)
    wishlist_items = db.relationship('WishlistItem', backref='author', lazy=True)
    
    # V5.0: 关联回答
    daily_answers = db.relationship('DailyAnswer', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# ... (Recipe, Ingredient, Seasoning, CookingLog, JournalEntry, Memory, WishlistItem 模型保持不变) ...
# 为节省篇幅，请确保您保留了 V4.6 中的所有这些模型类代码！
# 务必检查: WishlistItem 下面要添加 DailyQuestion 和 DailyAnswer

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    instructions = db.Column(db.Text, nullable=True)
    tips = db.Column(db.Text, nullable=True)
    image_file = db.Column(db.String(100), nullable=False, default='default.jpg')
    category = db.Column(db.String(50), nullable=True)
    difficulty = db.Column(db.Integer, nullable=True)
    calories = db.Column(db.Integer, nullable=True)
    source = db.Column(db.String(50), nullable=True)
    source_url = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('name', 'user_id', name='uq_recipe_name_user'),)
    ingredients = db.relationship('Ingredient', backref='recipe', lazy=True, cascade="all, delete-orphan")
    seasonings = db.relationship('Seasoning', backref='recipe', lazy=True, cascade="all, delete-orphan")
    logs = db.relationship('CookingLog', backref='recipe', lazy=True, cascade="all, delete-orphan")
class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50), nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)
class Seasoning(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50), nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)
class CookingLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_cooked = db.Column(db.DateTime, nullable=False, default=utcnow)
    time_taken = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)
class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_str = db.Column(db.String(10), nullable=False) 
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    last_request_id = db.Column(db.String(64), nullable=True)
    __table_args__ = (db.UniqueConstraint('date_str', 'author_id', name='_date_author_uc'),)
class Memory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    memory_date = db.Column(db.Date, nullable=True) 
    location = db.Column(db.String(100), nullable=True) 
    content = db.Column(db.Text, nullable=False)
    image_file = db.Column(db.String(100), nullable=False, default='default.jpg') 
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
class WishlistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(300), nullable=False)
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

# --- V5.4 NEW: 冰箱贴模型 (纪念日/倒数日) ---
class FridgeItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    target_date = db.Column(db.Date, nullable=False) # 目标日期
    item_type = db.Column(db.String(20), nullable=False) # 'anniversary' 或 'countdown'
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

# --- V5.0 NEW: 每日一问模型 ---
class DailyQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    date_str = db.Column(db.String(10), nullable=False)
    source = db.Column(db.String(20), default='随机题库')
    status = db.Column(db.String(20), nullable=False, default='open')
    close_reason = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)
    generation_meta = db.Column(db.Text, nullable=True)
    # Legacy duplicate questions are retained for history, but only the primary
    # record is eligible to be shown as that day's daily question.
    is_daily_primary = db.Column(db.Boolean, nullable=False, default=True)
    answers = db.relationship('DailyAnswer', backref='question', lazy=True, cascade="all, delete-orphan")
    __table_args__ = (
        db.Index('uq_daily_question_single_open', 'status', unique=True, sqlite_where=db.text("status = 'open'")),
        db.Index(
            'uq_daily_question_date_primary', 'date_str', unique=True,
            sqlite_where=db.text('is_daily_primary = 1')
        ),
    )

class DailyAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('daily_question.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('question_id', 'user_id', name='uq_daily_answer_question_user'),)

class QuestionLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('daily_question.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('question_id', 'user_id', name='uq_question_like_question_user'),)


class QuestionFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('daily_question.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    feedback_type = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    __table_args__ = (db.UniqueConstraint('question_id', 'user_id', name='uq_question_feedback_question_user'),)


class CoupleAIProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    summary = db.Column(db.Text, nullable=False, default='')
    updated_at = db.Column(db.DateTime, nullable=True)


class NotificationOutbox(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    body = db.Column(db.String(500), nullable=False)
    target_url = db.Column(db.String(300), nullable=False, default='/')
    status = db.Column(db.String(20), nullable=False, default='pending')
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)


class DailyCheckIn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_str = db.Column(db.String(10), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    mood = db.Column(db.String(20), nullable=False)
    energy = db.Column(db.String(20), nullable=False)
    need = db.Column(db.String(30), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (db.UniqueConstraint('date_str', 'user_id', name='uq_check_in_date_user'),)


class WeeklyReflection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week_start = db.Column(db.String(10), nullable=False, unique=True)
    summary = db.Column(db.Text, nullable=False, default='')
    gratitude_user_1 = db.Column(db.Text, nullable=True)
    gratitude_user_2 = db.Column(db.Text, nullable=True)
    confirmed_user_1 = db.Column(db.Boolean, nullable=False, default=False)
    confirmed_user_2 = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class CoupleTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week_start = db.Column(db.String(10), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='open')
    completed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

# --- 3. 辅助函数 ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def shared_user_ids():
    ids = [current_user.id]
    if current_user.partner_id:
        ids.append(current_user.partner_id)
    return ids


def can_access_author(author_id):
    return author_id in shared_user_ids()


def render_safe_markdown(value):
    rendered = md_lib.markdown(value or '', extensions=['sane_lists'])
    return bleach.clean(
        rendered,
        tags={'p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'code', 'pre', 'a'},
        attributes={'a': ['href', 'title']},
        protocols={'http', 'https'}, strip=True
    )


def save_uploaded_image(file_storage, prefix):
    if not file_storage or not file_storage.filename or not allowed_file(file_storage.filename):
        return None
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    filename = f'{prefix}_{secrets.token_hex(12)}.jpg'
    destination = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        image = Image.open(file_storage.stream)
        image.verify()
        file_storage.stream.seek(0)
        image = Image.open(file_storage.stream)
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((1800, 1800))
        image.save(destination, 'JPEG', quality=86, optimize=True)
        return filename
    except (UnidentifiedImageError, OSError, ValueError):
        if os.path.exists(destination):
            os.remove(destination)
        return None


def enqueue_push(user, title, body, target_url='/'):
    if user and user.push_subscription:
        item = NotificationOutbox(
            user_id=user.id, title=title, body=body, target_url=target_url
        )
        db.session.add(item)
        return item
    return None


def process_notification(notification_id):
    with app.app_context():
        item = db.session.get(NotificationOutbox, notification_id)
        if not item or item.status == 'sent':
            return
        user = db.session.get(User, item.user_id)
        if not user or not user.push_subscription or not VAPID_PRIVATE_KEY:
            item.status = 'failed'
            item.last_error = 'missing subscription or VAPID key'
            db.session.commit()
            return
        try:
            webpush(
                subscription_info=json.loads(user.push_subscription),
                data=json.dumps({'title': item.title, 'body': item.body, 'url': item.target_url}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS,
                timeout=8
            )
            item.status = 'sent'
            item.sent_at = utcnow()
            item.last_error = None
        except WebPushException as exc:
            item.attempts += 1
            item.status = 'failed' if item.attempts >= 3 else 'pending'
            item.last_error = str(exc)[:1000]
            if getattr(exc, 'response', None) is not None and exc.response.status_code in (404, 410):
                user.push_subscription = None
                item.status = 'failed'
        except Exception as exc:
            item.attempts += 1
            item.status = 'failed' if item.attempts >= 3 else 'pending'
            item.last_error = f'{type(exc).__name__}: {exc}'[:1000]
        db.session.commit()


def dispatch_notification(notification_id):
    threading.Thread(target=process_notification, args=(notification_id,), daemon=True).start()


@app.cli.command('process-notifications')
def process_notifications_command():
    pending = NotificationOutbox.query.filter_by(status='pending').order_by(NotificationOutbox.id).limit(50).all()
    for item in pending:
        process_notification(item.id)
    print(f'processed {len(pending)} notification(s)')


@app.route('/sw.js')
def service_worker():
    response = send_from_directory(app.static_folder, 'sw.js')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    response.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'"
    )
    if app_env == 'production' and app.config['SESSION_COOKIE_SECURE']:
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    if current_user.is_authenticated and request.endpoint != 'static':
        response.headers.setdefault('Cache-Control', 'private, no-store')
    return response

# --- 4. 路由 ---

# (login, logout, register 保持不变)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        client_key = request.remote_addr or 'unknown'
        now = time.time()
        with LOGIN_FAILURE_LOCK:
            recent = [stamp for stamp in LOGIN_FAILURES.get(client_key, []) if now - stamp < 600]
            LOGIN_FAILURES[client_key] = recent
        if len(recent) >= 5:
            flash('登录尝试过多，请十分钟后再试。', 'error')
            return redirect(url_for('login'))
        user = User.query.filter_by(username=request.form.get('username', '').strip()).first()
        if user is None or user.username == SYSTEM_RECIPE_USERNAME or not user.check_password(request.form['password']):
            with LOGIN_FAILURE_LOCK:
                LOGIN_FAILURES.setdefault(client_key, []).append(now)
            flash('无效的用户名或密码', 'error'); return redirect(url_for('login'))
        with LOGIN_FAILURE_LOCK:
            LOGIN_FAILURES.pop(client_key, None)
        login_user(user, remember=True); return redirect(url_for('index'))
    return render_template('login.html')
@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user(); return redirect(url_for('login'))
@app.route('/register', methods=['GET', 'POST'])
def register():
    if not app.config['ALLOW_REGISTRATION']:
        abort(404)
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('用户名已存在', 'error'); return redirect(url_for('register'))
        user = User(username=request.form['username']); user.set_password(request.form['password'])
        db.session.add(user); db.session.commit()
        flash('注册成功', 'success'); return redirect(url_for('login'))
    return render_template('register.html')

# (index 保持不变)
@app.route('/')
@login_required
def index():
    user_ids = shared_user_ids()
    activities = []
    recent_recipes = Recipe.query.filter(Recipe.user_id.in_(user_ids)).order_by(Recipe.id.desc()).limit(3).all()
    for r in recent_recipes: activities.append({'type': 'recipe', 'time': r.created_at, 'text': f"{r.author.username} 添加了新菜谱：{r.name}"})
    recent_memories = Memory.query.filter(Memory.author_id.in_(user_ids)).order_by(Memory.id.desc()).limit(3).all()
    for m in recent_memories: activities.append({'type': 'memory', 'time': m.created_at, 'text': f"{m.author.username} 添加了新回忆：{m.title}"})
    recent_wishes = WishlistItem.query.filter(WishlistItem.author_id.in_(user_ids)).order_by(WishlistItem.id.desc()).limit(3).all()
    for w in recent_wishes:
        action = "完成了愿望" if w.is_completed else "许下了愿望"
        activities.append({'type': 'wishlist', 'time': w.created_at, 'text': f"{w.author.username} {action}：{w.content}"})
    recent_journals = JournalEntry.query.filter(JournalEntry.author_id.in_(user_ids)).order_by(JournalEntry.id.desc()).limit(3).all()
    for j in recent_journals: activities.append({'type': 'journal', 'time': j.updated_at, 'text': f"{j.author.username} 写了一篇日记（{j.date_str}）"})
    activities.sort(key=lambda x: x['time'], reverse=True)
    
    # 获取冰箱贴
    fridge_items = FridgeItem.query.filter(FridgeItem.author_id.in_(user_ids)).order_by(FridgeItem.target_date.asc()).all()
    
    # 计算天数
    today_date = datetime.date.today()
    fridge_data = []
    for item in fridge_items:
        diff_days = (item.target_date - today_date).days
        fridge_data.append({
            'id': item.id,
            'title': item.title,
            'target_date': item.target_date.strftime('%Y-%m-%d'),
            'type': item.item_type,
            'author': db.session.get(User, item.author_id).username,
            'diff_days': abs(diff_days),
            'is_past': diff_days <= 0
        })
    
    active_question = get_current_daily_question(today_date)
    today_str = today_date.isoformat()
    weekday_names = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
    today_label = f"{today_date.year}年{today_date.month}月{today_date.day}日 · {weekday_names[today_date.weekday()]}"
    check_ins = DailyCheckIn.query.filter(
        DailyCheckIn.date_str == today_str, DailyCheckIn.user_id.in_(user_ids)
    ).all()
    check_in_map = {item.user_id: item for item in check_ins}

    on_this_day = Memory.query.filter(
        Memory.author_id.in_(user_ids), Memory.memory_date.isnot(None),
        db.extract('month', Memory.memory_date) == today_date.month,
        db.extract('day', Memory.memory_date) == today_date.day,
        db.extract('year', Memory.memory_date) < today_date.year
    ).order_by(Memory.memory_date.desc()).first()

    start_date = datetime.datetime.strptime(app.config['RELATIONSHIP_START_DATE'], '%Y-%m-%d').date()
    anniversary_days = max(1, (today_date - start_date).days + 1)
    week_start = (today_date - datetime.timedelta(days=today_date.weekday())).isoformat()
    weekly_task = CoupleTask.query.filter_by(week_start=week_start).order_by(CoupleTask.id.desc()).first()
    return render_template(
        'index.html', activities=activities[:8], fridge_data=fridge_data,
        active_question=active_question, check_in_map=check_in_map,
        on_this_day=on_this_day, anniversary_days=anniversary_days,
        weekly_task=weekly_task, today_label=today_label
    )

# (菜谱路由保持不变: recipes_list, add_recipe, recipe_detail, delete_recipe, add_log, what_can_i_make)
# ... (为简洁省略，请保留原代码) ...
RECIPES_PER_PAGE = 24

# Only equivalent ingredient names: cuts of meat are not interchangeable.
INGREDIENT_ALIASES = {'番茄': '西红柿', '土豆': '马铃薯', '洋芋': '马铃薯',
                      '包菜': '卷心菜', '圆白菜': '卷心菜', '大蒜': '蒜'}


def ingredient_matches(required, available):
    def normalize(value):
        value = re.sub(r'[（(].*', '', value).strip()
        return INGREDIENT_ALIASES.get(value, value)
    return normalize(required) == normalize(available)


@app.route('/recipes')
@login_required
def recipes_list():
    user_ids = [current_user.id]
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    system_user = User.query.filter_by(username=SYSTEM_RECIPE_USERNAME).first()
    system_id = system_user.id if system_user else None
    if system_id: user_ids.append(system_id)

    keyword = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    scope = request.args.get('scope', '').strip()
    if scope not in ('ours', 'library'):
        scope = ''
    page = request.args.get('page', 1, type=int)

    def apply_filters(query, with_category=True):
        query = query.filter(Recipe.user_id.in_(user_ids))
        if system_id and scope == 'ours':
            query = query.filter(Recipe.user_id != system_id)
        elif scope == 'library':
            query = query.filter(Recipe.user_id == system_id)
        if keyword:
            canonical = INGREDIENT_ALIASES.get(keyword, keyword)
            terms = {keyword, canonical} | {name for name, value in INGREDIENT_ALIASES.items() if value == canonical}
            query = query.filter(or_(*[
                or_(Recipe.name.ilike(f'%{term}%'),
                    Recipe.ingredients.any(Ingredient.name.ilike(f'%{term}%')))
                for term in terms
            ]))
        if with_category and category:
            if category == '未分类':
                query = query.filter(or_(Recipe.category.is_(None), Recipe.category == '', Recipe.category == '未分类'))
            else:
                query = query.filter(Recipe.category == category)
        return query

    category_counts = apply_filters(
        db.session.query(Recipe.category, db.func.count(Recipe.id)), with_category=False
    ).group_by(Recipe.category).all()
    counts = {}
    for name, total in category_counts:
        name = name or '未分类'
        counts[name] = counts.get(name, 0) + total
    categories = sorted(
        counts.items(),
        key=lambda row: row[1], reverse=True
    )

    listing = apply_filters(Recipe.query)
    if system_id:
        # The couple's own recipes should never be buried under the imported library.
        listing = listing.order_by((Recipe.user_id == system_id).asc(), Recipe.name.asc(), Recipe.id.asc())
    else:
        listing = listing.order_by(Recipe.name.asc(), Recipe.id.asc())
    pagination = listing.options(selectinload(Recipe.ingredients)).paginate(
        page=page, per_page=RECIPES_PER_PAGE, error_out=False
    )
    if pagination.pages and pagination.page > pagination.pages:
        return redirect(url_for('recipes_list', q=keyword, category=category, scope=scope, page=pagination.pages))

    own_total = Recipe.query.filter(Recipe.user_id.in_(
        [uid for uid in user_ids if uid != system_id]
    )).count()
    library_total = Recipe.query.filter_by(user_id=system_id).count() if system_id else 0

    def recipe_url(**overrides):
        params = {'q': keyword, 'category': category, 'scope': scope}
        params.update(overrides)
        return url_for('recipes_list', **{k: v for k, v in params.items() if v})

    return render_template(
        'recipes_list.html', pagination=pagination, recipes=pagination.items,
        categories=categories, total_matched=pagination.total, keyword=keyword,
        active_category=category, scope=scope, system_id=system_id,
        own_total=own_total, library_total=library_total, recipe_url=recipe_url
    )
@app.route('/add_recipe', methods=['GET', 'POST'])
@login_required
def add_recipe():
    if request.method == 'POST':
        recipe_name = request.form.get('recipe_name', '').strip()
        if not recipe_name:
            flash('菜谱名称不能为空', 'error')
            return redirect(url_for('add_recipe'))
        new_recipe = Recipe(name=recipe_name, instructions=request.form.get('instructions', '').strip(), category=request.form.get('category', '').strip() or None, user_id=current_user.id)
        db.session.add(new_recipe)
        try:
            db.session.flush()
            image_name = save_uploaded_image(request.files.get('recipe_image'), 'recipe')
            if image_name:
                new_recipe.image_file = image_name
            ing_names = request.form.getlist('ingredient_name[]'); ing_qtys = request.form.getlist('ingredient_qty[]')
            for n, q in zip(ing_names, ing_qtys):
                if n.strip(): db.session.add(Ingredient(name=n.strip(), quantity=q.strip(), recipe_id=new_recipe.id))
            sea_names = request.form.getlist('seasoning_name[]'); sea_qtys = request.form.getlist('seasoning_qty[]')
            for n, q in zip(sea_names, sea_qtys):
                if n.strip(): db.session.add(Seasoning(name=n.strip(), quantity=q.strip(), recipe_id=new_recipe.id))
            db.session.commit()
            return redirect(url_for('recipes_list'))
        except Exception as exc:
            db.session.rollback()
            app.logger.warning('add recipe failed: %s', exc)
            flash('保存菜谱失败，名称可能已经存在。', 'error')
            return redirect(url_for('add_recipe'))
    return render_template('add_recipe.html')
@app.route('/recipe/<int:recipe_id>')
@login_required
def recipe_detail(recipe_id):
    user_ids = [current_user.id]
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    system_user = User.query.filter_by(username=SYSTEM_RECIPE_USERNAME).first()
    if system_user: user_ids.append(system_user.id)
    recipe = Recipe.query.filter(Recipe.id == recipe_id, Recipe.user_id.in_(user_ids)).first()
    if not recipe: return redirect(url_for('recipes_list'))
    instructions_html = render_safe_markdown(recipe.instructions)
    tips_html = render_safe_markdown(recipe.tips) if recipe.tips else None
    return render_template('recipe_detail.html', recipe=recipe, instructions_html=instructions_html, tips_html=tips_html)
@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
def delete_recipe(recipe_id):
    r = Recipe.query.get_or_404(recipe_id)
    if r.user_id != current_user.id:
        abort(403)
    db.session.delete(r); db.session.commit()
    return redirect(url_for('recipes_list'))
@app.route('/recipe/<int:recipe_id>/add_log', methods=['POST'])
@login_required
def add_log(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    system_user = User.query.filter_by(username=SYSTEM_RECIPE_USERNAME).first()
    allowed_ids = shared_user_ids() + ([system_user.id] if system_user else [])
    if recipe.user_id not in allowed_ids:
        abort(404)
    new_log = CookingLog(time_taken=request.form.get('time_taken', '').strip(), notes=request.form.get('notes', '').strip(), recipe_id=recipe_id)
    db.session.add(new_log); db.session.commit()
    return redirect(url_for('recipe_detail', recipe_id=recipe_id))
@app.route('/what_can_i_make', methods=['GET', 'POST'])
@login_required
def what_can_i_make():
    user_ids = [current_user.id]
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    system_user = User.query.filter_by(username=SYSTEM_RECIPE_USERNAME).first()
    if system_user: user_ids.append(system_user.id)
    perfect_matches = []; partial_matches = []; pantry_input = ""
    if request.method == 'POST':
        pantry_input = request.form.get('pantry', '')
        pantry = {item.strip() for item in re.split(r'[,，、;；\s\n]+', pantry_input) if item.strip()}
        if pantry:
            all_recipes = Recipe.query.filter(Recipe.user_id.in_(user_ids)).options(
                selectinload(Recipe.ingredients)
            ).all()
            scored = []
            for recipe in all_recipes:
                required = [ing.name.strip() for ing in recipe.ingredients
                            if ing.name.strip() and '可选' not in (ing.quantity or '')]
                if not required:
                    continue
                missing = [n for n in required if not any(ingredient_matches(n, term) for term in pantry)]
                if len(missing) == len(required):
                    continue
                scored.append((len(missing), -(len(required) - len(missing)), recipe, missing))
            scored.sort(key=lambda row: (row[0], row[1], row[2].name))
            for missing_count, _, recipe, missing in scored:
                if missing_count == 0:
                    perfect_matches.append(recipe)
                elif len(partial_matches) < 40:
                    partial_matches.append((recipe, missing))
    return render_template('what_can_i_make.html', perfect_matches=perfect_matches, partial_matches=partial_matches, pantry_input=pantry_input, has_searched=request.method=='POST')

# --- V5.3 NEW: AI 菜单推荐 ---
@app.route('/ai_menu', methods=['GET', 'POST'])
@login_required
def ai_menu():
    result = None
    if request.method == 'POST':
        people_count = request.form.get('people_count', '2')
        preferences = request.form.get('preferences', '')
        
        # 获取所有可用的本地菜谱
        user_ids = [current_user.id]
        if current_user.partner_id:
            user_ids.append(current_user.partner_id)
            
        system_user = User.query.filter_by(username=SYSTEM_RECIPE_USERNAME).first()
        if system_user:
            user_ids.append(system_user.id)
            
        recipes = Recipe.query.filter(Recipe.user_id.in_(user_ids)).all()
        # 简单的随机打乱一下，防止总是用前面的菜
        # 将菜谱名字和对应的页面链接提供给 AI
        recipe_items = [f"{r.name}(链接ID:{r.id})" for r in recipes]
        random.shuffle(recipe_items)
        
        api_key = app.config.get('DASHSCOPE_API_KEY')
        if not api_key or 'sk-' not in api_key:
            flash('未配置有效的 DASHSCOPE_API_KEY，无法使用 AI 功能', 'error')
            return render_template('ai_menu.html', result=None)
            
        local_recipes_str = "、".join(recipe_items[:200])  # 提供前200个
        
        prompt_text = f"""
        你是一位专业的家庭主厨。我今天需要准备一桌丰盛的饭菜。
        要求：
        1. 就餐人数：{people_count}
        2. 饮食偏好/要求：{preferences}
        3. 请绝对优先从以下本地菜谱库中挑选菜品：【{local_recipes_str}】。
        4. 【重要】如果挑选了本地菜谱，请务必严格使用 Markdown 链接格式输出该菜名，链接地址为 `/recipe/链接ID`。
           例如选中了 "红烧肉(链接ID:15)"，在你的输出中任何提到它的地方请写成 `[红烧肉](/recipe/15)`，让用户可以点击跳转。如果本地不够吃，额外发挥的非本地菜直接写名字即可。
        5. 请输出：(1) 推荐菜单名称列表；(2) 所有推荐菜所需的材料统筹清单；(3) 简短的做菜顺序建议。
        """
        
        url = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
        headers = { 'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json' }
        data = { 
            "model": "qwen3.7-flash-2026-07-15",
            "messages": [{"role": "user", "content": prompt_text}],
            "temperature": 0.8
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=120)
            if response.status_code == 200:
                res_json = response.json()
                if 'choices' in res_json and res_json['choices']:
                    raw = res_json['choices'][0]['message']['content']
                    result = render_safe_markdown(raw)
            else:
                flash(f'AI 接口返回错误: {response.text}', 'error')
        except Exception as e:
            flash(f'请求 AI 异常: {e}', 'error')

    return render_template('ai_menu.html', result=result)

# (Partner, Journal, Memory, Wishlist 路由保持不变)
@app.route('/partner', methods=['GET'])
@login_required
def partner_page():
    users = User.query.filter(User.id.in_(shared_user_ids())).order_by(User.id).all()
    both_consented = len(users) == 2 and all(user.ai_context_consent for user in users)
    profile = CoupleAIProfile.query.first()
    return render_template(
        'partner.html', partner=current_user.partner, invite_code=current_user.invite_code,
        both_consented=both_consented, profile=profile
    )
@app.route('/partner/generate_code', methods=['POST'])
@login_required
def generate_invite_code():
    if current_user.partner_id:
        flash('已经绑定伴侣，无需生成邀请码。', 'error')
        return redirect(url_for('partner_page'))
    if not current_user.invite_code:
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        while User.query.filter_by(invite_code=code).first():
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        current_user.invite_code = code; db.session.commit()
    return redirect(url_for('partner_page'))
@app.route('/partner/redeem_code', methods=['POST'])
@login_required
def redeem_invite_code():
    code = request.form['invite_code'].strip().upper()
    target = User.query.filter_by(invite_code=code).first()
    if current_user.partner_id:
        flash('当前账号已经绑定伴侣。', 'error')
    elif not target or target.id == current_user.id:
        flash('邀请码无效。', 'error')
    elif target.partner_id:
        flash('该账号已经绑定伴侣。', 'error')
    else:
        target.partner_id = current_user.id
        current_user.partner_id = target.id
        target.invite_code = None
        db.session.commit()
        flash('伴侣绑定成功。', 'success')
    return redirect(url_for('partner_page'))

@app.route('/push/vapid-public-key')
@login_required
def vapid_public_key():
    return jsonify({"publicKey": VAPID_PUBLIC_KEY})

@app.route('/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    subscription = request.get_json(silent=True) or {}
    if not subscription.get('endpoint') or not isinstance(subscription.get('keys'), dict):
        return jsonify({'status': 'error', 'message': '无效的推送订阅'}), 400
    current_user.push_subscription = json.dumps(subscription)
    db.session.commit()
    return jsonify({"status": "ok"})

@app.route('/journal')
@login_required
def journal():
    if not current_user.partner_id: return redirect(url_for('partner_page'))
    now = datetime.datetime.now()
    try:
        year = int(request.args.get('year', now.year)); month = int(request.args.get('month', now.month))
        if not 1 <= month <= 12 or not 1900 <= year <= 2200:
            raise ValueError
    except (TypeError, ValueError):
        year, month = now.year, now.month
    user_ids = [current_user.id, current_user.partner_id]
    entries = JournalEntry.query.filter(JournalEntry.author_id.in_(user_ids), JournalEntry.date_str.like(f"{year}-{month:02d}-%")).all()
    calendar_data = {}
    for entry in entries:
        d = entry.date_str
        if d not in calendar_data: calendar_data[d] = {'me': False, 'partner': False, 'me_content': '', 'partner_content': ''}
        if entry.author_id == current_user.id: calendar_data[d]['me'] = True; calendar_data[d]['me_content'] = entry.content
        else: calendar_data[d]['partner'] = True; calendar_data[d]['partner_content'] = entry.content
    return render_template(
        'journal.html', calendar_data=calendar_data, partner_name=current_user.partner.username,
        year=year, month=month, cal_matrix=calendar.monthcalendar(year, month),
        today_str=datetime.date.today().isoformat()
    )
@app.route('/journal/add', methods=['POST'])
@login_required
def add_journal_entry():
    data = request.get_json(silent=True) or {}
    date_str = str(data.get('date', '')).strip()
    content = str(data.get('content', '')).strip()
    request_id = str(data.get('request_id', ''))[:64] or str(uuid.uuid4())
    try:
        datetime.datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'status': 'error', 'message': '日期格式无效'}), 400
    if not content:
        return jsonify({'status': 'error', 'message': '日记内容不能为空'}), 400
    if len(content) > 20000:
        return jsonify({'status': 'error', 'message': '日记内容过长'}), 400

    now = utcnow()
    statement = sqlite_insert(JournalEntry).values(
        date_str=date_str, content=content, author_id=current_user.id,
        created_at=now, updated_at=now, last_request_id=request_id
    ).on_conflict_do_update(
        index_elements=['date_str', 'author_id'],
        set_={'content': content, 'updated_at': now, 'last_request_id': request_id}
    )
    try:
        db.session.execute(statement)
        queued_id = None
        if current_user.partner:
            queued = enqueue_push(current_user.partner, '情侣小窝', f'{current_user.username} 写了一篇日记', url_for('journal'))
            db.session.flush()
            queued_id = queued.id if queued else None
        db.session.commit()
        if queued_id:
            dispatch_notification(queued_id)
        saved = JournalEntry.query.filter_by(date_str=date_str, author_id=current_user.id).first()
        return jsonify({
            'status': 'success', 'request_id': request_id,
            'saved_at': saved.updated_at.isoformat() + 'Z', 'version': saved.updated_at.isoformat()
        })
    except Exception as e:
        db.session.rollback()
        print(f"Journal save error: {e}")
        return jsonify({'status': 'error', 'message': '数据库繁忙，请重试保存'}), 500

# --- V5.4 NEW: 冰箱贴路由 ---
@app.route('/fridge/add', methods=['POST'])
@login_required
def add_fridge_item():
    title = request.form.get('title')
    target_date_str = request.form.get('target_date')
    item_type = request.form.get('item_type') # 'anniversary' 或 'countdown'
    
    if title and target_date_str and item_type:
        try:
            target_date = datetime.datetime.strptime(target_date_str, '%Y-%m-%d').date()
            new_item = FridgeItem(title=title, target_date=target_date, item_type=item_type, author_id=current_user.id)
            db.session.add(new_item)
            db.session.commit()
            flash('冰箱贴添加成功！', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'添加失败: {e}', 'error')
    
    return redirect(url_for('index'))

@app.route('/fridge/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_fridge_item(item_id):
    item = FridgeItem.query.get_or_404(item_id)
    # 允许本人或伴侣删除
    if item.author_id == current_user.id or item.author_id == current_user.partner_id:
        db.session.delete(item)
        db.session.commit()
        flash('冰箱贴已删除', 'success')
    return redirect(url_for('index'))

@app.route('/memories')
@login_required
def memories():
    if not current_user.partner_id: return redirect(url_for('partner_page'))
    user_ids = [current_user.id, current_user.partner_id]
    mems = Memory.query.filter(Memory.author_id.in_(user_ids)).order_by(Memory.memory_date.desc()).all()
    return render_template('memories.html', memories=mems)
@app.route('/memory/add', methods=['GET', 'POST'])
@login_required
def add_memory():
    if request.method == 'POST':
        new_mem = Memory(title=request.form['title'], content=request.form['content'], location=request.form['location'], author_id=current_user.id)
        if request.form['memory_date']: new_mem.memory_date = datetime.datetime.strptime(request.form['memory_date'], '%Y-%m-%d').date()
        image_name = save_uploaded_image(request.files.get('image'), 'memory')
        if request.files.get('image') and request.files['image'].filename and not image_name:
            flash('图片格式无效或无法读取。', 'error')
            return render_template('add_memory.html')
        if image_name:
            new_mem.image_file = image_name
        db.session.add(new_mem); db.session.commit()
        return redirect(url_for('memories'))
    return render_template('add_memory.html')
@app.route('/memory/<int:memory_id>')
@login_required
def memory_detail(memory_id):
    mem = Memory.query.get_or_404(memory_id)
    if not can_access_author(mem.author_id):
        abort(404)
    return render_template('memory_detail.html', memory=mem)
@app.route('/memory/<int:memory_id>/delete', methods=['POST'])
@login_required
def delete_memory(memory_id):
    mem = Memory.query.get_or_404(memory_id)
    if mem.author_id != current_user.id:
        abort(403)
    db.session.delete(mem); db.session.commit()
    return redirect(url_for('memories'))
@app.route('/wishlist')
@login_required
def wishlist():
    if not current_user.partner_id: return redirect(url_for('partner_page'))
    user_ids = [current_user.id, current_user.partner_id]
    all_w = WishlistItem.query.filter(WishlistItem.author_id.in_(user_ids)).order_by(WishlistItem.is_completed.asc(), WishlistItem.id.desc()).all()
    return render_template('wishlist.html', todo_wishes=[w for w in all_w if not w.is_completed], done_wishes=[w for w in all_w if w.is_completed])
@app.route('/wishlist/add', methods=['POST'])
@login_required
def add_wish():
    db.session.add(WishlistItem(content=request.form['content'], author_id=current_user.id)); db.session.commit()
    return redirect(url_for('wishlist'))
@app.route('/wishlist/toggle/<int:item_id>', methods=['POST'])
@login_required
def toggle_wish(item_id):
    item = db.session.get(WishlistItem, item_id)
    if not item or not can_access_author(item.author_id):
        abort(404)
    item.is_completed = not item.is_completed; db.session.commit()
    return redirect(url_for('wishlist'))
@app.route('/wishlist/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_wish(item_id):
    item = db.session.get(WishlistItem, item_id)
    if item and item.author_id == current_user.id: db.session.delete(item); db.session.commit()
    return redirect(url_for('wishlist'))

def get_current_daily_question(today=None):
    """Return today's question, or an unanswered question carried over from earlier."""
    today = today or datetime.date.today()
    # A completed/skipped question must still be reused for the rest of its day.
    # Checking the date first prevents its status from accidentally triggering a
    # second AI generation on the same day.
    question = DailyQuestion.query.filter_by(
        date_str=today.isoformat(), is_daily_primary=True
    ).first()
    if question:
        return question
    return DailyQuestion.query.filter_by(
        status='open', is_daily_primary=True
    ).order_by(DailyQuestion.id.desc()).first()


def get_or_create_daily_question(today=None):
    """Keep one question per day while carrying unanswered questions across days."""
    today = today or datetime.date.today()
    question = get_current_daily_question(today)
    if question:
        return question
    content, meta = generate_question_from_ai()
    source = 'AI 生成'
    if not content:
        content = choose_fallback_question()
        source = '精选题库'
    question = DailyQuestion(
        content=content, date_str=today.isoformat(), source=source,
        status='open', is_daily_primary=True,
        generation_meta=json.dumps(meta, ensure_ascii=False)
    )
    db.session.add(question)
    try:
        db.session.commit()
        return question
    except IntegrityError:
        db.session.rollback()
        question = get_current_daily_question(today)
        if question:
            return question
        raise


@app.route('/daily_question')
@login_required
def daily_question():
    if not current_user.partner_id:
        flash('请先绑定伴侣。', 'error')
        return redirect(url_for('partner_page'))

    requested_id = request.args.get('question_id', type=int)
    question = db.session.get(DailyQuestion, requested_id) if requested_id else None
    if not question:
        question = get_or_create_daily_question()

    my_answer = DailyAnswer.query.filter_by(question_id=question.id, user_id=current_user.id).first()
    partner_answer = DailyAnswer.query.filter_by(question_id=question.id, user_id=current_user.partner_id).first()
    is_unlocked = bool(my_answer and partner_answer)
    my_like = QuestionLike.query.filter_by(question_id=question.id, user_id=current_user.id).first()
    partner_like = QuestionLike.query.filter_by(question_id=question.id, user_id=current_user.partner_id).first()
    my_feedback = QuestionFeedback.query.filter_by(question_id=question.id, user_id=current_user.id).first()
    users = User.query.filter(User.id.in_(shared_user_ids())).order_by(User.id).all()
    both_consented = len(users) == 2 and all(user.ai_context_consent for user in users)
    profile = CoupleAIProfile.query.first()
    return render_template(
        'daily_question.html', question=question, my_answer=my_answer,
        partner_answer=partner_answer, is_unlocked=is_unlocked,
        partner_name=current_user.partner.username, my_like=my_like,
        partner_like=partner_like, both_liked=bool(my_like and partner_like),
        my_feedback=my_feedback, feedback_reasons=QUESTION_FEEDBACK_REASONS,
        both_consented=both_consented, profile=profile
    )

# --- V5.2 NEW: 历史回顾路由 ---
@app.route('/daily_question/history')
@login_required
def daily_history():
    if not current_user.partner_id:
        return redirect(url_for('partner_page'))
        
    all_questions = DailyQuestion.query.order_by(DailyQuestion.id.desc()).all()
    
    completed_history = []
    
    for q in all_questions:
        # 2. 查找这个问题的回答
        my_ans = DailyAnswer.query.filter_by(question_id=q.id, user_id=current_user.id).first()
        partner_ans = DailyAnswer.query.filter_by(question_id=q.id, user_id=current_user.partner_id).first()
        
        # 3. 核心逻辑：只有双方都回答了，才算"历史记录"
        if my_ans and partner_ans:
            completed_history.append({
                'date': q.date_str,
                'content': q.content,
                'source': q.source,
                'my_answer': my_ans.content,
                'partner_answer': partner_ans.content
            })
            
    return render_template('daily_history.html', history=completed_history)

@app.route('/daily_question/answer/<int:question_id>', methods=['POST'])
@login_required
def answer_daily_question(question_id):
    question = DailyQuestion.query.get_or_404(question_id)
    content = request.form.get('content', '').strip()
    if not content:
        flash('回答不能为空。', 'error'); return redirect(url_for('daily_question', question_id=question_id))
    if len(content) > 5000:
        flash('回答内容过长。', 'error'); return redirect(url_for('daily_question', question_id=question_id))
        
    existing = DailyAnswer.query.filter_by(question_id=question_id, user_id=current_user.id).first()
    if existing:
        existing.content = content
        flash('回答已更新。', 'success')
    else:
        new_answer = DailyAnswer(content=content, question_id=question_id, user_id=current_user.id)
        db.session.add(new_answer)
        flash('回答已提交！', 'success')
        
    db.session.flush()
    answer_count = DailyAnswer.query.filter_by(question_id=question_id).count()
    if answer_count >= 2:
        question.status = 'completed'
        question.close_reason = 'both_answered'
        question.closed_at = utcnow()
    if current_user.partner:
        queued = enqueue_push(current_user.partner, '情侣小窝', f'{current_user.username} 回答了当前问题', url_for('daily_question', question_id=question_id))
        db.session.flush()
        queued_id = queued.id if queued else None
    else:
        queued_id = None
    db.session.commit()
    if queued_id:
        dispatch_notification(queued_id)

    return redirect(url_for('daily_question', question_id=question_id))

@app.route('/daily_question/<int:question_id>/like', methods=['POST'])
@login_required
def like_daily_question(question_id):
    DailyQuestion.query.get_or_404(question_id)
    existing = QuestionLike.query.filter_by(question_id=question_id, user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(QuestionLike(question_id=question_id, user_id=current_user.id))
    db.session.commit()
    return redirect(url_for('daily_question', question_id=question_id))


@app.route('/daily_question/<int:question_id>/feedback', methods=['POST'])
@login_required
def feedback_daily_question(question_id):
    question = DailyQuestion.query.get_or_404(question_id)
    feedback_type = request.form.get('feedback_type', '').strip()
    reason = request.form.get('reason', '').strip() or None
    if feedback_type not in {'disliked', 'skipped'}:
        abort(400)
    if reason and reason not in QUESTION_FEEDBACK_REASONS:
        abort(400)
    feedback = QuestionFeedback.query.filter_by(question_id=question_id, user_id=current_user.id).first()
    if feedback:
        feedback.feedback_type = feedback_type
        feedback.reason = reason
        feedback.created_at = utcnow()
    else:
        db.session.add(QuestionFeedback(
            question_id=question_id, user_id=current_user.id,
            feedback_type=feedback_type, reason=reason
        ))
    if feedback_type == 'skipped' and question.status == 'open':
        question.status = 'skipped'
        question.close_reason = reason or 'skipped'
        question.closed_at = utcnow()
    db.session.commit()
    flash('反馈已记录。', 'success')
    if feedback_type == 'skipped':
        return redirect(url_for('daily_question'))
    return redirect(url_for('daily_question', question_id=question_id))


@app.route('/ai-profile/consent', methods=['POST'])
@login_required
def ai_profile_consent():
    current_user.ai_context_consent = request.form.get('consent') == 'yes'
    db.session.commit()
    flash('AI 内容授权已更新。', 'success')
    return redirect(url_for('partner_page'))


def _build_profile_source():
    ids = shared_user_ids()
    parts = []
    for item in JournalEntry.query.filter(JournalEntry.author_id.in_(ids)).order_by(JournalEntry.id.desc()).limit(20):
        parts.append(f'日记主题：{item.content[:300]}')
    for item in Memory.query.filter(Memory.author_id.in_(ids)).order_by(Memory.id.desc()).limit(15):
        parts.append(f'回忆：{item.title}；{item.content[:200]}')
    for item in WishlistItem.query.filter(WishlistItem.author_id.in_(ids)).order_by(WishlistItem.id.desc()).limit(15):
        parts.append(f'愿望：{item.content}')
    for item in DailyAnswer.query.filter(DailyAnswer.user_id.in_(ids)).order_by(DailyAnswer.id.desc()).limit(20):
        parts.append(f'问答内容：{item.content[:250]}')
    return '\n'.join(parts)[:10000]


@app.route('/ai-profile/refresh', methods=['POST'])
@login_required
def refresh_ai_profile():
    users = User.query.filter(User.id.in_(shared_user_ids())).all()
    if len(users) != 2 or not all(user.ai_context_consent for user in users):
        flash('需要双方都开启授权后才能更新 AI 档案。', 'error')
        return redirect(url_for('partner_page'))
    api_key = app.config.get('DASHSCOPE_API_KEY')
    if not api_key:
        flash('尚未配置 AI API Key。', 'error')
        return redirect(url_for('partner_page'))
    prompt = f"""将以下情侣内容整理成不超过600字的客观档案，只保留共同兴趣、近期生活主题、沟通偏好和明确禁区。不要评价关系，不推断疾病或人格。\n{_build_profile_source()}"""
    try:
        response = requests.post(
            'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={'model': 'qwen3.7-flash-2026-07-15', 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0.2},
            timeout=120
        )
        response.raise_for_status()
        summary = response.json()['choices'][0]['message']['content'].strip()[:1200]
        profile = CoupleAIProfile.query.first() or CoupleAIProfile()
        profile.summary = summary
        profile.updated_at = utcnow()
        db.session.add(profile)
        db.session.commit()
        flash('AI 情侣档案已更新。', 'success')
    except Exception as exc:
        app.logger.warning('profile refresh failed: %s', exc)
        flash('档案更新失败，请稍后重试。', 'error')
    return redirect(url_for('partner_page'))


@app.route('/daily-check-in', methods=['POST'])
@login_required
def daily_check_in():
    mood = request.form.get('mood', '').strip()
    energy = request.form.get('energy', '').strip()
    need = request.form.get('need', '').strip()
    if mood not in {'开心', '平静', '低落', '焦虑', '疲惫'}:
        abort(400)
    if energy not in {'充足', '一般', '很低'}:
        abort(400)
    if need not in {'想聊聊', '想抱抱', '需要陪伴', '想安静一下', '一切都好'}:
        abort(400)
    today = datetime.date.today().isoformat()
    check_in = DailyCheckIn.query.filter_by(date_str=today, user_id=current_user.id).first()
    if check_in:
        check_in.mood, check_in.energy, check_in.need = mood, energy, need
        check_in.updated_at = utcnow()
    else:
        db.session.add(DailyCheckIn(date_str=today, user_id=current_user.id, mood=mood, energy=energy, need=need))
    if current_user.partner:
        queued = enqueue_push(current_user.partner, '情侣小窝', f'{current_user.username} 更新了今天的状态', url_for('index'))
        db.session.flush()
        queued_id = queued.id if queued else None
    else:
        queued_id = None
    db.session.commit()
    if queued_id:
        dispatch_notification(queued_id)
    flash('今天的状态已更新。', 'success')
    return redirect(url_for('index'))


TASK_POOL = [
    '一起选一首本周主题歌', '交换一张今天最喜欢的照片', '一起散步十分钟，不带耳机',
    '从愿望清单里挑一件近期能完成的小事', '一起复刻一道以前吃过的菜',
    '各自说一件这周想感谢对方的小事', '一起整理并保存一张最近的合照'
]


@app.route('/weekly-task/create', methods=['POST'])
@login_required
def create_weekly_task():
    today = datetime.date.today()
    week_start = (today - datetime.timedelta(days=today.weekday())).isoformat()
    existing = CoupleTask.query.filter_by(week_start=week_start).first()
    if not existing:
        recent_titles = {task.title for task in CoupleTask.query.order_by(CoupleTask.id.desc()).limit(5)}
        options = [title for title in TASK_POOL if title not in recent_titles] or TASK_POOL
        db.session.add(CoupleTask(week_start=week_start, title=random.choice(options)))
        db.session.commit()
    return redirect(url_for('index'))


@app.route('/weekly-task/<int:task_id>/<action>', methods=['POST'])
@login_required
def update_weekly_task(task_id, action):
    task = CoupleTask.query.get_or_404(task_id)
    if action not in {'complete', 'skip'}:
        abort(400)
    task.status = 'completed' if action == 'complete' else 'skipped'
    task.completed_by = current_user.id if action == 'complete' else None
    db.session.commit()
    return redirect(url_for('index'))


def current_week_start():
    today = datetime.date.today()
    return (today - datetime.timedelta(days=today.weekday())).isoformat()


@app.route('/weekly', methods=['GET', 'POST'])
@login_required
def weekly_reflection():
    if not current_user.partner_id:
        return redirect(url_for('partner_page'))
    week_start = current_week_start()
    reflection = WeeklyReflection.query.filter_by(week_start=week_start).first()
    if not reflection:
        reflection = WeeklyReflection(week_start=week_start)
        db.session.add(reflection)
        db.session.commit()
    users = sorted(shared_user_ids())
    current_slot = 1 if current_user.id == users[0] else 2
    if request.method == 'POST':
        gratitude = request.form.get('gratitude', '').strip()[:3000]
        setattr(reflection, f'gratitude_user_{current_slot}', gratitude or None)
        setattr(reflection, f'confirmed_user_{current_slot}', bool(gratitude))
        week_date = datetime.date.fromisoformat(week_start)
        week_end = week_date + datetime.timedelta(days=6)
        answer_count = DailyAnswer.query.join(DailyQuestion).filter(
            DailyQuestion.date_str.between(week_start, week_end.isoformat()),
            DailyAnswer.user_id.in_(users)
        ).count()
        memory_count = Memory.query.filter(
            Memory.author_id.in_(users), Memory.created_at >= datetime.datetime.combine(week_date, datetime.time.min)
        ).count()
        reflection.summary = f'这周留下了 {answer_count} 条问答和 {memory_count} 条新回忆。'
        db.session.commit()
        flash('本周小结已保存。', 'success')
        return redirect(url_for('weekly_reflection'))
    my_gratitude = getattr(reflection, f'gratitude_user_{current_slot}') or ''
    partner_gratitude = getattr(reflection, f'gratitude_user_{2 if current_slot == 1 else 1}') or ''
    both_confirmed = reflection.confirmed_user_1 and reflection.confirmed_user_2
    return render_template(
        'weekly.html', reflection=reflection, my_gratitude=my_gratitude,
        partner_gratitude=partner_gratitude if both_confirmed else None,
        both_confirmed=both_confirmed, partner_name=current_user.partner.username
    )

if __name__ == '__main__':
    app.run(debug=app_env == 'development', port=5000)
