"""add task timing columns

Revision ID: 7c1c2d4e5f6a
Revises: 6f2a8c1d9b7e
Create Date: 2025-08-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7c1c2d4e5f6a'
down_revision = '6f2a8c1d9b7e'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {col['name'] for col in insp.get_columns('tasks')}
    existing_indexes = {ix['name'] for ix in insp.get_indexes('tasks')}

    if 'started_at' not in existing_cols:
        op.add_column('tasks', sa.Column('started_at', sa.DateTime(), nullable=True))
    if 'finished_at' not in existing_cols:
        op.add_column('tasks', sa.Column('finished_at', sa.DateTime(), nullable=True))

    if 'ix_tasks_started_at' not in existing_indexes:
        op.create_index('ix_tasks_started_at', 'tasks', ['started_at'])
    if 'ix_tasks_finished_at' not in existing_indexes:
        op.create_index('ix_tasks_finished_at', 'tasks', ['finished_at'])

def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {col['name'] for col in insp.get_columns('tasks')}
    existing_indexes = {ix['name'] for ix in insp.get_indexes('tasks')}

    if 'ix_tasks_started_at' in existing_indexes:
        op.drop_index('ix_tasks_started_at', table_name='tasks')
    if 'ix_tasks_finished_at' in existing_indexes:
        op.drop_index('ix_tasks_finished_at', table_name='tasks')

    if 'started_at' in existing_cols:
        op.drop_column('tasks', 'started_at')
    if 'finished_at' in existing_cols:
        op.drop_column('tasks', 'finished_at')
