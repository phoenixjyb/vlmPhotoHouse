"""add task progress and cancel fields

Revision ID: 5b6b4d1c2a3f
Revises: 402a07259e4a
Create Date: 2025-08-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '5b6b4d1c2a3f'
down_revision = '402a07259e4a'
branch_labels = None
depends_on = None

def upgrade():
    # Use direct add_column to avoid SQLite batch circular dependency issues
    # Also guard with existence checks to be idempotent if partially applied.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {col['name'] for col in insp.get_columns('tasks')}

    if 'progress_current' not in existing_cols:
        op.add_column('tasks', sa.Column('progress_current', sa.Integer(), nullable=True))
    if 'progress_total' not in existing_cols:
        op.add_column('tasks', sa.Column('progress_total', sa.Integer(), nullable=True))
    if 'cancel_requested' not in existing_cols:
        op.add_column('tasks', sa.Column('cancel_requested', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {col['name'] for col in insp.get_columns('tasks')}

    if 'cancel_requested' in existing_cols:
        op.drop_column('tasks', 'cancel_requested')
    if 'progress_total' in existing_cols:
        op.drop_column('tasks', 'progress_total')
    if 'progress_current' in existing_cols:
        op.drop_column('tasks', 'progress_current')
