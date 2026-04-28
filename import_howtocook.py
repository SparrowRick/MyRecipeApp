import os
import glob
import re
import subprocess
import shutil
from app import app, db, User, Recipe, Ingredient

REPO_URL = "https://github.com/Anduin2017/HowToCook.git"
TEMP_DIR = "temp_howtocook"
SYSTEM_USERNAME = "GitHub how to cook"

def setup_user():
    with app.app_context():
        user = User.query.filter_by(username=SYSTEM_USERNAME).first()
        if not user:
            print(f"创建系统账号: {SYSTEM_USERNAME}")
            user = User(username=SYSTEM_USERNAME)
            user.set_password("system_random_password_12345!")
            db.session.add(user)
            db.session.commit()
        return user.id

def clone_repo():
    if os.path.exists(TEMP_DIR):
        print(f"清理旧的 {TEMP_DIR} 目录...")
        shutil.rmtree(TEMP_DIR)
    
    print(f"正在克隆 HowToCook 仓库到 {TEMP_DIR} (这可能需要一些时间)...")
    subprocess.run(["git", "clone", "--depth", "1", REPO_URL, TEMP_DIR], check=True)

def parse_markdown(filepath):
    """简单解析 Markdown 提取菜名和材料"""
    filename = os.path.basename(filepath)
    recipe_name = os.path.splitext(filename)[0]
    
    ingredients = []
    instructions_lines = []
    
    # 一个极简的解析逻辑，实际 Markdown 格式可能多变，尽力提取
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    in_ingredients_section = False
    
    for line in lines:
        line = line.strip()
        instructions_lines.append(line)
        
        # 判断是否进入材料区
        if '原料' in line or '材料' in line or '食材' in line or '必备' in line:
            if line.startswith('#'):
                in_ingredients_section = True
                continue
                
        # 判断是否离开材料区
        if in_ingredients_section and line.startswith('#'):
            if '步' in line or '做' in line or '进阶' in line:
                in_ingredients_section = False
        
        # 提取列表项作为材料
        if in_ingredients_section:
            if line.startswith('- ') or line.startswith('* '):
                # 提取出 "- 猪肉 500g" 中的 "猪肉" 和 "500g"
                ing_text = line[2:].strip()
                # 简单分隔，如果没有数量就不管
                parts = re.split(r'[-\*\s:,]+', ing_text)
                name = parts[0] if parts else ing_text
                qty = parts[1] if len(parts)>1 else "适量"
                if name:
                    # 避免一些说明性文字被当成材料
                    if len(name) < 15: 
                        ingredients.append({"name": name, "qty": qty})
                        
    return {
        "name": recipe_name,
        "ingredients": ingredients,
        "instructions": "\n".join(instructions_lines)
    }

def import_recipes(user_id):
    search_path = os.path.join(TEMP_DIR, 'dishes', '**', '*.md')
    md_files = glob.glob(search_path, recursive=True)

    print(f"找到 {len(md_files)} 个菜谱文件。准备导入...")

    success_count = 0
    with app.app_context():
        for filepath in md_files:
            if 'README' in filepath or 'example' in filepath.lower() or 'template' in filepath.lower():
                continue

            category = os.path.basename(os.path.dirname(filepath))
            parsed = parse_markdown(filepath)
            name = parsed['name']

            existing = Recipe.query.filter_by(name=name, user_id=user_id).first()
            if existing:
                existing.category = category
                db.session.commit()
                continue

            print(f"导入: {name}")
            new_recipe = Recipe(
                name=name,
                instructions=parsed['instructions'][:2000],
                user_id=user_id,
                image_file='default.jpg',
                category=category
            )
            db.session.add(new_recipe)
            db.session.flush()

            for ing in parsed['ingredients']:
                db.session.add(Ingredient(name=ing['name'], quantity=ing['qty'], recipe_id=new_recipe.id))

            success_count += 1
            if success_count % 50 == 0:
                db.session.commit()

        db.session.commit()

    print(f"成功导入 {success_count} 个新菜谱！")

if __name__ == '__main__':
    user_id = setup_user()
    clone_repo()
    import_recipes(user_id)
    
    # 清理
    if os.path.exists(TEMP_DIR):
        print("清理临时文件...")
        # Windows由于文件占用有时不好直接删带有 .git 的目录，可以用 cmd 的 rmdir
        try:
             shutil.rmtree(TEMP_DIR, ignore_errors=True)
        except Exception as e:
             print(f"清理临时目录失败: {e}")
            
    print("全部完成！请在网站上查看 'GitHub how to cook' 账号的菜谱。")
