"""enforce one primary daily question per date

Revision ID: b31f2d9a6e7c
Revises: 9f8a7b6c5d4e
"""
from alembic import op
import sqlalchemy as sa


revision = 'b31f2d9a6e7c'
down_revision = '9f8a7b6c5d4e'
branch_labels = None
depends_on = None


def upgrade():
    # Keep legacy duplicates for history, but designate the original question as
    # the one daily prompt for that date before adding the partial unique index.
    with op.batch_alter_table('daily_question') as batch_op:
        batch_op.add_column(
            sa.Column('is_daily_primary', sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.execute("""
        UPDATE daily_question
        SET is_daily_primary = 1
        WHERE id IN (
            SELECT original_id
            FROM (
                SELECT MIN(id) AS original_id
                FROM daily_question
                GROUP BY date_str
            )
        )
    """)
    op.create_index(
        'uq_daily_question_date_primary', 'daily_question', ['date_str'],
        unique=True, sqlite_where=sa.text('is_daily_primary = 1')
    )


def downgrade():
    op.drop_index('uq_daily_question_date_primary', table_name='daily_question')
    with op.batch_alter_table('daily_question') as batch_op:
        batch_op.drop_column('is_daily_primary')
