import os
import string 
import secrets 
import datetime
import calendar
import re
import random
import requests
import json
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify 
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate 
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename 
from sqlalchemy import or_ 

# NEW: 导入通义千问 SDK
import dashscope
from http import HTTPStatus

# --- 1. 配置区域 ---
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'recipes.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'a_very_secret_key_change_this_for_production'
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# --- NEW: 通义千问 API Key 配置 ---
# 请在这里填入您的阿里云 DashScope API Key
app.config['DASHSCOPE_API_KEY'] = 'sk-3e0826f5b610402d849223ef6029c421' 

# --- NEW: 关键修复！增加 SQLite 等待时间 ---
# 默认只有 5秒，遇到并发容易报错。改成 30秒。
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 30} 
}

db = SQLAlchemy(app)
migrate = Migrate(app, db) 
login_manager = LoginManager(app)
login_manager.login_view = 'login' 
login_manager.login_message = '您需要先登录才能访问此页面。'
login_manager.login_message_category = 'error'

# 本地题库 (AI 失败时的兜底)
QUESTIONS_POOL = [
    "如果我们可以去世界上任何地方旅行，你想去哪里？",
    "你最喜欢我身上的哪一点？",
    "我们在一起最美好的回忆是什么？",
    "如果中了一千万，你第一件事想做什么？",
    "你觉得完美的约会是什么样的？",
    "最近有什么事情让你感到压力很大吗？",
    "你小时候的梦想是什么？",
    "如果可以拥有一种超能力，你想要什么？",
    "我们老了以后，你希望过什么样的生活？",
    "此时此刻，你最想吃什么？"
]

# --- NEW: AI 生成函数 (通义千问) ---
def generate_question_from_ai():
    api_key = app.config.get('DASHSCOPE_API_KEY')
    if not api_key or 'sk-' not in api_key:
        print("警告: 未配置有效的 DASHSCOPE_API_KEY")
        return None

    # 1. 定义多样化的主题库 (强制 AI 聚焦特定领域)
    topics = [
        "童年回忆与成长经历", "具体的未来规划", "价值观与人生哲学", "旅行中的突发状况", 
        "对彼此的初印象与变化", "生活习惯与怪癖", "假如世界末日/假如中奖 (脑洞假设)", 
        "性与亲密关系", "工作挑战与职业理想", "家庭关系与父母", 
        "最尴尬或最糗的时刻", "最自豪的成就", "内心深处的恐惧", 
        "精神世界与梦想", "日常琐事与家务分工", "对于衰老与死亡的看法"
    ]
    
    # 2. 定义不同的提问风格 (调整语气)
    styles = [
        "幽默风趣的", "深情浪漫的", "严肃深刻的", "轻松随意的", 
        "充满好奇心的", "怀旧感伤的", "脑洞大开的", "犀利直接的"
    ]
    
    # 3. 随机抽取
    selected_topic = random.choice(topics)
    selected_style = random.choice(styles)
    
    print(f"DEBUG: 今天 AI 的生成方向 -> 主题: {selected_topic}, 风格: {selected_style}")

    url = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation'
    headers = { 'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json' }
    
    # 4. 构造更具体的 Prompt
    prompt_text = f"""
    请生成一个适合情侣之间互相询问的每日互动问题。
    
    【强制要求】：
    1. 核心主题必须关于：“{selected_topic}”。
    2. 提问风格必须是：“{selected_style}”。
    3. 避免生成那种泛泛而谈的“你最喜欢什么...”的问题，要具体、有场景感。
    4. 问题要能引发两人的深入对话，而不是简单的“是/否”回答。
    5. 只返回问题本身，不要包含任何前缀、引号或解释。
    6. 必须是中文。
    """
    
    # 为了增加随机性，提高 temperature 参数 (0.0 - 1.0, 越高越随机)
    data = { 
        "model": "qwen-turbo", 
        "input": { "messages": [{"role": "user", "content": prompt_text}] }, 
        "parameters": { 
            "result_format": "message",
            "temperature": 0.85,  # 提高随机性
            "top_p": 0.8 
        } 
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
        if response.status_code == 200:
            result = response.json()
            if 'output' in result and 'choices' in result['output']:
                content = result['output']['choices'][0]['message']['content']
                return content.strip().replace('"', '').replace('“', '').replace('”', '')
        return None
    except Exception as e:
        print(f"AI 生成异常: {e}")
        return None


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- 2. 数据库模型 ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    recipes = db.relationship('Recipe', backref='author', lazy=True, cascade="all, delete-orphan")
    invite_code = db.Column(db.String(6), unique=True, nullable=True) 
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
    name = db.Column(db.String(100), nullable=False, unique=True) 
    instructions = db.Column(db.Text, nullable=True)
    image_file = db.Column(db.String(100), nullable=False, default='default.jpg')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) 
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
    date_cooked = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    time_taken = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)
class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_str = db.Column(db.String(10), nullable=False) 
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('date_str', 'author_id', name='_date_author_uc'),)
class Memory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    memory_date = db.Column(db.Date, nullable=True) 
    location = db.Column(db.String(100), nullable=True) 
    content = db.Column(db.Text, nullable=False)
    image_file = db.Column(db.String(100), nullable=False, default='default.jpg') 
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
class WishlistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(300), nullable=False)
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# --- V5.0 NEW: 每日一问模型 ---
class DailyQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    date_str = db.Column(db.String(10), unique=True, nullable=False) 
    source = db.Column(db.String(20), default='随机题库')
    answers = db.relationship('DailyAnswer', backref='question', lazy=True, cascade="all, delete-orphan")

class DailyAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('daily_question.id'), nullable=False)


# --- 3. 辅助函数 ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- 4. 路由 ---

# (login, logout, register 保持不变)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user is None or not user.check_password(request.form['password']):
            flash('无效的用户名或密码', 'error'); return redirect(url_for('login'))
        login_user(user, remember=True); return redirect(url_for('index'))
    return render_template('login.html')
@app.route('/logout')
def logout():
    logout_user(); return redirect(url_for('login'))
@app.route('/register', methods=['GET', 'POST'])
def register():
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
    user_ids = [current_user.id]
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    activities = []
    recent_recipes = Recipe.query.filter(Recipe.user_id.in_(user_ids)).order_by(Recipe.id.desc()).limit(3).all()
    for r in recent_recipes: activities.append({'type': 'recipe', 'time': r.id, 'text': f"{r.author.username} 添加了新菜谱: {r.name}"})
    recent_memories = Memory.query.filter(Memory.author_id.in_(user_ids)).order_by(Memory.id.desc()).limit(3).all()
    for m in recent_memories: activities.append({'type': 'memory', 'time': m.id, 'text': f"{m.author.username} 添加了新回忆: {m.title}"})
    recent_wishes = WishlistItem.query.filter(WishlistItem.author_id.in_(user_ids)).order_by(WishlistItem.id.desc()).limit(3).all()
    for w in recent_wishes:
        action = "完成了愿望" if w.is_completed else "许下了愿望"
        activities.append({'type': 'wishlist', 'time': w.id, 'text': f"{w.author.username} {action}: {w.content}"})
    recent_journals = JournalEntry.query.filter(JournalEntry.author_id.in_(user_ids)).order_by(JournalEntry.id.desc()).limit(3).all()
    for j in recent_journals: activities.append({'type': 'journal', 'time': j.id, 'text': f"{j.author.username} 写了一篇日记 ({j.date_str})"})
    activities.sort(key=lambda x: x['time'], reverse=True)
    return render_template('index.html', activities=activities[:10])

# (菜谱路由保持不变: recipes_list, add_recipe, recipe_detail, delete_recipe, add_log, what_can_i_make)
# ... (为简洁省略，请保留原代码) ...
@app.route('/recipes')
@login_required
def recipes_list():
    user_ids = [current_user.id]; 
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    all_recipes = Recipe.query.filter(Recipe.user_id.in_(user_ids)).order_by(Recipe.id.desc()).all() 
    return render_template('recipes_list.html', recipes=all_recipes)
@app.route('/add_recipe', methods=['GET', 'POST'])
@login_required
def add_recipe():
    if request.method == 'POST':
        new_recipe = Recipe(name=request.form['recipe_name'], instructions=request.form['instructions'], user_id=current_user.id)
        db.session.add(new_recipe)
        try: db.session.commit()
        except: db.session.rollback(); return redirect(url_for('add_recipe'))
        if 'recipe_image' in request.files:
            f = request.files['recipe_image']
            if f.filename != '' and allowed_file(f.filename):
                fname = secure_filename(f.filename); ext = fname.rsplit('.', 1)[1].lower()
                new_recipe.image_file = f"recipe_{new_recipe.id}.{ext}"
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], new_recipe.image_file))
        ing_names = request.form.getlist('ingredient_name[]'); ing_qtys = request.form.getlist('ingredient_qty[]')
        for n, q in zip(ing_names, ing_qtys): db.session.add(Ingredient(name=n, quantity=q, recipe_id=new_recipe.id))
        sea_names = request.form.getlist('seasoning_name[]'); sea_qtys = request.form.getlist('seasoning_qty[]')
        for n, q in zip(sea_names, sea_qtys): db.session.add(Seasoning(name=n, quantity=q, recipe_id=new_recipe.id))
        db.session.commit(); return redirect(url_for('recipes_list'))
    return render_template('add_recipe.html')
@app.route('/recipe/<int:recipe_id>')
@login_required
def recipe_detail(recipe_id):
    user_ids = [current_user.id]; 
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    recipe = Recipe.query.filter(Recipe.id == recipe_id, Recipe.user_id.in_(user_ids)).first()
    if not recipe: return redirect(url_for('recipes_list'))
    return render_template('recipe_detail.html', recipe=recipe)
@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
def delete_recipe(recipe_id):
    r = Recipe.query.get_or_404(recipe_id)
    if r.author_id == current_user.id: db.session.delete(r); db.session.commit()
    return redirect(url_for('recipes_list'))
@app.route('/recipe/<int:recipe_id>/add_log', methods=['POST'])
@login_required
def add_log(recipe_id):
    new_log = CookingLog(time_taken=request.form['time_taken'], notes=request.form['notes'], recipe_id=recipe_id)
    db.session.add(new_log); db.session.commit()
    return redirect(url_for('recipe_detail', recipe_id=recipe_id))
@app.route('/what_can_i_make', methods=['GET', 'POST'])
@login_required
def what_can_i_make():
    user_ids = [current_user.id]
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    perfect_matches = []; partial_matches = []; pantry_input = ""
    if request.method == 'POST':
        pantry_input = request.form['pantry']
        user_pantry_set = {item.strip() for item in re.split(r'[,\s\n]+', pantry_input) if item.strip()}
        all_recipes = Recipe.query.filter(Recipe.user_id.in_(user_ids)).all()
        for recipe in all_recipes:
            req_ings = {ing.name.strip() for ing in recipe.ingredients}
            if req_ings and req_ings.issubset(user_pantry_set): perfect_matches.append(recipe)
            elif req_ings:
                missing = req_ings.difference(user_pantry_set)
                if len(missing) < len(req_ings): partial_matches.append((recipe, list(missing)))
    return render_template('what_can_i_make.html', perfect_matches=perfect_matches, partial_matches=partial_matches, pantry_input=pantry_input, has_searched=request.method=='POST')

# (Partner, Journal, Memory, Wishlist 路由保持不变)
@app.route('/partner', methods=['GET'])
@login_required
def partner_page():
    return render_template('partner.html', partner=current_user.partner, invite_code=current_user.invite_code)
@app.route('/partner/generate_code', methods=['POST'])
@login_required
def generate_invite_code():
    if not current_user.invite_code:
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for i in range(6))
        current_user.invite_code = code; db.session.commit()
    return redirect(url_for('partner_page'))
@app.route('/partner/redeem_code', methods=['POST'])
@login_required
def redeem_invite_code():
    code = request.form['invite_code'].strip().upper()
    target = User.query.filter_by(invite_code=code).first()
    if target and target.id != current_user.id:
        target.partner_id = current_user.id; current_user.partner_id = target.id; target.invite_code = None; db.session.commit()
    return redirect(url_for('partner_page'))
@app.route('/journal')
@login_required
def journal():
    if not current_user.partner_id: return redirect(url_for('partner_page'))
    now = datetime.datetime.now()
    try: year = int(request.args.get('year', now.year)); month = int(request.args.get('month', now.month))
    except: year, month = now.year, now.month
    user_ids = [current_user.id, current_user.partner_id]
    entries = JournalEntry.query.filter(JournalEntry.author_id.in_(user_ids), JournalEntry.date_str.like(f"{year}-{month:02d}-%")).all()
    calendar_data = {}
    for entry in entries:
        d = entry.date_str
        if d not in calendar_data: calendar_data[d] = {'me': False, 'partner': False, 'me_content': '', 'partner_content': ''}
        if entry.author_id == current_user.id: calendar_data[d]['me'] = True; calendar_data[d]['me_content'] = entry.content
        else: calendar_data[d]['partner'] = True; calendar_data[d]['partner_content'] = entry.content
    return render_template('journal.html', calendar_data=calendar_data, partner_name=current_user.partner.username, year=year, month=month, cal_matrix=calendar.monthcalendar(year, month))
@app.route('/journal/add', methods=['POST'])
@login_required
def add_journal_entry():
    data = request.json; date, content = data.get('date'), data.get('content')
    existing = JournalEntry.query.filter_by(date_str=date, author_id=current_user.id).first()
    if existing: existing.content = content
    else: db.session.add(JournalEntry(date_str=date, content=content, author_id=current_user.id))
    db.session.commit()
    return jsonify({'status':'success'})
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
        db.session.add(new_mem); db.session.commit()
        if 'image' in request.files:
             f = request.files['image']
             if f.filename != '' and allowed_file(f.filename):
                 fname = secure_filename(f.filename); ext = fname.rsplit('.', 1)[1].lower()
                 new_mem.image_file = f"memory_{new_mem.id}.{ext}"; f.save(os.path.join(app.config['UPLOAD_FOLDER'], new_mem.image_file)); db.session.commit()
        return redirect(url_for('memories'))
    return render_template('add_memory.html')
@app.route('/memory/<int:memory_id>')
@login_required
def memory_detail(memory_id):
    mem = Memory.query.get_or_404(memory_id)
    return render_template('memory_detail.html', memory=mem)
@app.route('/memory/<int:memory_id>/delete', methods=['POST'])
@login_required
def delete_memory(memory_id):
    mem = Memory.query.get_or_404(memory_id)
    if mem.author_id == current_user.id: db.session.delete(mem); db.session.commit()
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
    item = WishlistItem.query.get(item_id)
    if item: item.is_completed = not item.is_completed; db.session.commit()
    return redirect(url_for('wishlist'))
@app.route('/wishlist/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_wish(item_id):
    item = WishlistItem.query.get(item_id)
    if item and item.author_id == current_user.id: db.session.delete(item); db.session.commit()
    return redirect(url_for('wishlist'))

# --- V5.2 UPDATE: 每日一问 (带来源标注) ---
@app.route('/daily_question')
@login_required
def daily_question():
    if not current_user.partner_id:
        flash('请先绑定伴侣。', 'error'); return redirect(url_for('partner_page'))

    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    
    # 1. 检查今天是否已有问题
    question = DailyQuestion.query.filter_by(date_str=today_str).first()
    
    if not question:
        # --- AI 生成逻辑 ---
        new_content = generate_question_from_ai()
        source = "AI 生成" # 标记来源
        
        # 兜底
        if not new_content:
            new_content = random.choice(QUESTIONS_POOL)
            source = "随机题库" # 标记来源
            
        question = DailyQuestion(content=new_content, date_str=today_str, source=source)
        db.session.add(question)
        db.session.commit()
    
    my_answer = DailyAnswer.query.filter_by(question_id=question.id, user_id=current_user.id).first()
    partner_answer = DailyAnswer.query.filter_by(question_id=question.id, user_id=current_user.partner_id).first()
    is_unlocked = (my_answer is not None) and (partner_answer is not None)
    
    return render_template('daily_question.html', 
                           question=question, 
                           my_answer=my_answer, 
                           partner_answer=partner_answer,
                           is_unlocked=is_unlocked,
                           partner_name=current_user.partner.username)

# --- V5.2 NEW: 历史回顾路由 ---
@app.route('/daily_question/history')
@login_required
def daily_history():
    if not current_user.partner_id:
        return redirect(url_for('partner_page'))
        
    # 1. 获取所有历史问题 (按日期倒序)
    all_questions = DailyQuestion.query.order_by(DailyQuestion.date_str.desc()).all()
    
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
    content = request.form.get('content')
    if not content:
        flash('回答不能为空哦。', 'error'); return redirect(url_for('daily_question'))
        
    existing = DailyAnswer.query.filter_by(question_id=question_id, user_id=current_user.id).first()
    if existing:
        existing.content = content
        flash('回答已更新。', 'success')
    else:
        new_answer = DailyAnswer(content=content, question_id=question_id, user_id=current_user.id)
        db.session.add(new_answer)
        flash('回答已提交！', 'success')
        
    db.session.commit()
    return redirect(url_for('daily_question'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
