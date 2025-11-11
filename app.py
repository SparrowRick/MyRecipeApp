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
from werkzeug.utils import secure_filename # NEW: 确保导入 secure_filename

# --- 配置 ---
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
        lazy=True 
    )
    
    # --- V3.0: 日记关联 ---
    journal_entries = db.relationship('JournalEntry', backref='author', lazy=True)

    # --- V3.1 NEW: 纪念册关联 ---
    memories = db.relationship('Memory', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# 菜谱表 (不变)
class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True) 
    instructions = db.Column(db.Text, nullable=True)
    image_file = db.Column(db.String(100), nullable=False, default='default.jpg')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) 
    ingredients = db.relationship('Ingredient', backref='recipe', lazy=True, cascade="all, delete-orphan")
    seasonings = db.relationship('Seasoning', backref='recipe', lazy=True, cascade="all, delete-orphan")
    logs = db.relationship('CookingLog', backref='recipe', lazy=True, cascade="all, delete-orphan")

# 食材表 (不变)
class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50), nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)

# 调料表 (不变)
class Seasoning(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50), nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)

# 烹饪日志表 (不变)
class CookingLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_cooked = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    time_taken = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)

# V3.0 日记模型 (不变)
class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_str = db.Column(db.String(10), nullable=False) 
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('date_str', 'author_id', name='_date_author_uc'),)

# --- V3.1 NEW: 纪念册模型 ---
class Memory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    # 我们使用 db.Date 而不是 DateTime
    memory_date = db.Column(db.Date, nullable=True) 
    location = db.Column(db.String(100), nullable=True) # 地点
    content = db.Column(db.Text, nullable=False)
    image_file = db.Column(db.String(100), nullable=False, default='default.jpg') # 使用和菜谱一样的默认图
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


# --- 路由 (Routes / 网页) ---

# 辅助函数 (不变)
def allowed_file(filename):
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

# --- 菜谱路由 (V3.0 - 共享 - 不变) ---

@app.route('/')
@login_required
def index():
    # ... (代码不变) ...
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
    # ... (代码不变, V2.2 Bug修复版) ...
    if request.method == 'POST':
        recipe_name = request.form['recipe_name']
        instructions = request.form['instructions']

        if not recipe_name:
            flash('菜谱名称不能为空!', 'error')
            return redirect(url_for('add_recipe'))
        
        new_recipe = Recipe(
            name=recipe_name,
            instructions=instructions,
            user_id=current_user.id, 
            image_file='default.jpg' 
        )
        db.session.add(new_recipe)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            if "UNIQUE constraint failed" in str(e):
                 existing = Recipe.query.filter_by(name=recipe_name).first()
                 if existing and (existing.user_id == current_user.id or existing.user_id == current_user.partner_id):
                     flash(f'您或您的伴侣已经有一道叫 "{recipe_name}" 的菜了。', 'error')
                 else:
                     flash(f'菜谱名称 "{recipe_name}" 已被他人使用。', 'error')
            else:
                 flash(f'添加菜谱时发生错误: {e}', 'error')
            return redirect(url_for('add_recipe'))

        try:
            if 'recipe_image' in request.files:
                file = request.files['recipe_image']
                if file.filename != '' and allowed_file(file.filename):
                    original_filename = secure_filename(file.filename)
                    ext = original_filename.rsplit('.', 1)[1].lower()
                    image_filename = f"recipe_{new_recipe.id}.{ext}" 
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                    file.save(file_path)
                    new_recipe.image_file = image_filename
            
            ingredient_names = request.form.getlist('ingredient_name[]')
            ingredient_qtys = request.form.getlist('ingredient_qty[]')
            for name, qty in zip(ingredient_names, ingredient_qtys):
                if name:
                    db.session.add(Ingredient(name=name, quantity=qty, recipe_id=new_recipe.id))
            
            seasoning_names = request.form.getlist('seasoning_name[]')
            seasoning_qtys = request.form.getlist('seasoning_qty[]')
            for name, qty in zip(seasoning_names, seasoning_qtys):
                if name:
                    db.session.add(Seasoning(name=name, quantity=qty, recipe_id=new_recipe.id))
            db.session.commit()
            flash('菜谱添加成功!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'添加食材或图片时出错: {e}', 'error')
            return redirect(url_for('add_recipe'))
    return render_template('add_recipe.html')

@app.route('/recipe/<int:recipe_id>')
@login_required
def recipe_detail(recipe_id):
    # ... (代码不变) ...
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
    recipe_to_delete = Recipe.query.get_or_404(recipe_id)
    if recipe_to_delete.author_id != current_user.id:
        flash('您没有权限删除这道菜谱，只有作者本人才能删除。', 'error')
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))
    image_filename = recipe_to_delete.image_file
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
        db.session.commit()
        flash(f'菜谱 "{recipe_to_delete.name}" 已被成功删除。', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        flash(f'删除菜谱时出错: {e}', 'error')
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))

@app.route('/recipe/<int:recipe_id>/add_log', methods=['POST'])
@login_required
def add_log(recipe_id):
    # ... (代码不变) ...
    user_ids_to_query = [current_user.id]
    if current_user.partner_id:
        user_ids_to_query.append(current_user.partner_id)
    recipe = Recipe.query.filter(
        Recipe.id == recipe_id,
        Recipe.user_id.in_(user_ids_to_query)
    ).first()
    if not recipe:
        flash('未找到该菜谱。', 'error')
        return redirect(url_for('index'))
    time_taken = request.form['time_taken']
    notes = request.form['notes']
    new_log = CookingLog(time_taken=time_taken, notes=notes, recipe_id=recipe.id)
    db.session.add(new_log)
    db.session.commit()
    flash('烹饪日志已添加!', 'success')
    return redirect(url_for('recipe_detail', recipe_id=recipe_id))

@app.route('/what_can_i_make', methods=['GET', 'POST'])
@login_required
def what_can_i_make():
    # ... (代码不变) ...
    user_ids_to_query = [current_user.id]
    if current_user.partner_id:
        user_ids_to_query.append(current_user.partner_id)
    perfect_matches = []
    partial_matches = []
    pantry_input = "" 
    import re
    if request.method == 'POST':
        pantry_input = request.form['pantry']
        user_pantry_list = re.split(r'[,\s\n]+', pantry_input)
        user_pantry_set = {item.strip() for item in user_pantry_list if item.strip()}
        if not user_pantry_set:
            flash('请输入您拥有的食材！', 'error')
            return render_template('what_can_i_make.html', pantry_input=pantry_input)
        all_recipes = Recipe.query.filter(Recipe.user_id.in_(user_ids_to_query)).all()
        for recipe in all_recipes:
            required_ingredients_set = {ing.name.strip() for ing in recipe.ingredients}
            if not required_ingredients_set:
                continue
            if required_ingredients_set.issubset(user_pantry_set):
                perfect_matches.append(recipe)
            else:
                missing_ingredients = required_ingredients_set.difference(user_pantry_set)
                if len(missing_ingredients) < len(required_ingredients_set):
                    partial_matches.append((recipe, list(missing_ingredients)))
    return render_template('what_can_i_make.html', 
                           perfect_matches=perfect_matches, 
                           partial_matches=partial_matches,
                           pantry_input=pantry_input,
                           has_searched=request.method == 'POST') 

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
    if current_user.partner_id:
        flash('您已经绑定了伴侣。', 'error')
        return redirect(url_for('partner_page'))
    if current_user.invite_code:
        flash(f'您已有一个邀请码: {current_user.invite_code}', 'info')
        return redirect(url_for('partner_page'))
    while True:
        alphabet = string.ascii_uppercase + string.digits
        new_code = ''.join(secrets.choice(alphabet) for i in range(6))
        existing_code = User.query.filter_by(invite_code=new_code).first()
        if not existing_code:
            break 
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
    # ... (代码不变) ...
    code_to_redeem = request.form['invite_code'].strip().upper()
    if not code_to_redeem:
        flash('请输入邀请码。', 'error')
        return redirect(url_for('partner_page'))
    if current_user.partner_id:
        flash('您已经绑定了伴侣。', 'error')
        return redirect(url_for('partner_page'))
    user_with_code = User.query.filter_by(invite_code=code_to_redeem).first()
    if not user_with_code:
        flash('邀请码无效或不存在。', 'error')
        return redirect(url_for('partner_page'))
    if user_with_code.id == current_user.id:
        flash('您不能和自己绑定！', 'error')
        return redirect(url_for('partner_page'))
    try:
        user_with_code.partner_id = current_user.id
        current_user.partner_id = user_with_code.id
        user_with_code.invite_code = None
        db.session.commit()
        flash(f'成功！您已和 {user_with_code.username} 绑定为情侣。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'绑定时发生错误: {e}', 'error')
    return redirect(url_for('partner_page'))

# --- V3.0: 共享日记路由 (不变) ---

@app.route('/journal')
@login_required
def journal():
    # ... (代码不变) ...
    if not current_user.partner_id:
        flash('您必须先绑定伴侣才能使用共享日记。', 'error')
        return redirect(url_for('partner_page'))
    user_ids = [current_user.id, current_user.partner_id]
    entries = JournalEntry.query.filter(
        JournalEntry.author_id.in_(user_ids)
    ).all()
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
    if not current_user.partner_id:
        return jsonify({'status': 'error', 'message': '未绑定伴侣'}), 403
    data = request.json
    date_str = data.get('date')
    content = data.get('content')
    if not date_str or not content:
        return jsonify({'status': 'error', 'message': '日期或内容不能为空'}), 400
    existing_entry = JournalEntry.query.filter_by(
        date_str=date_str, 
        author_id=current_user.id
    ).first()
    try:
        if existing_entry:
            existing_entry.content = content
            db.session.commit()
            return jsonify({'status': 'success', 'message': '日记已更新'})
        else:
            new_entry = JournalEntry(
                date_str=date_str,
                content=content,
                author_id=current_user.id
            )
            db.session.add(new_entry)
            db.session.commit()
            return jsonify({'status': 'success', 'message': '日记已保存'})
    except Exception as e:
        db.session.rollback()
        if "UNIQUE constraint failed" in str(e):
             existing_entry = JournalEntry.query.filter_by(date_str=date_str, author_id=current_user.id).first()
             if existing_entry:
                 existing_entry.content = content
                 db.session.commit()
                 return jsonify({'status': 'success', 'message': '日记已更新 (覆盖旧条目)'})
        return jsonify({'status': 'error', 'message': str(e)}), 500


# --- V3.1 NEW: 纪念册路由 ---

@app.route('/memories')
@login_required
def memories():
    # 1. 确保已绑定伴侣
    if not current_user.partner_id:
        flash('您必须先绑定伴侣才能使用纪念册。', 'error')
        return redirect(url_for('partner_page'))
        
    # 2. 获取您和伴侣的 ID
    user_ids = [current_user.id, current_user.partner_id]
    
    # 3. 查询所有共享的纪念册, 按日期倒序
    all_memories = Memory.query.filter(
        Memory.author_id.in_(user_ids)
    ).order_by(Memory.memory_date.desc()).all()
    
    return render_template('memories.html', memories=all_memories)

@app.route('/memory/add', methods=['GET', 'POST'])
@login_required
def add_memory():
    # 确保已绑定伴侣
    if not current_user.partner_id:
        flash('您必须先绑定伴侣才能添加纪念册。', 'error')
        return redirect(url_for('partner_page'))

    if request.method == 'POST':
        title = request.form['title']
        # HTML 日期输入框 'YYYY-MM-DD'
        date_str = request.form['memory_date']
        location = request.form['location']
        content = request.form['content']

        if not title or not content:
            flash('标题和内容不能为空!', 'error')
            return redirect(url_for('add_memory'))
        
        # 转换日期
        memory_date_obj = None
        if date_str:
            try:
                memory_date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('日期格式不正确, 请使用 YYYY-MM-DD 格式。', 'error')
                return redirect(url_for('add_memory'))
        
        new_memory = Memory(
            title=title,
            memory_date=memory_date_obj,
            location=location,
            content=content,
            author_id=current_user.id,
            image_file='default.jpg' # 默认
        )
        db.session.add(new_memory)
        
        try:
            # 第一次提交, 获取 ID
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'添加纪念册时发生错误: {e}', 'error')
            return redirect(url_for('add_memory'))

        # 第二次提交, 处理图片 (和 add_recipe 完全一样)
        try:
            if 'image' in request.files:
                file = request.files['image']
                if file.filename != '' and allowed_file(file.filename):
                    original_filename = secure_filename(file.filename)
                    ext = original_filename.rsplit('.', 1)[1].lower()
                    # 我们用 'memory_' 前缀来区分图片
                    image_filename = f"memory_{new_memory.id}.{ext}" 
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                    file.save(file_path)
                    new_memory.image_file = image_filename
                    db.session.commit() # 提交图片更新
            
            flash('纪念册添加成功!', 'success')
            return redirect(url_for('memories'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'处理纪念册图片时出错: {e}', 'error')
            return redirect(url_for('add_memory'))
            
    return render_template('add_memory.html')

@app.route('/memory/<int:memory_id>')
@login_required
def memory_detail(memory_id):
    # 确保我们能访问
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
    # 找到纪念册
    memory_to_delete = Memory.query.get_or_404(memory_id)
    
    # 权限检查: 必须是作者本人
    if memory_to_delete.author_id != current_user.id:
        flash('您没有权限删除这篇纪念册，只有作者本人才能删除。', 'error')
        return redirect(url_for('memory_detail', memory_id=memory_id))
        
    # 删除图片
    image_filename = memory_to_delete.image_file
    if image_filename != 'default.jpg':
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            print(f"警告: 无法删除图片 {image_path}. 错误: {e}")
            pass 
    
    try:
        db.session.delete(memory_to_delete)
        db.session.commit()
        flash(f'纪念册 "{memory_to_delete.title}" 已被成功删除。', 'success')
        return redirect(url_for('memories'))
    except Exception as e:
        db.session.rollback()
        flash(f'删除纪念册时出错: {e}', 'error')
        return redirect(url_for('memory_detail', memory_id=memory_id))


# --- 启动器 ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)