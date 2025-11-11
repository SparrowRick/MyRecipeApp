import os
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import string # NEW: 用于生成邀请码
import secrets # NEW: 用于生成邀请码
# NEW: 导入 Migrate
from flask_migrate import Migrate

# --- 配置 ---
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'recipes.db')
# ... (其他 app.config 不变) ...
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'a_very_secret_key_change_this_for_production'
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)
# NEW: 初始化 Migrate
migrate = Migrate(app, db)

# NEW: 配置 Flask-Login
# ... (login_manager 的所有配置不变) ...
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录以访问此页面。'
login_manager.login_message_category = 'error'


# --- 数据库模型 (Models) ---

# NEW: 用户模型
# ... (User 模型 和 load_user 函数不变) ...
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    
    recipes = db.relationship('Recipe', backref='author', lazy=True)
    # --- NEW: 情侣关联 ---
    # 邀请码 (一次性, 6位)
    invite_code = db.Column(db.String(6), unique=True, nullable=True) 
    # 指向伴侣的 User.id
    partner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) 
    
    # 建立一个“虚拟”的 partner 关系, 方便查询
    # (这是一个复杂的关系: 1对1, 且指向自己)
    partner = db.relationship(
        'User', 
        remote_side=[id], # 远程的 ID
        primaryjoin=partner_id == id, # 本地的 partner_id == 远程的 id
        uselist=False # 关系只返回一个人, 而不是列表
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# 菜谱表 (MODIFIED: user_id 允许为空)
class Recipe(db.Model):
    # ... (id, name, instructions, image_file 字段不变) ...
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) 
    instructions = db.Column(db.Text, nullable=True) 
    image_file = db.Column(db.String(100), nullable=False, default='default.jpg')
    
    # NEW: 外键, 关联到 User 表
    # CRITICAL CHANGE: nullable=False 变为 nullable=True
    # 这允许您的旧菜谱在迁移过程中暂时没有主人
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # ... (relationships 不变) ...
    ingredients = db.relationship('Ingredient', backref='recipe', lazy=True, cascade="all, delete-orphan")
    seasonings = db.relationship('Seasoning', backref='recipe', lazy=True, cascade="all, delete-orphan")
    logs = db.relationship('CookingLog', backref='recipe', lazy=True, cascade="all, delete-orphan")

# ... (Ingredient, Seasoning, CookingLog 模型不变) ...
class Ingredient(db.Model):
# ... (existing code) ...
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50), nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)

class Seasoning(db.Model):
# ... (existing code) ...
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50), nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)

class CookingLog(db.Model):
# ... (existing code) ...
    id = db.Column(db.Integer, primary_key=True)
    date_cooked = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    time_taken = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)


def allowed_file(filename):
# ... (existing code) ...
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# --- NEW: 用户认证路由 ---
# ... (login, register, logout 路由不变) ...
@app.route('/login', methods=['GET', 'POST'])
def login():
# ... (existing code) ...
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user is None or not user.check_password(password):
            flash('无效的用户名或密码。', 'error')
            return redirect(url_for('login'))
        
        login_user(user, remember=True)
        
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('index')
            
        return redirect(next_page)
        
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
# ... (existing code) ...
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if not username or not password:
            flash('用户名和密码不能为空!', 'error')
            return redirect(url_for('register'))
            
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('用户名已存在，请选择其他用户名。', 'error')
            return redirect(url_for('register'))
        
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        
        try:
            db.session.commit()
            flash('注册成功！请登录。', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'注册时发生错误: {e}', 'error')
            
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
# ... (existing code) ...
    logout_user()
    flash('您已成功退出。', 'success')
    return redirect(url_for('login'))


# --- (MODIFIED): 保护和修改所有旧路由 ---
# ... (index, add_recipe, recipe_detail, delete_recipe, add_log, what_can_i_make 路由不变) ...
# ... (除了 'what_can_i_make' 里的 import re) ...

@app.route('/')
@login_required
def index():
# ... (existing code) ...
    all_recipes = Recipe.query.filter_by(user_id=current_user.id).all()
    return render_template('index.html', recipes=all_recipes)

@app.route('/add_recipe', methods=['GET', 'POST'])
@login_required
def add_recipe():
    if request.method == 'POST':
        recipe_name = request.form['recipe_name']
        instructions = request.form['instructions']

        if not recipe_name:
            flash('菜谱名称不能为空!', 'error')
            return redirect(url_for('add_recipe'))
        
        # 1. 创建对象
        new_recipe = Recipe(
            name=recipe_name,
            instructions=instructions,
            user_id=current_user.id,
            image_file='default.jpg' # 假设默认
        )
        
        # 2. 添加到 Session
        db.session.add(new_recipe)

        try:
            # 3. 第一次提交 (关键!)
            # 这会生成 new_recipe.id
            # 并且会触发 UNIQUE 约束检查
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            if "UNIQUE constraint failed" in str(e):
                 # 我们在 V2.1 中修复了这里的逻辑，确保它能正确处理 UNIQUE
                 flash(f'您已经有一道叫 "{recipe_name}" 的菜了。', 'error')
            else:
                 flash(f'添加菜谱时发生错误: {e}', 'error')
            return redirect(url_for('add_recipe'))

        # --- 如果执行到这里, new_recipe.id 100% 存在 ---

        try:
            # 4. 处理图片 (现在是 "更新" 操作)
            if 'recipe_image' in request.files:
                file = request.files['recipe_image']
                if file.filename != '' and allowed_file(file.filename):
                    original_filename = secure_filename(file.filename)
                    ext = original_filename.rsplit('.', 1)[1].lower()
                    image_filename = f"recipe_{new_recipe.id}.{ext}" # 使用已生成的 ID
                    
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                    file.save(file_path)
                    
                    # 更新对象
                    new_recipe.image_file = image_filename
            
            # 5. 处理食材 (使用已生成的 ID)
            ingredient_names = request.form.getlist('ingredient_name[]')
            ingredient_qtys = request.form.getlist('ingredient_qty[]')
            for name, qty in zip(ingredient_names, ingredient_qtys):
                if name:
                    db.session.add(Ingredient(name=name, quantity=qty, recipe_id=new_recipe.id))
            
            # 6. 处理调料 (使用已生成的 ID)
            seasoning_names = request.form.getlist('seasoning_name[]')
            seasoning_qtys = request.form.getlist('seasoning_qty[]')
            for name, qty in zip(seasoning_names, seasoning_qtys):
                if name:
                    db.session.add(Seasoning(name=name, quantity=qty, recipe_id=new_recipe.id))

            # 7. 第二次提交 (提交图片更新、食材、调料)
            db.session.commit()
            flash('菜谱添加成功!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            # 如果第 4-7 步失败, 回滚
            db.session.rollback()
            flash(f'添加食材或图片时出错: {e}', 'error')
            # (此时可能有一个没有食材的菜谱留在了数据库中, 但这比崩溃要好)
            return redirect(url_for('add_recipe'))
            
    return render_template('add_recipe.html')

@app.route('/recipe/<int:recipe_id>')
@login_required
def recipe_detail(recipe_id):
# ... (existing code) ...
    recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first()
    if not recipe:
        abort(404)
        
    return render_template('recipe_detail.html', recipe=recipe)

@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
def delete_recipe(recipe_id):
# ... (existing code) ...
    recipe_to_delete = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first()
    if not recipe_to_delete:
        abort(404)

    image_filename = recipe_to_delete.image_file
# ... (existing code) ...
    if image_filename != 'default.jpg':
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            print(f"警告: 无法删除图片 {image_path}. 错误: {e}")
            pass 
    
    try:
        db.session.delete(recipe_to_delete)
# ... (existing code) ...
        db.session.commit()
        flash(f'菜谱 "{recipe_to_delete.name}" 已被成功删除。', 'success')
        return redirect(url_for('index'))
    except Exception as e:
# ... (existing code) ...
        db.session.rollback()
        flash(f'删除菜谱时出错: {e}', 'error')
        return redirect(url_for('recipe_detail', recipe_id=recipe.id))

@app.route('/recipe/<int:recipe_id>/add_log', methods=['POST'])
@login_required
def add_log(recipe_id):
# ... (existing code) ...
    recipe = Recipe.query.filter_by(id=recipe_id, user_id=current_user.id).first()
    if not recipe:
        abort(404)
        
    time_taken = request.form['time_taken']
# ... (existing code) ...
    notes = request.form['notes']
    
    new_log = CookingLog(time_taken=time_taken, notes=notes, recipe_id=recipe.id)
    db.session.add(new_log)
    db.session.commit()
    
    flash('烹饪日志已添加!', 'success')
    return redirect(url_for('recipe_detail', recipe_id=recipe.id))

@app.route('/what_can_i_make', methods=['GET', 'POST'])
@login_required
def what_can_i_make():
# ... (existing code) ...
    perfect_matches = []
    partial_matches = []
    pantry_input = "" 
    import re # 确保导入 re

    if request.method == 'POST':
# ... (existing code) ...
        pantry_input = request.form['pantry']
        user_pantry_list = re.split(r'[,\s\n]+', pantry_input)
        user_pantry_set = {item.strip() for item in user_pantry_list if item.strip()}

        if not user_pantry_set:
# ... (existing code) ...
            flash('请输入您拥有的食材！', 'error')
            return render_template('what_can_i_make.html', pantry_input=pantry_input)

        all_recipes = Recipe.query.filter_by(user_id=current_user.id).all()
        
        for recipe in all_recipes:
# ... (existing code) ...
            required_ingredients_set = {ing.name.strip() for ing in recipe.ingredients}
            if not required_ingredients_set:
                continue
            
            if required_ingredients_set.issubset(user_pantry_set):
# ... (existing code) ...
                perfect_matches.append(recipe)
            else:
                missing_ingredients = required_ingredients_set.difference(user_pantry_set)
                if len(missing_ingredients) < len(required_ingredients_set):
# ... (existing code) ...
                    partial_matches.append((recipe, list(missing_ingredients)))

    return render_template('what_can_i_make.html', 
# ... (existing code) ...
                           perfect_matches=perfect_matches, 
                           partial_matches=partial_matches,
                           pantry_input=pantry_input,
                           has_searched=request.method == 'POST')
@app.route('/partner', methods=['GET'])
@login_required
def partner_page():
    # 查找您的伴侣 (通过 User.partner 关系)
    partner = current_user.partner
    return render_template('partner.html', partner=partner, invite_code=current_user.invite_code)

@app.route('/partner/generate_code', methods=['POST'])
@login_required
def generate_invite_code():
    # 如果已有伴侣, 不允许生成
    if current_user.partner_id:
        flash('您已经绑定了伴侣。', 'error')
        return redirect(url_for('partner_page'))
    
    # 如果已有邀请码, 不重新生成
    if current_user.invite_code:
        flash(f'您已有一个邀请码: {current_user.invite_code}', 'info')
        return redirect(url_for('partner_page'))

    # 生成一个6位的、不重复的 字母+数字 邀请码
    while True:
        alphabet = string.ascii_uppercase + string.digits
        new_code = ''.join(secrets.choice(alphabet) for i in range(6))
        # 检查这个码是否已存在
        existing_code = User.query.filter_by(invite_code=new_code).first()
        if not existing_code:
            break # 找到了唯一的码
    
    current_user.invite_code = new_code
    try:
        db.session.commit()
        flash(f'您的专属邀请码是: {new_code}。请让您的伴侣用它来绑定。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'生成邀请码时出错: {e}', 'error')
        
    return redirect(url_for('partner_page'))

@app.route('/partner/redeem_code', methods=['POST'])
@login_required
def redeem_invite_code():
    code_to_redeem = request.form['invite_code'].strip().upper()
    
    # 1. 检查自己
    if not code_to_redeem:
        flash('请输入邀请码。', 'error')
        return redirect(url_for('partner_page'))
    if current_user.partner_id:
        flash('您已经绑定了伴侣。', 'error')
        return redirect(url_for('partner_page'))
        
    # 2. 查找邀请码
    user_with_code = User.query.filter_by(invite_code=code_to_redeem).first()
    
    if not user_with_code:
        flash('邀请码无效或不存在。', 'error')
        return redirect(url_for('partner_page'))
        
    # 3. 不能自己邀请自己
    if user_with_code.id == current_user.id:
        flash('您不能和自己绑定！', 'error')
        return redirect(url_for('partner_page'))

    # 4. (成功) 互相绑定
    try:
        # 绑定 A -> B
        user_with_code.partner_id = current_user.id
        # 绑定 B -> A
        current_user.partner_id = user_with_code.id
        # 消耗掉邀请码 (设为 None)
        user_with_code.invite_code = None
        
        db.session.commit()
        flash(f'成功！您已和 {user_with_code.username} 绑定为情侣。', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'绑定时发生错误: {e}', 'error')

    return redirect(url_for('partner_page'))

# --- 启动器 ---
if __name__ == '__main__':
    # ... (db.create_all() 和 app.run() 不变) ...
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)