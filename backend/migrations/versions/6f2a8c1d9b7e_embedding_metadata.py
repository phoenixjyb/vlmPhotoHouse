"""add embedding device and model_version

Revision ID: 6f2a8c1d9b7e
Revises: 5b6b4d1c2a3f
Create Date: 2025-08-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '6f2a8c1d9b7e'
down_revision = '5b6b4d1c2a3f'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('embeddings') as batch_op:
        batch_op.add_column(sa.Column('device', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('model_version', sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table('embeddings') as batch_op:
        batch_op.drop_column('device')
        batch_op.drop_column('model_version')
