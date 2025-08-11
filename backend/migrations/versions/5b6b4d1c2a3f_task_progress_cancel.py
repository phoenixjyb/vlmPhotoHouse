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
    with op.batch_alter_table('tasks') as batch_op:
        batch_op.add_column(sa.Column('progress_current', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('progress_total', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('cancel_requested', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade():
    with op.batch_alter_table('tasks') as batch_op:
        batch_op.drop_column('progress_current')
        batch_op.drop_column('progress_total')
        batch_op.drop_column('cancel_requested')
