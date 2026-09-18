"""Sync recipes from the HowToCook repository into the local cookbook.

Safe to re-run: recipes are matched on (name, system user) and updated in place.
"""
import argparse
import hashlib
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, unquote, urljoin

from PIL import Image, ImageOps, UnidentifiedImageError

from app import app, db, User, Recipe, Ingredient, Seasoning

REPO_URL = "https://github.com/Anduin2017/HowToCook.git"
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_howtocook')
SYSTEM_USERNAME = "GitHub how to cook"
SOURCE_TAG = "HowToCook"
BLOB_BASE = "https://github.com/Anduin2017/HowToCook/blob/master/dishes"
IMAGE_SUBDIR = "howtocook"

CATEGORY_MAP = {
    'aquatic': '水产',
    'breakfast': '早餐',
    'condiment': '调味料',
    'dessert': '甜点',
    'drink': '饮品',
    'meat_dish': '荤菜',
    'semi-finished': '半成品',
    'soup': '汤羹',
    'staple': '主食',
    'vegetable_dish': '素菜',
}

SEASONINGS = {
    '盐', '食盐', '食用盐', '精盐', '糖', '白糖', '白砂糖', '冰糖', '红糖',
    '生抽', '老抽', '酱油', '生抽酱油', '蚝油', '香油', '芝麻油', '食用油',
    '油', '花生油', '菜籽油', '橄榄油', '料酒', '黄酒', '白酒', '醋', '白醋',
    '陈醋', '香醋', '米醋', '豆瓣酱', '甜面酱', '番茄酱', '沙茶酱', '蒜蓉辣椒酱',
    '辣椒酱', '味精', '鸡精', '胡椒粉', '白胡椒粉', '黑胡椒', '黑胡椒粉',
    '花椒', '八角', '桂皮', '香叶', '孜然', '孜然粉', '五香粉', '十三香',
    '辣椒粉', '干辣椒', '淀粉', '生粉', '玉米淀粉', '水淀粉', '蜂蜜', '芝麻',
    '白芝麻', '耗油', '老干妈', '豆豉', '腐乳', '咖喱', '咖喱块',
}

# The repo appends this call-to-action to every 附加内容 section; it is not a cooking tip.
BOILERPLATE = re.compile(r'如果您遵循本指南的制作流程.*?(Issue|issue).*?$', re.M)
IMAGE_LINE = re.compile(r'^\s*!\[.*?\]\(.*?\)\s*$', re.M)
IMAGE_REF = re.compile(r'!\[.*?\]\(\s*(.*?)\s*\)')
SECTION = re.compile(r'^## +(.+?)\s*$', re.M)
TOOLS = re.compile(r'(?:锅|烤箱|微波炉|电饭煲|电蒸炉|煲汤盅|刀|砧板|案板|碗|盘子|筷子|锅铲|笊篱|刮刀|模具|分蛋器|打蛋器|擀面杖|烘焙纸|锡纸|保鲜膜|吧勺|压汁器|海波杯|过滤网|纱布|量杯|搅拌机|榨汁机|烤盘|电子秤)')
WATER = {'水', '清水', '开水', '冷水', '热水', '温水', '饮用水', '凉白开水'}


def is_tool(name):
    # Avoid confusing food names such as 火锅底料、二锅头、刀削面 with equipment.
    return bool(TOOLS.search(name)) and not any(word in name for word in ('底料', '二锅头', '刀削', '锅巴'))


def setup_user():
    user = User.query.filter_by(username=SYSTEM_USERNAME).first()
    if not user:
        print(f"创建系统账号: {SYSTEM_USERNAME}")
        user = User(username=SYSTEM_USERNAME)
        # The system recipe owner must never have a known, reusable login password.
        user.set_password(secrets.token_urlsafe(48))
        db.session.add(user)
        db.session.commit()
    return user.id


def clone_repo():
    if os.path.exists(TEMP_DIR):
        raise SystemExit(f'{TEMP_DIR} 已存在；请用 --skip-clone 复用，或先将旧目录移走后再同步。')
    print(f"正在克隆 HowToCook 仓库到 {TEMP_DIR} (这可能需要几分钟)...")
    subprocess.run(["git", "clone", "--depth", "1", REPO_URL, TEMP_DIR], check=True)


def split_sections(text):
    """Return {heading: body} for every level-2 section."""
    marks = list(SECTION.finditer(text))
    sections = {}
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        sections[mark.group(1)] = text[mark.end():end].strip()
    return sections, marks[0].start() if marks else len(text)


def top_level_items(body):
    """Bullet list items at indent level 0, with any parenthetical note kept aside."""
    items = []
    for line in body.split('\n'):
        if line.startswith(('- ', '* ', '+ ')):
            items.append(line[2:].strip())
    return items


def strip_note(value):
    return re.sub(r'[（(].*', '', value).strip()


def parse_quantity(name, calc_items):
    """Find the 计算 line describing `name` and return just the amount part."""
    for item in calc_items:
        if not item.startswith(name):
            continue
        rest = item[len(name):].strip()
        rest = re.sub(r'^(的用量为|用量为|的用量|：|:|=|＝)\s*', '', rest).strip()
        return (rest or '适量')[:50]
    return '适量'


def parse_recipe(md_path, rel_path):
    text = Path(md_path).read_text(encoding='utf-8')
    source_url = f"{BLOB_BASE}/{quote(rel_path.replace(os.sep, '/'), safe='/')}"

    def source_links(body):
        # Keep diagrams and relative reference links usable on the recipe page.
        def replace(match):
            label, target = match.groups()
            resolved = urljoin(source_url, target)
            if label.startswith('!'):
                resolved = resolved.replace('github.com/Anduin2017/HowToCook/blob/', 'raw.githubusercontent.com/Anduin2017/HowToCook/')
                label = '[查看步骤图片：' + (label[2:-1] or '原图') + ']'
            return f'{label}({resolved})'
        return re.sub(r'(!?\[[^\]]*\])\(([^\s)]+)\)', replace, body)

    title = re.search(r'^# +(.+?)\s*$', text, re.M)
    name = title.group(1).strip() if title else os.path.splitext(os.path.basename(md_path))[0]
    name = re.sub(r'的做法$', '', name).strip()

    difficulty = None
    stars = re.search(r'预估烹饪难度：\s*(★+)', text)
    if stars:
        difficulty = len(stars.group(1))

    calories = None
    kcal = re.search(r'预估卡路里：\s*(\d+)', text)
    if kcal:
        calories = int(kcal.group(1))

    sections, first_section_at = split_sections(text)

    # Description: prose between the title and the first metadata line.
    head = text[:first_section_at]
    head = re.sub(r'^# .*$', '', head, count=1, flags=re.M)
    head = re.split(r'预估烹饪难度：', head)[0]
    head = IMAGE_LINE.sub('', head)
    description = '\n'.join(p.strip() for p in head.strip().split('\n') if p.strip()) or None

    material_items = top_level_items(sections.get('必备原料和工具', ''))
    calc_items = top_level_items(sections.get('计算', ''))

    ingredients, seasonings = [], []
    seen = set()
    for raw in material_items:
        item_name = strip_note(re.sub(r'^\[可选\]\s*', '', raw)).strip('`* ')
        inline_quantity = re.search(r'\s+(\d+(?:\.\d+)?\s*(?:g|kg|ml|L|克|千克|毫升|升|个|根|片|颗|只|块|斤|两)\b.*)$', item_name, re.I)
        if inline_quantity:
            item_name = item_name[:inline_quantity.start()].strip()
        if not item_name or len(item_name) > 40 or item_name in seen:
            continue
        seen.add(item_name)
        if is_tool(item_name) or item_name in WATER or item_name.startswith('注：'):
            continue
        quantity = parse_quantity(item_name, calc_items)
        if quantity == '适量' and inline_quantity:
            quantity = inline_quantity.group(1)
        if '可选' in raw:
            quantity = '可选；' + quantity
        entry = {'name': item_name[:100], 'quantity': quantity[:50]}
        (seasonings if item_name in SEASONINGS else ingredients).append(entry)

    steps = sections.get('操作', '').strip()
    if steps:
        # Retain the complete original quantities, serving basis and equipment.
        preparation = '\n\n'.join('### ' + heading + '\n\n' + sections[heading]
                                    for heading in ('必备原料和工具', '计算') if sections.get(heading))
        steps = source_links(preparation + '\n\n### 操作\n\n' + steps)

    tips = BOILERPLATE.sub('', sections.get('附加内容', '')).strip()
    tips = source_links(tips) if tips else None

    return {
        'name': name[:100],
        'description': description,
        'instructions': steps,
        'tips': tips,
        'difficulty': difficulty,
        'calories': calories,
        'ingredients': ingredients,
        'seasonings': seasonings,
        'source_url': source_url,
        'image_source': find_image(md_path, text),
    }


def find_image(md_path, text):
    """Prefer an image the document actually references, else any image beside it."""
    folder = os.path.dirname(md_path)
    for ref in IMAGE_REF.findall(text):
        if ref.startswith('http'):
            continue
        candidate = os.path.realpath(os.path.join(folder, unquote(ref)))
        root = os.path.realpath(os.path.join(TEMP_DIR, 'dishes'))
        if os.path.commonpath([root, candidate]) == root and os.path.isfile(candidate):
            return candidate
    # Shared category folders contain unrelated dishes: never borrow their photos.
    if len(list(Path(folder).glob('*.md'))) != 1:
        return None
    for entry in sorted(os.listdir(folder)):
        if entry.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            return os.path.join(folder, entry)
    return None


def store_image(source_path, rel_path):
    """Copy an image into static/uploads under a deterministic, ASCII-safe name."""
    digest = hashlib.md5(rel_path.replace(os.sep, '/').encode('utf-8')).hexdigest()[:16]
    rel_name = f"{IMAGE_SUBDIR}/{digest}.jpg"
    folder = os.path.join(app.config['UPLOAD_FOLDER'], IMAGE_SUBDIR)
    os.makedirs(folder, exist_ok=True)
    destination = os.path.join(app.config['UPLOAD_FOLDER'], rel_name)
    if os.path.exists(destination):
        return rel_name
    try:
        image = Image.open(source_path)
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((1600, 1600))
        image.save(destination, 'JPEG', quality=85, optimize=True)
        return rel_name
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        print(f"  图片处理失败 ({source_path}): {exc}")
        if os.path.exists(destination):
            os.remove(destination)
        return None


def sync(user_id, limit=None, with_images=True):
    dishes_root = os.path.join(TEMP_DIR, 'dishes')
    md_files = []
    for folder, _, files in os.walk(dishes_root):
        for filename in files:
            if filename.endswith('.md'):
                md_files.append(os.path.join(folder, filename))
    md_files.sort()

    created = updated = skipped = 0
    for md_path in md_files:
        rel_path = os.path.relpath(md_path, dishes_root)
        top = rel_path.split(os.sep)[0]
        if top == 'template' or os.path.basename(md_path).lower().startswith('readme'):
            skipped += 1
            continue
        if limit and (created + updated) >= limit:
            break

        parsed = parse_recipe(md_path, rel_path)
        if not parsed['name'] or not parsed['instructions']:
            print(f"  跳过（解析为空）: {rel_path}")
            skipped += 1
            continue

        recipe = Recipe.query.filter_by(source_url=parsed['source_url'], user_id=user_id).first()
        if recipe is None:
            recipe = Recipe.query.filter_by(name=parsed['name'], user_id=user_id).first()
            # Keep distinct upstream files even when their titles are identical.
            if recipe and recipe.source_url and unquote(recipe.source_url) != unquote(parsed['source_url']):
                suffix = hashlib.sha256(rel_path.replace(os.sep, '/').encode()).hexdigest()[:6]
                parsed['name'] = parsed['name'][:88] + f'（版本 {suffix}）'
                recipe = Recipe.query.filter_by(name=parsed['name'], user_id=user_id).first()
        is_new = recipe is None
        if is_new:
            recipe = Recipe(name=parsed['name'], user_id=user_id)
            db.session.add(recipe)

        recipe.category = CATEGORY_MAP.get(top, top)
        recipe.description = parsed['description']
        recipe.instructions = parsed['instructions']
        recipe.tips = parsed['tips']
        recipe.difficulty = parsed['difficulty']
        recipe.calories = parsed['calories']
        recipe.source = SOURCE_TAG
        recipe.source_url = parsed['source_url']

        if with_images and parsed['image_source']:
            stored = store_image(parsed['image_source'], rel_path)
            if stored:
                recipe.image_file = stored

        db.session.flush()

        Ingredient.query.filter_by(recipe_id=recipe.id).delete()
        Seasoning.query.filter_by(recipe_id=recipe.id).delete()
        for item in parsed['ingredients']:
            db.session.add(Ingredient(name=item['name'], quantity=item['quantity'], recipe_id=recipe.id))
        for item in parsed['seasonings']:
            db.session.add(Seasoning(name=item['name'], quantity=item['quantity'], recipe_id=recipe.id))

        if is_new:
            created += 1
        else:
            updated += 1
        if (created + updated) % 50 == 0:
            db.session.commit()
            print(f"  已处理 {created + updated} 道...")

    db.session.commit()
    print(f"\n完成：新增 {created} 道，更新 {updated} 道，跳过 {skipped} 个文件。")


def main():
    parser = argparse.ArgumentParser(description="同步 HowToCook 菜谱")
    parser.add_argument('--skip-clone', action='store_true', help='复用已存在的 temp_howtocook 目录')
    parser.add_argument('--no-images', action='store_true', help='不下载菜品图片')
    parser.add_argument('--limit', type=int, help='只导入前 N 道，用于试跑')
    parser.add_argument('--keep-temp', action='store_true', help='结束后保留克隆目录')
    args = parser.parse_args()

    if not args.skip_clone:
        clone_repo()
    elif not os.path.isdir(os.path.join(TEMP_DIR, 'dishes')):
        raise SystemExit(f"{TEMP_DIR}/dishes 不存在，请去掉 --skip-clone")

    with app.app_context():
        user_id = setup_user()
        sync(user_id, limit=args.limit, with_images=not args.no_images)

    if not args.keep_temp and not args.skip_clone:
        print("清理临时文件...")
        target = Path(TEMP_DIR).resolve()
        expected = Path(__file__).resolve().parent / 'temp_howtocook'
        if target != expected or target.is_symlink():
            raise RuntimeError('临时目录路径不符合预期，未清理')
        shutil.rmtree(target)


if __name__ == '__main__':
    main()
