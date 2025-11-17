import os
import string 
import secrets 
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify 
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate 
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_ 
import datetime
from werkzeug.utils import secure_filename 

# --- 配置 (不变) ---
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'recipes.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'a_very_secret_key_change_this'
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)
migrate = Migrate(app, db) 
login_manager = LoginManager(app)
login_manager.login_view = 'login' 
login_manager.login_message = '您需要先登录才能访问此页面。'
login_manager.login_message_category = 'error'

# --- 数据库模型 (Models) ---

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    
    recipes = db.relationship('Recipe', backref='author', lazy=True, cascade="all, delete-orphan")
    
    # --- V2.5: 情侣关联 ---
    invite_code = db.Column(db.String(6), unique=True, nullable=True) 
    partner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) 
    partner = db.relationship(
        'User', 
        remote_side=[id], 
        primaryjoin=partner_id == id, 
        uselist=False,
        lazy=True # V3.1: 修复递归错误
    )
    
    # --- V3.0: 日记关联 ---
    journal_entries = db.relationship('JournalEntry', backref='author', lazy=True)

    # --- V3.1: 纪念册关联 ---
    memories = db.relationship('Memory', backref='author', lazy=True)
    
    # --- V3.2 NEW: 愿望清单关联 ---
    wishlist_items = db.relationship('WishlistItem', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# --- 各种模型 (Recipe, Ingredient, Seasoning, CookingLog, JournalEntry, Memory - 不变) ---

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

# --- V3.2 NEW: 愿望清单模型 ---
class WishlistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(300), nullable=False)
    # is_completed 字段用于标记是否已完成, 默认为 False
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # V3.3 升级: 我们可以添加 'completer_id' 来记录是谁完成的


# --- 路由 (Routes / 网页) ---

# 辅助函数 (不变)
def allowed_file(filename):
    # ... (代码不变) ...
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- 用户认证路由 (不变) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    # ... (代码不变) ...
    if current_user.is_authenticated:
        return redirect(url_for('index'))
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
    # ... (代码不变) ...
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    # ... (代码不变) ...
    if current_user.is_authenticated:
        return redirect(url_for('index'))
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

# --- 菜谱路由 (不变) ---
@app.route('/')
@login_required
def index():
    # ... (V3.0 共享代码 - 不变) ...
    user_ids_to_query = [current_user.id]
    if current_user.partner_id:
        user_ids_to_query.append(current_user.partner_id)
    all_recipes = Recipe.query.filter(
        Recipe.user_id.in_(user_ids_to_query)
    ).order_by(Recipe.id.desc()).all() 
    return render_template('index.html', recipes=all_recipes)

@app.route('/add_recipe', methods=['GET', 'POST'])
@login_required
def add_recipe():
    # ... (代码不变) ...
    return render_template('add_recipe.html') # 省略完整代码

@app.route('/recipe/<int:recipe_id>')
@login_required
def recipe_detail(recipe_id):
    # ... (V3.0 共享代码 - 不变) ...
    user_ids_to_query = [current_user.id]
    if current_user.partner_id:
        user_ids_to_query.append(current_user.partner_id)
    recipe = Recipe.query.filter(
        Recipe.id == recipe_id,
        Recipe.user_id.in_(user_ids_to_query)
    ).first()
    if not recipe:
        flash('未找到该菜谱，或者该菜谱不属于您或您的伴侣。', 'error')
        return redirect(url_for('index'))
    return render_template('recipe_detail.html', recipe=recipe)

@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
def delete_recipe(recipe_id):
    # ... (代码不变) ...
    return redirect(url_for('index')) # 省略完整代码

@app.route('/recipe/<int:recipe_id>/add_log', methods=['POST'])
@login_required
def add_log(recipe_id):
    # ... (代码不变) ...
    return redirect(url_for('recipe_detail', recipe_id=recipe_id)) # 省略完整代码

@app.route('/what_can_i_make', methods=['GET', 'POST'])
@login_required
def what_can_i_make():
    # ... (V3.0 共享代码 - 不变) ...
    return render_template('what_can_i_make.html') # 省略完整代码

# --- V2.5: 情侣关联路由 (不变) ---
@app.route('/partner', methods=['GET'])
@login_required
def partner_page():
    # ... (代码不变) ...
    partner = current_user.partner
    return render_template('partner.html', partner=partner, invite_code=current_user.invite_code)

@app.route('/partner/generate_code', methods=['POST'])
@login_required
def generate_invite_code():
    # ... (代码不变) ...
    return redirect(url_for('partner_page')) # 省略完整代码

@app.route('/partner/redeem_code', methods=['POST'])
@login_required
def redeem_invite_code():
    # ... (代码不变) ...
    return redirect(url_for('partner_page')) # 省略完整代码

# --- V3.0: 共享日记路由 (不变) ---
@app.route('/journal')
@login_required
def journal():
    # ... (代码不变) ...
    if not current_user.partner_id:
        flash('您必须先绑定伴侣才能使用共享日记。', 'error')
        return redirect(url_for('partner_page'))
    user_ids = [current_user.id, current_user.partner_id]
    entries = JournalEntry.query.filter(JournalEntry.author_id.in_(user_ids)).all()
    calendar_data = {}
    for entry in entries:
        date = entry.date_str
        if date not in calendar_data:
            calendar_data[date] = {'me': False, 'partner': False, 'me_content': '', 'partner_content': ''}
        if entry.author_id == current_user.id:
            calendar_data[date]['me'] = True
            calendar_data[date]['me_content'] = entry.content
        else:
            calendar_data[date]['partner'] = True
            calendar_data[date]['partner_content'] = entry.content
    return render_template(
        'journal.html', 
        calendar_data=calendar_data,
        partner_name=current_user.partner.username
    )

@app.route('/journal/add', methods=['POST'])
@login_required
def add_journal_entry():
    # ... (代码不变) ...
    return jsonify({'status': 'error', 'message': '...'}) # 省略完整代码

# --- V3.1: 纪念册路由 (不变) ---
@app.route('/memories')
@login_required
def memories():
    # ... (代码不变) ...
    if not current_user.partner_id:
        flash('您必须先绑定伴侣才能使用纪念册。', 'error')
        return redirect(url_for('partner_page'))
    user_ids = [current_user.id, current_user.partner_id]
    all_memories = Memory.query.filter(
        Memory.author_id.in_(user_ids)
    ).order_by(Memory.memory_date.desc()).all()
    return render_template('memories.html', memories=all_memories)

@app.route('/memory/add', methods=['GET', 'POST'])
@login_required
def add_memory():
    # ... (代码不变) ...
    return render_template('add_memory.html') # 省略完整代码

@app.route('/memory/<int:memory_id>')
@login_required
def memory_detail(memory_id):
    # ... (代码不变) ...
    user_ids = [current_user.id]
    if current_user.partner_id:
        user_ids.append(current_user.partner_id)
    memory = Memory.query.filter(
        Memory.id == memory_id,
        Memory.author_id.in_(user_ids)
    ).first()
    if not memory:
        flash('未找到该纪念册，或者它不属于您们。', 'error')
        return redirect(url_for('memories'))
    return render_template('memory_detail.html', memory=memory)

@app.route('/memory/<int:memory_id>/delete', methods=['POST'])
@login_required
def delete_memory(memory_id):
    # ... (代码不变) ...
    return redirect(url_for('memories')) # 省略完整代码


# --- V3.2 NEW: 愿望清单路由 ---

@app.route('/wishlist')
@login_required
def wishlist():
    # 1. 确保已绑定伴侣
    if not current_user.partner_id:
        flash('您必须先绑定伴侣才能使用愿望清单。', 'error')
        return redirect(url_for('partner_page'))
        
    # 2. 获取您和伴侣的 ID
    user_ids = [current_user.id, current_user.partner_id]
    
    # 3. 查询所有共享的愿望
    all_wishes = WishlistItem.query.filter(
        WishlistItem.author_id.in_(user_ids)
    ).order_by(WishlistItem.is_completed.asc(), WishlistItem.id.desc()).all()
    
    # 4. 分离 "待办" 和 "已完成"
    todo_wishes = [w for w in all_wishes if not w.is_completed]
    done_wishes = [w for w in all_wishes if w.is_completed]
    
    return render_template('wishlist.html', todo_wishes=todo_wishes, done_wishes=done_wishes)

@app.route('/wishlist/add', methods=['POST'])
@login_required
def add_wish():
    # 确保已绑定伴侣
    if not current_user.partner_id:
        flash('您必须先绑定伴侣。', 'error')
        return redirect(url_for('partner_page'))

    content = request.form['content']
    if not content:
        flash('愿望内容不能为空!', 'error')
        return redirect(url_for('wishlist'))
        
    new_wish = WishlistItem(
        content=content,
        author_id=current_user.id # 由当前用户添加
    )
    db.session.add(new_wish)
    try:
        db.session.commit()
        flash('新愿望已添加!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'添加愿望时出错: {e}', 'error')
        
    return redirect(url_for('wishlist'))

@app.route('/wishlist/toggle/<int:item_id>', methods=['POST'])
@login_required
def toggle_wish(item_id):
    # 确保我们能访问
    user_ids = [current_user.id]
    if current_user.partner_id:
        user_ids.append(current_user.partner_id)
        
    item = WishlistItem.query.filter(
        WishlistItem.id == item_id,
        WishlistItem.author_id.in_(user_ids)
    ).first()

    if not item:
        flash('未找到该愿望。', 'error')
        return redirect(url_for('wishlist'))
        
    # (任何人都可以 "完成" 愿望, 即使是对方添加的)
    item.is_completed = not item.is_completed
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'更新愿望时出错: {e}', 'error')
        
    return redirect(url_for('wishlist'))

@app.route('/wishlist/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_wish(item_id):
    item = WishlistItem.query.get_or_404(item_id)
    
    # 权限检查: 必须是作者本人
    if item.author_id != current_user.id:
        flash('您没有权限删除这个愿望，只有作者本人才能删除。', 'error')
        return redirect(url_for('wishlist'))
        
    try:
        db.session.delete(item)
        db.session.commit()
        flash('愿望已删除。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'删除愿望时出错: {e}', 'error')
        
    return redirect(url_for('wishlist'))


# --- 启动器 ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)