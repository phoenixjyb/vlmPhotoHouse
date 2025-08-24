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
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {col['name'] for col in insp.get_columns('embeddings')}
    if 'device' not in existing_cols:
        op.add_column('embeddings', sa.Column('device', sa.String(length=16), nullable=True))
    if 'model_version' not in existing_cols:
        op.add_column('embeddings', sa.Column('model_version', sa.String(length=64), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {col['name'] for col in insp.get_columns('embeddings')}
    if 'device' in existing_cols:
        op.drop_column('embeddings', 'device')
    if 'model_version' in existing_cols:
        op.drop_column('embeddings', 'model_version')
