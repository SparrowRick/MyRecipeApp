"""private couple reliability and interaction upgrade

Revision ID: 9f8a7b6c5d4e
Revises: acf0745ab1c0
"""
from alembic import op
import sqlalchemy as sa


revision = '9f8a7b6c5d4e'
down_revision = 'acf0745ab1c0'
branch_labels = None
depends_on = None


def upgrade():
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('ai_context_consent', sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table('journal_entry') as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))
        batch_op.add_column(sa.Column('last_request_id', sa.String(length=64), nullable=True))

    for table_name in ('recipe', 'memory', 'wishlist_item', 'fridge_item'):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))

    if 'daily_question' not in existing_tables:
        op.create_table(
            'daily_question',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('content', sa.String(length=200), nullable=False),
            sa.Column('date_str', sa.String(length=10), nullable=False),
            sa.Column('source', sa.String(length=20), nullable=True, server_default='精选题库'),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
            sa.Column('close_reason', sa.String(length=40), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('closed_at', sa.DateTime(), nullable=True),
            sa.Column('generation_meta', sa.Text(), nullable=True),
        )
    else:
        # SQLite needs a table rebuild to remove the old global UNIQUE(date_str).
        naming = {'uq': 'uq_%(table_name)s_%(column_0_name)s'}
        with op.batch_alter_table('daily_question', naming_convention=naming, recreate='always') as batch_op:
            batch_op.add_column(sa.Column('status', sa.String(length=20), nullable=False, server_default='closed'))
            batch_op.add_column(sa.Column('close_reason', sa.String(length=40), nullable=True))
            batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))
            batch_op.add_column(sa.Column('closed_at', sa.DateTime(), nullable=True))
            batch_op.add_column(sa.Column('generation_meta', sa.Text(), nullable=True))
            batch_op.drop_constraint('uq_daily_question_date_str', type_='unique')

    if 'daily_answer' not in existing_tables:
        op.create_table(
            'daily_answer',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
            sa.Column('question_id', sa.Integer(), sa.ForeignKey('daily_question.id'), nullable=False),
            sa.UniqueConstraint('question_id', 'user_id', name='uq_daily_answer_question_user'),
        )

    op.create_index(
        'uq_daily_question_single_open', 'daily_question', ['status'],
        unique=True, sqlite_where=sa.text("status = 'open'")
    )

    # V1 questions stay available in history but do not become the new active prompt.
    # The first visit after upgrading creates a fresh question with the V2 quality rules.

    if 'daily_answer' in existing_tables:
        with op.batch_alter_table('daily_answer') as batch_op:
            batch_op.create_unique_constraint('uq_daily_answer_question_user', ['question_id', 'user_id'])

    with op.batch_alter_table('question_like') as batch_op:
        batch_op.create_unique_constraint('uq_question_like_question_user', ['question_id', 'user_id'])

    op.create_table(
        'question_feedback',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('question_id', sa.Integer(), sa.ForeignKey('daily_question.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('feedback_type', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('question_id', 'user_id', name='uq_question_feedback_question_user'),
    )
    op.create_table(
        'couple_ai_profile',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'notification_outbox',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('body', sa.String(length=500), nullable=False),
        sa.Column('target_url', sa.String(length=300), nullable=False, server_default='/'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'daily_check_in',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('date_str', sa.String(length=10), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('mood', sa.String(length=20), nullable=False),
        sa.Column('energy', sa.String(length=20), nullable=False),
        sa.Column('need', sa.String(length=30), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('date_str', 'user_id', name='uq_check_in_date_user'),
    )
    op.create_table(
        'weekly_reflection',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('week_start', sa.String(length=10), nullable=False, unique=True),
        sa.Column('summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('gratitude_user_1', sa.Text(), nullable=True),
        sa.Column('gratitude_user_2', sa.Text(), nullable=True),
        sa.Column('confirmed_user_1', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('confirmed_user_2', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_table(
        'couple_task',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('week_start', sa.String(length=10), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('completed_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )


def downgrade():
    for table_name in ('couple_task', 'weekly_reflection', 'daily_check_in', 'notification_outbox', 'couple_ai_profile', 'question_feedback'):
        op.drop_table(table_name)
    with op.batch_alter_table('question_like') as batch_op:
        batch_op.drop_constraint('uq_question_like_question_user', type_='unique')
    with op.batch_alter_table('daily_answer') as batch_op:
        batch_op.drop_constraint('uq_daily_answer_question_user', type_='unique')
    with op.batch_alter_table('daily_question') as batch_op:
        batch_op.drop_index('uq_daily_question_single_open')
        batch_op.drop_column('generation_meta')
        batch_op.drop_column('closed_at')
        batch_op.drop_column('created_at')
        batch_op.drop_column('close_reason')
        batch_op.drop_column('status')
        batch_op.create_unique_constraint('uq_daily_question_date_str', ['date_str'])
    for table_name in ('fridge_item', 'wishlist_item', 'memory', 'recipe'):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column('created_at')
    with op.batch_alter_table('journal_entry') as batch_op:
        batch_op.drop_column('last_request_id')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('created_at')
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('ai_context_consent')
