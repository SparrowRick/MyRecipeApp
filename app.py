import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import datetime
from werkzeug.utils import secure_filename 
import re

# --- 配置 (不变) ---
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'recipes.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'a_very_secret_key_change_this' 
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- 数据库模型 (Models) ---

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    instructions = db.Column(db.Text, nullable=True) 
    image_file = db.Column(db.String(100), nullable=False, default='default.jpg')
    
    # 关系: 一道菜谱可以有多种食材
    ingredients = db.relationship('Ingredient', backref='recipe', lazy=True, cascade="all, delete-orphan")
    # NEW: 添加调料关系
    seasonings = db.relationship('Seasoning', backref='recipe', lazy=True, cascade="all, delete-orphan")
    
    # 关系: 一道菜谱可以有多个烹饪日志
    logs = db.relationship('CookingLog', backref='recipe', lazy=True, cascade="all, delete-orphan")

# 食材表 (不变)
class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50), nullable=True) # 比如 "2个" 或 "500克"
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)

# NEW: 调料表 (Ingredient的复制版)
class Seasoning(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50), nullable=True) # 比如 "少许" 或 "3勺"
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)

# 烹饪日志表 (不变)
class CookingLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_cooked = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    time_taken = db.Column(db.String(50), nullable=True) # 比如 "30分钟"
    notes = db.Column(db.Text, nullable=True) # 制作心得
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)


# --- 路由 (Routes / 网页) ---

# ... '/' (index) 路由保持不变 ...
@app.route('/')
def index():
    all_recipes = Recipe.query.all()
    return render_template('index.html', recipes=all_recipes)

# 'add_recipe' 路由修改
@app.route('/add_recipe', methods=['GET', 'POST'])
def add_recipe():
    if request.method == 'POST':
        recipe_name = request.form['recipe_name']
        instructions = request.form['instructions']
        
        if not recipe_name:
            flash('菜谱名称不能为空!', 'error')
            return redirect(url_for('add_recipe'))
        
        image_filename = 'default.jpg' 
        new_recipe = None # NEW: 提前声明

        # --- 处理图片 (和之前一样) ---
        if 'recipe_image' in request.files:
            file = request.files['recipe_image']
            if file.filename != '' and allowed_file(file.filename):
                try:
                    new_recipe = Recipe(name=recipe_name, instructions=instructions)
                    db.session.add(new_recipe)
                    db.session.commit()
                    
                    original_filename = secure_filename(file.filename)
                    ext = original_filename.rsplit('.', 1)[1].lower()
                    image_filename = f"recipe_{new_recipe.id}.{ext}"
                    
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                    file.save(file_path)
                    
                    new_recipe.image_file = image_filename
                except Exception as e:
                    db.session.rollback()
                    flash(f'处理图片时出错: {e}', 'error')
                    return redirect(url_for('add_recipe'))
        
        # 如果没有上传图片, 或者处理失败, 确保 new_recipe 对象存在
        if new_recipe is None:
             new_recipe = Recipe(name=recipe_name, instructions=instructions, image_file=image_filename)
             db.session.add(new_recipe)


        # --- 处理食材和调料 ---
        try:
            # 提交菜谱基本信息 (和图片)
            db.session.commit() # 此时 new_recipe.id 肯定存在了
            
            # 1. 获取食材 (和之前一样)
            ingredient_names = request.form.getlist('ingredient_name[]')
            ingredient_qtys = request.form.getlist('ingredient_qty[]')
            
            for name, qty in zip(ingredient_names, ingredient_qtys):
                if name:
                    ingredient = Ingredient(name=name, quantity=qty, recipe_id=new_recipe.id)
                    db.session.add(ingredient)
            
            # 2. NEW: 获取调料
            seasoning_names = request.form.getlist('seasoning_name[]')
            seasoning_qtys = request.form.getlist('seasoning_qty[]')

            for name, qty in zip(seasoning_names, seasoning_qtys):
                if name: # 确保调料名称不为空
                    seasoning = Seasoning(name=name, quantity=qty, recipe_id=new_recipe.id)
                    db.session.add(seasoning)

            # 3. 一次性提交食材和调料
            db.session.commit()
            flash('菜谱添加成功!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            # 如果是唯一性约束错误 (比如菜谱名重复)
            if "UNIQUE constraint failed" in str(e):
                 flash(f'添加失败: 菜谱名称 "{recipe_name}" 已经存在。', 'error')
            else:
                 flash(f'添加失败: {e}', 'error')
            return redirect(url_for('add_recipe'))
            
    return render_template('add_recipe.html')


# ... recipe_detail, add_log, what_can_i_make 路由保持不变 (除了 detail 页的模板) ...
@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    return render_template('recipe_detail.html', recipe=recipe)
# NEW: 删除菜谱的路由
@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
def delete_recipe(recipe_id):
    # 1. 根据ID找到要删除的菜谱
    recipe_to_delete = Recipe.query.get_or_404(recipe_id)
    
    # 2. (可选但推荐) 删除关联的图片文件，以节省服务器空间
    image_filename = recipe_to_delete.image_file
    if image_filename != 'default.jpg': # 不删除默认图片
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            # 即使图片删除失败，也继续删除数据库条目
            print(f"警告: 无法删除图片 {image_path}. 错误: {e}")
            pass 
    
    try:
        # 3. 从数据库中删除该菜谱
        # (由于我们设置了级联删除, 相关的食材、调料、日志也会被自动删除)
        db.session.delete(recipe_to_delete)
        
        # 4. 提交更改
        db.session.commit()
        
        flash(f'菜谱 "{recipe_to_delete.name}" 已被成功删除。', 'success')
        # 5. 重定向回主页
        return redirect(url_for('index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'删除菜谱时出错: {e}', 'error')
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))
# --- (新代码结束) ---
@app.route('/recipe/<int:recipe_id>/add_log', methods=['POST'])
def add_log(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    time_taken = request.form['time_taken']
    notes = request.form['notes']
    new_log = CookingLog(time_taken=time_taken, notes=notes, recipe_id=recipe.id)
    db.session.add(new_log)
    db.session.commit()
    flash('烹饪日志已添加!', 'success')
    return redirect(url_for('recipe_detail', recipe_id=recipe.id))

@app.route('/what_can_i_make', methods=['GET', 'POST'])
def what_can_i_make():
    perfect_matches = [] # 完美匹配 (所有食材都有)
    partial_matches = [] # 部分匹配 (还缺几样)
    pantry_input = "" # 用于在页面上回显用户输入

    if request.method == 'POST':
        pantry_input = request.form['pantry']
        
        # 1. 清理用户输入:
        # 允许用户使用逗号、空格、换行来分隔
        # "鸡蛋,番茄\n白菜" -> ["鸡蛋", "番茄", "白菜"]
        # 我们使用 re.split 来处理多种分隔符
        user_pantry_list = re.split(r'[,\s\n]+', pantry_input)
        
        # 2. 转换为 "集合(Set)" 以提高查询效率, 并去除空字符串
        user_pantry_set = {item.strip() for item in user_pantry_list if item.strip()}

        if not user_pantry_set:
            flash('请输入您拥有的食材！', 'error')
            return render_template('what_can_i_make.html', pantry_input=pantry_input)

        # 3. 遍历所有菜谱
        all_recipes = Recipe.query.all()
        
        for recipe in all_recipes:
            # 4. 获取每道菜的 "必要食材" 列表
            # (我们假设筛选只基于 "食材"，不基于 "调料")
            required_ingredients_set = {ing.name.strip() for ing in recipe.ingredients}

            # 如果这个菜谱没有定义食材，跳过
            if not required_ingredients_set:
                continue

            # 5. 核心匹配逻辑
            
            # 检查：用户拥有的食材 (user_pantry_set) 
            # 是否 "完全包含" 菜谱所需的食材 (required_ingredients_set)
            
            if required_ingredients_set.issubset(user_pantry_set):
                # 5a. 完美匹配
                perfect_matches.append(recipe)
            else:
                # 5b. 检查是否为部分匹配
                missing_ingredients = required_ingredients_set.difference(user_pantry_set)
                
                # 如果缺少的食材 "不是全部" (说明至少有一部分匹配)
                if len(missing_ingredients) < len(required_ingredients_set):
                    # 我们把 (菜谱, 缺少的食材列表) 一起存入
                    partial_matches.append((recipe, list(missing_ingredients)))

    # 渲染结果页 (GET请求 或 POST处理完毕后)
    return render_template('what_can_i_make.html', 
                           perfect_matches=perfect_matches, 
                           partial_matches=partial_matches,
                           pantry_input=pantry_input,
                           has_searched=request.method == 'POST') # 标记是否已执行过搜索

# --- 启动器 ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)