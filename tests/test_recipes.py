import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
import app as a
import import_howtocook as importer


class RecipeTests(unittest.TestCase):
    def setUp(self):
        a.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = a.app.app_context()
        self.context.push()
        a.db.create_all()
        users = [a.User(username=name, password_hash='unused')
                 for name in ('owner', 'partner', 'outsider', a.SYSTEM_RECIPE_USERNAME)]
        a.db.session.add_all(users)
        a.db.session.flush()
        self.owner, self.partner, self.outsider, self.system = users
        self.owner.partner_id = self.partner.id
        a.db.session.commit()
        self.client = a.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.owner.id)
            session['_fresh'] = True

    def tearDown(self):
        a.db.session.remove()
        a.db.drop_all()
        self.context.pop()

    def recipe(self, name, user=None, category=None):
        recipe = a.Recipe(name=name, user_id=(user or self.owner).id, category=category)
        a.db.session.add(recipe)
        a.db.session.commit()
        return recipe

    def test_filters_counts_and_private_recipes(self):
        self.recipe('空分类甲')
        self.recipe('空分类乙', category='')
        self.recipe('已分类', category='素菜')
        self.recipe('伴侣菜谱', self.partner)
        self.recipe('系统菜谱', self.system)
        private = self.recipe('不应看到', self.outsider)
        page = self.client.get('/recipes?category=未分类&scope=ours').get_data(as_text=True)
        self.assertIn('共 3 道', page)
        self.assertIn('空分类甲', page)
        self.assertIn('伴侣菜谱', page)
        self.assertNotIn('系统菜谱</b>', page)
        self.assertNotIn('不应看到', page)
        self.assertEqual(self.client.get(f'/recipe/{private.id}').status_code, 302)
        library = self.client.get('/recipes?scope=library').get_data(as_text=True)
        self.assertIn('共 1 道', library)

    def test_pagination_preserves_filters_and_recovers_out_of_range(self):
        for i in range(25):
            self.recipe(f'分页菜{i:02}', category='素菜')
        response = self.client.get('/recipes?q=分页&scope=ours&category=素菜&page=999')
        self.assertEqual(response.status_code, 302)
        self.assertIn('page=2', response.location)
        page = self.client.get(response.location).get_data(as_text=True)
        self.assertIn('共 25 道', page)
        self.assertIn('第 2 / 2 页', page)
        self.assertIn('分页菜24', page)

    def test_pantry_aliases_optional_and_no_substring_false_matches(self):
        recipe = self.recipe('番茄炒蛋测试')
        a.db.session.add_all([a.Ingredient(recipe_id=recipe.id, name=n, quantity=q)
                              for n, q in [('西红柿', '1 个'), ('鸡蛋', '2 个'), ('葱花', '可选；适量')]])
        a.db.session.commit()
        page = self.client.post('/what_can_i_make', data={'pantry': '番茄、鸡蛋'}).get_data(as_text=True)
        self.assertIn('番茄炒蛋测试', page.split('ALMOST THERE')[0])
        self.assertFalse(a.ingredient_matches('鸡蛋', '鸡蛋面'))
        self.assertFalse(a.ingredient_matches('五花肉', '猪肉'))
        self.assertTrue(a.ingredient_matches('土豆', '马铃薯'))
        self.assertIn('番茄炒蛋测试', self.client.get('/recipes?q=西红柿').get_data(as_text=True))

    def test_plus_bullets_and_equipment_classification(self):
        self.assertEqual(importer.top_level_items('+ 猪肉\n+ 青椒\n  + 备注'), ['猪肉', '青椒'])
        self.assertTrue(importer.is_tool('压汁器'))
        self.assertFalse(importer.is_tool('北京二锅头酒'))

    def test_import_preserves_quantities_tools_optional_and_repeat_sync(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dish = root / 'dishes' / 'vegetable_dish' / '测试.md'
            dish.parent.mkdir(parents=True)
            dish.write_text('# 测试的做法\n\n预估烹饪难度：★★\n\n## 必备原料和工具\n\n* 西红柿\n* 鸡蛋\n* 葱花（可选）\n* 盐\n* 炒锅\n\n## 计算\n\n一份够 1 人食用\n\n* 西红柿 = 1 个 * 份数\n* 鸡蛋 = 2 个\n\n## 操作\n\n1. 炒熟\n\n## 附加内容\n\n第一段\n\n第二段', encoding='utf8')
            with patch.object(importer, 'TEMP_DIR', folder):
                importer.sync(self.system.id, with_images=False)
                first = a.Recipe.query.filter_by(user_id=self.system.id).one()
                first_id = first.id
                a.db.session.add(a.CookingLog(recipe_id=first.id, notes='保留批注'))
                a.db.session.commit()
                importer.sync(self.system.id, with_images=False)
                a.db.session.expire_all()
                recipe = a.Recipe.query.filter_by(user_id=self.system.id).one()
                self.assertEqual(recipe.id, first_id)
                self.assertEqual(len(recipe.logs), 1)
                self.assertEqual(len(recipe.ingredients), 3)
                self.assertEqual(len(recipe.seasonings), 1)
                self.assertIn('一份够 1 人食用', recipe.instructions)
                self.assertIn('炒锅', recipe.instructions)
                self.assertIn('可选', next(i.quantity for i in recipe.ingredients if i.name == '葱花'))
                self.assertIn('第一段\n\n第二段', recipe.tips)
                self.assertEqual(self.client.get(f'/recipe/{recipe.id}').status_code, 200)
                duplicate = dish.parent / '另一版本' / '测试.md'
                duplicate.parent.mkdir()
                duplicate.write_text(dish.read_text(encoding='utf8') + '\n\n![步骤](./step.png)', encoding='utf8')
                importer.sync(self.system.id, with_images=False)
                importer.sync(self.system.id, with_images=False)
                a.db.session.expire_all()
                self.assertEqual(a.Recipe.query.filter_by(user_id=self.system.id).count(), 2)
                variant = a.Recipe.query.filter(a.Recipe.id != first_id).one()
                self.assertIn('[查看步骤图片：步骤](https://raw.githubusercontent.com/', variant.tips)
                self.assertEqual(a.CookingLog.query.count(), 1)
