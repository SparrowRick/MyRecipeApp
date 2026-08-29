import os
import unittest
from unittest import mock

# Tests must never connect to the application's real SQLite file.
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

import app as application


class CoupleAppTestCase(unittest.TestCase):
    def setUp(self):
        application.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.app = application.app
        self.db = application.db
        with self.app.app_context():
            self.db.drop_all()
            self.db.create_all()
            first = application.User(username='first')
            first.set_password('password-one')
            second = application.User(username='second')
            second.set_password('password-two')
            outsider = application.User(username='outsider')
            outsider.set_password('password-three')
            self.db.session.add_all([first, second, outsider])
            self.db.session.flush()
            first.partner_id = second.id
            second.partner_id = first.id
            self.db.session.commit()
            self.first_id, self.second_id, self.outsider_id = first.id, second.id, outsider.id

    def tearDown(self):
        with self.app.app_context():
            self.db.session.remove()
            self.db.drop_all()

    def login_as(self, client, user_id):
        with client.session_transaction() as session:
            session['_user_id'] = str(user_id)
            session['_fresh'] = True

    def test_registration_is_closed(self):
        response = self.app.test_client().get('/register')
        self.assertEqual(response.status_code, 404)

    def test_journal_upsert_is_idempotent(self):
        client = self.app.test_client()
        self.login_as(client, self.first_id)
        payload = {'date': '2026-07-21', 'content': '第一版', 'request_id': 'request-1'}
        self.assertEqual(client.post('/journal/add', json=payload).status_code, 200)
        payload['content'] = '修改后的内容'
        response = client.post('/journal/add', json=payload)
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            rows = application.JournalEntry.query.all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].content, '修改后的内容')

    def test_question_remains_open_until_both_answer(self):
        with self.app.app_context():
            question = application.DailyQuestion(content='最近哪件小事让你觉得被照顾到了？', date_str='2026-07-21')
            self.db.session.add(question)
            self.db.session.commit()
            question_id = question.id
        first_client = self.app.test_client()
        self.login_as(first_client, self.first_id)
        first_client.post(f'/daily_question/answer/{question_id}', data={'content': '一件小事'})
        with self.app.app_context():
            self.assertEqual(self.db.session.get(application.DailyQuestion, question_id).status, 'open')
        second_client = self.app.test_client()
        self.login_as(second_client, self.second_id)
        second_client.post(f'/daily_question/answer/{question_id}', data={'content': '另一件小事'})
        with self.app.app_context():
            self.assertEqual(self.db.session.get(application.DailyQuestion, question_id).status, 'completed')

    def test_question_context_is_limited_to_ten(self):
        with self.app.app_context():
            for index in range(12):
                self.db.session.add(application.DailyQuestion(content=f'这是第{index}个足够具体而且值得回答的问题吗？', date_str=f'2026-07-{index + 1:02d}', status='closed'))
            self.db.session.commit()
            history = application._compact_question_history()
            self.assertEqual(len(history), 10)

    def test_question_filter_requires_a_bilateral_neutral_viewpoint(self):
        recent = []
        self.assertFalse(application._question_is_acceptable(
            '当你觉得意见没有被重视时，我应该怎样回应你？', recent
        ))
        self.assertFalse(application._question_is_acceptable(
            '你这周盯盘时最希望对方怎样配合你的节奏？', recent
        ))
        self.assertFalse(application._question_is_acceptable(
            '你难过时更希望对方拥抱你还是陪你散步？', recent
        ))
        self.assertTrue(application._question_is_acceptable(
            '最近哪一种寻常气味会让你立刻觉得安心？', recent
        ))

    def test_question_filter_cools_down_semantically_repeated_themes(self):
        recent = [
            '这周赶方案或盯盘特别累的时候，对方做什么会让你放松？',
            '异地期间，哪一种联络习惯让你觉得彼此仍然很近？',
            '高强度工作期情绪急躁时，怎样沟通最有效？',
            '当意见没被重视时，哪种回应会让你愿意继续说？',
        ]
        self.assertFalse(application._question_is_acceptable(
            '最近工作很累时，你最希望对方怎样陪伴你？', recent
        ))
        self.assertFalse(application._question_is_acceptable(
            '最近不能见面的日子里，什么小事最能缩短距离？', recent
        ))
        self.assertTrue(application._question_is_acceptable(
            '最近哪一种寻常气味会让你立刻觉得安心？', recent
        ))

    def test_ai_generation_ignores_one_sided_and_repeated_candidates(self):
        with self.app.app_context():
            self.db.session.add(application.DailyQuestion(
                content='最近工作很累时，对方做什么会让你放松？',
                date_str='2026-08-28', status='completed'
            ))
            self.db.session.commit()
            fake_response = mock.Mock()
            fake_response.raise_for_status.return_value = None
            fake_response.json.return_value = {
                'choices': [{'message': {'content': application.json.dumps({
                    'candidates': [
                        {'question': '你这周盯盘时最希望对方怎样配合你的节奏？', 'both_answerable': True, 'natural': 10, 'desire': 10, 'freshness': 10},
                        {'question': '最近加班回家后，对方做什么最能让你放松？', 'both_answerable': True, 'natural': 9, 'desire': 9, 'freshness': 9},
                        {'question': '最近哪一种寻常气味会让你立刻觉得安心？', 'both_answerable': False, 'natural': 10, 'desire': 10, 'freshness': 10},
                        {'question': '最近哪一个普通声音让你感到生活很踏实？', 'both_answerable': True, 'natural': 8, 'desire': 8, 'freshness': 9},
                    ]
                }, ensure_ascii=False)}}]
            }
            old_key = self.app.config.get('DASHSCOPE_API_KEY')
            self.app.config['DASHSCOPE_API_KEY'] = 'test-key'
            try:
                with mock.patch.object(application.requests, 'post', return_value=fake_response) as post:
                    question, meta = application.generate_question_from_ai()
            finally:
                self.app.config['DASHSCOPE_API_KEY'] = old_key

        self.assertEqual(question, '最近哪一个普通声音让你感到生活很踏实？')
        self.assertEqual(meta['valid_count'], 1)
        sent_prompt = post.call_args.kwargs['json']['messages'][0]['content']
        self.assertIn('同一句问题原样展示给两个人', sent_prompt)
        self.assertIn('both_answerable', sent_prompt)

    def test_outsider_cannot_read_memory_by_id(self):
        with self.app.app_context():
            memory = application.Memory(title='private', content='secret', author_id=self.first_id)
            self.db.session.add(memory)
            self.db.session.commit()
            memory_id = memory.id
        client = self.app.test_client()
        self.login_as(client, self.outsider_id)
        self.assertEqual(client.get(f'/memory/{memory_id}').status_code, 404)

    def test_markdown_is_sanitized(self):
        cleaned = application.render_safe_markdown('[安全](javascript:alert(1))<script>alert(2)</script>')
        self.assertNotIn('<script', cleaned)
        self.assertNotIn('javascript:', cleaned)

    def test_main_pages_render(self):
        client = self.app.test_client()
        self.login_as(client, self.first_id)
        for path in ('/', '/journal', '/daily_question', '/daily_question/history', '/weekly', '/partner'):
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 200)

    def test_open_question_is_reused(self):
        with self.app.app_context():
            question = application.DailyQuestion(content='最近哪件小事让你觉得被照顾到了？', date_str='2026-01-01')
            self.db.session.add(question)
            self.db.session.commit()
            original_id = question.id
        client = self.app.test_client()
        self.login_as(client, self.first_id)
        client.get('/daily_question')
        client.get('/daily_question')
        with self.app.app_context():
            open_questions = application.DailyQuestion.query.filter_by(status='open').all()
            self.assertEqual([item.id for item in open_questions], [original_id])

    def test_completed_question_is_reused_for_the_rest_of_the_day(self):
        today = application.datetime.date.today().isoformat()
        with self.app.app_context():
            question = application.DailyQuestion(
                content='今天最想和对方分享的一件小事是什么？',
                date_str=today,
            )
            self.db.session.add(question)
            self.db.session.commit()
            question_id = question.id

        first_client = self.app.test_client()
        self.login_as(first_client, self.first_id)
        second_client = self.app.test_client()
        self.login_as(second_client, self.second_id)
        first_client.post(f'/daily_question/answer/{question_id}', data={'content': '我的回答'})
        second_client.post(f'/daily_question/answer/{question_id}', data={'content': '对方的回答'})

        with mock.patch.object(application, 'generate_question_from_ai') as generate:
            response = first_client.get('/daily_question')

        self.assertEqual(response.status_code, 200)
        self.assertIn('今天最想和对方分享的一件小事是什么？'.encode('utf-8'), response.data)
        generate.assert_not_called()
        with self.app.app_context():
            self.assertEqual(application.DailyQuestion.query.count(), 1)

    def test_only_one_primary_question_can_exist_per_day(self):
        today = application.datetime.date.today().isoformat()
        with self.app.app_context():
            first = application.DailyQuestion(
                content='今天最想和对方分享的一件小事是什么？', date_str=today,
            )
            self.db.session.add(first)
            self.db.session.commit()

            duplicate = application.DailyQuestion(
                content='今天有没有一句想对对方说的话？', date_str=today,
            )
            self.db.session.add(duplicate)
            with self.assertRaises(application.IntegrityError):
                self.db.session.commit()
            self.db.session.rollback()

    def test_new_question_is_created_on_next_day_after_completion(self):
        next_day = application.datetime.date(2026, 7, 23)
        with self.app.app_context():
            previous = application.DailyQuestion(
                content='昨天最值得记住的小事是什么？',
                date_str='2026-07-22',
                status='completed',
            )
            self.db.session.add(previous)
            self.db.session.commit()

            with mock.patch.object(
                application,
                'generate_question_from_ai',
                return_value=('今天想一起完成哪件小事？', {'model': 'test'}),
            ) as generate:
                first = application.get_or_create_daily_question(next_day)
                second = application.get_or_create_daily_question(next_day)

            self.assertEqual(first.id, second.id)
            self.assertEqual(first.date_str, next_day.isoformat())
            self.assertEqual(application.DailyQuestion.query.count(), 2)
            generate.assert_called_once_with()

    def test_skip_feedback_closes_question(self):
        with self.app.app_context():
            question = application.DailyQuestion(content='最近哪件小事让你觉得被照顾到了？', date_str='2026-07-21')
            self.db.session.add(question)
            self.db.session.commit()
            question_id = question.id
        client = self.app.test_client()
        self.login_as(client, self.first_id)
        response = client.post(
            f'/daily_question/{question_id}/feedback',
            data={'feedback_type': 'skipped', 'reason': 'not_today'},
            follow_redirects=False
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            question = self.db.session.get(application.DailyQuestion, question_id)
            self.assertEqual(question.status, 'skipped')
            self.assertEqual(question.close_reason, 'not_today')

    def test_csrf_protects_json_write(self):
        client = self.app.test_client()
        self.login_as(client, self.first_id)
        self.app.config['WTF_CSRF_ENABLED'] = True
        try:
            response = client.post('/journal/add', json={'date': '2026-07-21', 'content': 'no token'})
            self.assertEqual(response.status_code, 400)
        finally:
            self.app.config['WTF_CSRF_ENABLED'] = False

    def test_system_recipe_owner_cannot_log_in(self):
        with self.app.app_context():
            system_user = application.User(username=application.SYSTEM_RECIPE_USERNAME)
            system_user.set_password('known-password')
            self.db.session.add(system_user)
            self.db.session.commit()
        client = self.app.test_client()
        response = client.post('/login', data={'username': application.SYSTEM_RECIPE_USERNAME, 'password': 'known-password'}, follow_redirects=True)
        self.assertIn('无效的用户名或密码'.encode('utf-8'), response.data)


if __name__ == '__main__':
    unittest.main()
