"""add recipe metadata fields and per-user name uniqueness

Revision ID: 3265ab6170d6
Revises: b31f2d9a6e7c
Create Date: 2026-09-18 12:51:12.921697

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3265ab6170d6'
down_revision = 'b31f2d9a6e7c'
branch_labels = None
depends_on = None


# The original UNIQUE(name) was declared inline, so SQLite stored it unnamed and
# autogenerate cannot drop it. Reflecting under this convention gives it a
# deterministic name that drop_constraint can target.
naming_convention = {'uq': 'uq_%(table_name)s_%(column_0_name)s'}


def upgrade():
    with op.batch_alter_table('recipe', schema=None, naming_convention=naming_convention) as batch_op:
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('tips', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('difficulty', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('calories', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('source', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('source_url', sa.String(length=300), nullable=True))
        batch_op.drop_constraint('uq_recipe_name', type_='unique')
        batch_op.create_unique_constraint('uq_recipe_name_user', ['name', 'user_id'])


def downgrade():
    with op.batch_alter_table('recipe', schema=None, naming_convention=naming_convention) as batch_op:
        batch_op.drop_constraint('uq_recipe_name_user', type_='unique')
        batch_op.create_unique_constraint('uq_recipe_name', ['name'])
        batch_op.drop_column('source_url')
        batch_op.drop_column('source')
        batch_op.drop_column('calories')
        batch_op.drop_column('difficulty')
        batch_op.drop_column('tips')
        batch_op.drop_column('description')
