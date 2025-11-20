import os
import string 
import secrets 
import datetime
import calendar
import re
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify 
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate 
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename 
from sqlalchemy import or_ 

# --- 1. 配置区域 (必须在最前面) ---
basedir = os.path.abspath(os.path.dirname(__file__))

# 关键：在这里初始化 'app' 变量
app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'recipes.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'a_very_secret_key_change_this_for_production'
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)
migrate = Migrate(app, db) 
login_manager = LoginManager(app)
login_manager.login_view = 'login' 
login_manager.login_message = '您需要先登录才能访问此页面。'
login_manager.login_message_category = 'error'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- 2. 数据库模型 (Models) ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    recipes = db.relationship('Recipe', backref='author', lazy=True, cascade="all, delete-orphan")
    invite_code = db.Column(db.String(6), unique=True, nullable=True) 
    partner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) 
    partner = db.relationship(
        'User', 
        remote_side=[id], 
        primaryjoin=partner_id == id, 
        uselist=False,
        lazy=True 
    )
    journal_entries = db.relationship('JournalEntry', backref='author', lazy=True)
    memories = db.relationship('Memory', backref='author', lazy=True)
    wishlist_items = db.relationship('WishlistItem', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

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

# --- 3. 辅助函数 ---

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- 4. 用户认证路由 ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user is None or not user.check_password(request.form['password']):
            flash('无效的用户名或密码', 'error')
            return redirect(url_for('login'))
        login_user(user, remember=True)
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('用户名已存在, 请换一个', 'error')
            return redirect(url_for('register'))
        user = User(username=request.form['username'])
        user.set_password(request.form['password'])
        db.session.add(user)
        try:
            db.session.commit()
            flash('注册成功! 请登录。', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'注册时出错: {e}', 'error')
            return redirect(url_for('register'))
    return render_template('register.html')

# --- 5. 首页与仪表盘 (V4.5 动态版) ---

@app.route('/')
@login_required
def index():
    # 1. 获取用户和伴侣 ID
    user_ids = [current_user.id]
    if current_user.partner_id:
        user_ids.append(current_user.partner_id)
    
    activities = []

    # 2. 获取最近的菜谱 (Recipe)
    recent_recipes = Recipe.query.filter(Recipe.user_id.in_(user_ids)).order_by(Recipe.id.desc()).limit(3).all()
    for r in recent_recipes:
        activities.append({
            'type': 'recipe',
            'time': r.id, 
            'text': f"{r.author.username} 添加了新菜谱: {r.name}"
        })

    # 3. 获取最近的回忆 (Memory)
    recent_memories = Memory.query.filter(Memory.author_id.in_(user_ids)).order_by(Memory.id.desc()).limit(3).all()
    for m in recent_memories:
        activities.append({
            'type': 'memory',
            'time': m.id,
            'text': f"{m.author.username} 添加了新回忆: {m.title}"
        })

    # 4. 获取最近的愿望 (Wishlist)
    recent_wishes = WishlistItem.query.filter(WishlistItem.author_id.in_(user_ids)).order_by(WishlistItem.id.desc()).limit(3).all()
    for w in recent_wishes:
        action = "完成了愿望" if w.is_completed else "许下了愿望"
        activities.append({
            'type': 'wishlist',
            'time': w.id,
            'text': f"{w.author.username} {action}: {w.content}"
        })

    # 5. 获取最近的日记 (Journal)
    recent_journals = JournalEntry.query.filter(JournalEntry.author_id.in_(user_ids)).order_by(JournalEntry.id.desc()).limit(3).all()
    for j in recent_journals:
        activities.append({
            'type': 'journal',
            'time': j.id,
            'text': f"{j.author.username} 写了一篇日记 ({j.date_str})"
        })
    
    # 6. 混合排序并截取前 10 条
    activities.sort(key=lambda x: x['time'], reverse=True)
    latest_activities = activities[:10]

    return render_template('index.html', activities=latest_activities)


# --- 6. 菜谱功能路由 ---

@app.route('/recipes')
@login_required
def recipes_list():
    user_ids = [current_user.id]
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    all_recipes = Recipe.query.filter(Recipe.user_id.in_(user_ids)).order_by(Recipe.id.desc()).all() 
    return render_template('recipes_list.html', recipes=all_recipes)

@app.route('/add_recipe', methods=['GET', 'POST'])
@login_required
def add_recipe():
    if request.method == 'POST':
        recipe_name = request.form['recipe_name']
        instructions = request.form['instructions']
        if not recipe_name:
            flash('菜谱名称不能为空!', 'error'); return redirect(url_for('add_recipe'))
        new_recipe = Recipe(name=recipe_name, instructions=instructions, user_id=current_user.id, image_file='default.jpg')
        db.session.add(new_recipe)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'添加菜谱错误: {e}', 'error'); return redirect(url_for('add_recipe'))
        try:
            if 'recipe_image' in request.files:
                file = request.files['recipe_image']
                if file.filename != '' and allowed_file(file.filename):
                    original_filename = secure_filename(file.filename)
                    ext = original_filename.rsplit('.', 1)[1].lower()
                    image_filename = f"recipe_{new_recipe.id}.{ext}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
                    new_recipe.image_file = image_filename
            ingredient_names = request.form.getlist('ingredient_name[]')
            ingredient_qtys = request.form.getlist('ingredient_qty[]')
            for name, qty in zip(ingredient_names, ingredient_qtys):
                if name: db.session.add(Ingredient(name=name, quantity=qty, recipe_id=new_recipe.id))
            seasoning_names = request.form.getlist('seasoning_name[]')
            seasoning_qtys = request.form.getlist('seasoning_qty[]')
            for name, qty in zip(seasoning_names, seasoning_qtys):
                if name: db.session.add(Seasoning(name=name, quantity=qty, recipe_id=new_recipe.id))
            db.session.commit()
            flash('菜谱添加成功!', 'success')
            return redirect(url_for('recipes_list'))
        except Exception as e:
            db.session.rollback(); flash(f'添加食材出错: {e}', 'error'); return redirect(url_for('add_recipe'))
    return render_template('add_recipe.html')

@app.route('/recipe/<int:recipe_id>')
@login_required
def recipe_detail(recipe_id):
    user_ids = [current_user.id]
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    recipe = Recipe.query.filter(Recipe.id == recipe_id, Recipe.user_id.in_(user_ids)).first()
    if not recipe:
        flash('未找到该菜谱', 'error')
        return redirect(url_for('recipes_list'))
    return render_template('recipe_detail.html', recipe=recipe)

@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.author_id != current_user.id:
        flash('无权删除', 'error'); return redirect(url_for('recipe_detail', recipe_id=recipe_id))
    try:
        db.session.delete(recipe)
        db.session.commit()
        flash('删除成功', 'success')
        return redirect(url_for('recipes_list'))
    except Exception as e:
        db.session.rollback(); flash(f'删除出错: {e}', 'error'); return redirect(url_for('recipe_detail', recipe_id=recipe_id))

@app.route('/recipe/<int:recipe_id>/add_log', methods=['POST'])
@login_required
def add_log(recipe_id):
    user_ids = [current_user.id]
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    recipe = Recipe.query.filter(Recipe.id == recipe_id, Recipe.user_id.in_(user_ids)).first()
    if not recipe: return redirect(url_for('recipes_list'))
    new_log = CookingLog(time_taken=request.form['time_taken'], notes=request.form['notes'], recipe_id=recipe.id)
    db.session.add(new_log); db.session.commit()
    flash('日志已添加', 'success')
    return redirect(url_for('recipe_detail', recipe_id=recipe.id))

@app.route('/what_can_i_make', methods=['GET', 'POST'])
@login_required
def what_can_i_make():
    user_ids = [current_user.id]
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    perfect_matches = []
    partial_matches = []
    pantry_input = ""
    
    if request.method == 'POST':
        pantry_input = request.form['pantry']
        user_pantry_set = {item.strip() for item in re.split(r'[,\s\n]+', pantry_input) if item.strip()}
        if not user_pantry_set:
            flash('请输入食材', 'error'); return render_template('what_can_i_make.html', pantry_input=pantry_input)
        all_recipes = Recipe.query.filter(Recipe.user_id.in_(user_ids)).all()
        for recipe in all_recipes:
            req_ings = {ing.name.strip() for ing in recipe.ingredients}
            if not req_ings: continue
            if req_ings.issubset(user_pantry_set): perfect_matches.append(recipe)
            else:
                missing = req_ings.difference(user_pantry_set)
                if len(missing) < len(req_ings): partial_matches.append((recipe, list(missing)))
    return render_template('what_can_i_make.html', perfect_matches=perfect_matches, partial_matches=partial_matches, pantry_input=pantry_input, has_searched=request.method=='POST')

# --- 7. 情侣绑定路由 ---

@app.route('/partner', methods=['GET'])
@login_required
def partner_page():
    return render_template('partner.html', partner=current_user.partner, invite_code=current_user.invite_code)

@app.route('/partner/generate_code', methods=['POST'])
@login_required
def generate_invite_code():
    if current_user.partner_id or current_user.invite_code: return redirect(url_for('partner_page'))
    while True:
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for i in range(6))
        if not User.query.filter_by(invite_code=code).first(): break
    current_user.invite_code = code; db.session.commit()
    flash(f'邀请码: {code}', 'success')
    return redirect(url_for('partner_page'))

@app.route('/partner/redeem_code', methods=['POST'])
@login_required
def redeem_invite_code():
    code = request.form['invite_code'].strip().upper()
    target = User.query.filter_by(invite_code=code).first()
    if not target or target.id == current_user.id or current_user.partner_id:
        flash('邀请码无效', 'error'); return redirect(url_for('partner_page'))
    target.partner_id = current_user.id; current_user.partner_id = target.id; target.invite_code = None
    db.session.commit()
    flash('绑定成功', 'success')
    return redirect(url_for('partner_page'))

# --- 8. 共享日记路由 ---

@app.route('/journal')
@login_required
def journal():
    if not current_user.partner_id:
        flash('您必须先绑定伴侣才能使用共享日记。', 'error')
        return redirect(url_for('partner_page'))
        
    # 获取年份和月份
    now = datetime.datetime.now()
    try:
        year = int(request.args.get('year', now.year))
        month = int(request.args.get('month', now.month))
    except ValueError:
        year, month = now.year, now.month

    user_ids = [current_user.id, current_user.partner_id]
    # 构造当月查询字符串 YYYY-MM
    month_str = f"{year}-{month:02d}"
    entries = JournalEntry.query.filter(
        JournalEntry.author_id.in_(user_ids),
        JournalEntry.date_str.like(f"{month_str}-%")
    ).all()
    
    calendar_data = {}
    for entry in entries:
        d = entry.date_str
        if d not in calendar_data: calendar_data[d] = {'me': False, 'partner': False, 'me_content': '', 'partner_content': ''}
        if entry.author_id == current_user.id:
            calendar_data[d]['me'] = True; calendar_data[d]['me_content'] = entry.content
        else:
            calendar_data[d]['partner'] = True; calendar_data[d]['partner_content'] = entry.content
            
    cal_matrix = calendar.monthcalendar(year, month)

    return render_template(
        'journal.html', 
        calendar_data=calendar_data,
        partner_name=current_user.partner.username,
        year=year,
        month=month,
        cal_matrix=cal_matrix
    )

@app.route('/journal/add', methods=['POST'])
@login_required
def add_journal_entry():
    if not current_user.partner_id: return jsonify({'status':'error'}), 403
    data = request.json
    date, content = data.get('date'), data.get('content')
    if not date or not content: return jsonify({'status':'error'}), 400
    existing = JournalEntry.query.filter_by(date_str=date, author_id=current_user.id).first()
    try:
        if existing: existing.content = content; msg='更新成功'
        else: db.session.add(JournalEntry(date_str=date, content=content, author_id=current_user.id)); msg='保存成功'
        db.session.commit()
        return jsonify({'status':'success', 'message':msg})
    except Exception as e:
        db.session.rollback()
        if "UNIQUE" in str(e): 
             existing = JournalEntry.query.filter_by(date_str=date, author_id=current_user.id).first()
             if existing: existing.content = content; db.session.commit(); return jsonify({'status':'success'})
        return jsonify({'status':'error'}), 500

# --- 9. 纪念册路由 ---

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
    if not current_user.partner_id: return redirect(url_for('partner_page'))
    if request.method == 'POST':
        new_mem = Memory(title=request.form['title'], content=request.form['content'], location=request.form['location'], author_id=current_user.id, image_file='default.jpg')
        if request.form['memory_date']: new_mem.memory_date = datetime.datetime.strptime(request.form['memory_date'], '%Y-%m-%d').date()
        db.session.add(new_mem); db.session.commit()
        if 'image' in request.files:
             f = request.files['image']
             if f.filename != '' and allowed_file(f.filename):
                 fname = secure_filename(f.filename)
                 ext = fname.rsplit('.', 1)[1].lower()
                 new_mem.image_file = f"memory_{new_mem.id}.{ext}"
                 f.save(os.path.join(app.config['UPLOAD_FOLDER'], new_mem.image_file))
                 db.session.commit()
        flash('回忆已保存', 'success'); return redirect(url_for('memories'))
    return render_template('add_memory.html')

@app.route('/memory/<int:memory_id>')
@login_required
def memory_detail(memory_id):
    user_ids = [current_user.id]
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    mem = Memory.query.filter(Memory.id == memory_id, Memory.author_id.in_(user_ids)).first()
    if not mem: return redirect(url_for('memories'))
    return render_template('memory_detail.html', memory=mem)

@app.route('/memory/<int:memory_id>/delete', methods=['POST'])
@login_required
def delete_memory(memory_id):
    mem = Memory.query.get_or_404(memory_id)
    if mem.author_id != current_user.id: return redirect(url_for('memory_detail', memory_id=memory_id))
    db.session.delete(mem); db.session.commit()
    flash('删除成功', 'success'); return redirect(url_for('memories'))

# --- 10. 愿望清单路由 ---

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
    if not current_user.partner_id: return redirect(url_for('partner_page'))
    db.session.add(WishlistItem(content=request.form['content'], author_id=current_user.id)); db.session.commit()
    flash('愿望已添加', 'success'); return redirect(url_for('wishlist'))

@app.route('/wishlist/toggle/<int:item_id>', methods=['POST'])
@login_required
def toggle_wish(item_id):
    user_ids = [current_user.id]; 
    if current_user.partner_id: user_ids.append(current_user.partner_id)
    item = WishlistItem.query.filter(WishlistItem.id == item_id, WishlistItem.author_id.in_(user_ids)).first()
    if item: item.is_completed = not item.is_completed; db.session.commit()
    return redirect(url_for('wishlist'))

@app.route('/wishlist/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_wish(item_id):
    item = WishlistItem.query.get_or_404(item_id)
    if item.author_id == current_user.id: db.session.delete(item); db.session.commit()
    return redirect(url_for('wishlist'))

# --- 启动器 ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)