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
    with op.batch_alter_table('tasks') as batch_op:
        batch_op.add_column(sa.Column('started_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('finished_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_tasks_started_at', ['started_at'])
        batch_op.create_index('ix_tasks_finished_at', ['finished_at'])

def downgrade():
    with op.batch_alter_table('tasks') as batch_op:
        batch_op.drop_index('ix_tasks_started_at')
        batch_op.drop_index('ix_tasks_finished_at')
        batch_op.drop_column('started_at')
        batch_op.drop_column('finished_at')
