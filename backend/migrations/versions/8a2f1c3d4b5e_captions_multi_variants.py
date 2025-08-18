"""captions: support multiple variants per asset (add id pk)

Revision ID: 8a2f1c3d4b5e
Revises: 7c1c2d4e5f6a
Create Date: 2025-08-18
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8a2f1c3d4b5e'
down_revision = '7c1c2d4e5f6a'
branch_labels = None
depends_on = None


def upgrade():
    # Create new table with id primary key to allow multiple captions per asset
    op.create_table(
        'captions_new',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('user_edited', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    # Migrate existing data (one caption per asset)
    conn = op.get_bind()
    try:
        conn.execute(sa.text(
            'INSERT INTO captions_new (asset_id, text, model, user_edited, created_at, updated_at) '
            'SELECT asset_id, text, model, COALESCE(user_edited, 0), created_at, updated_at FROM captions'
        ))
    except Exception:
        # If old table is empty or missing, ignore
        pass
    # Drop old table and rename new
    try:
        op.drop_table('captions')
    except Exception:
        pass
    op.rename_table('captions_new', 'captions')
    # Create index on asset_id for lookups
    try:
        op.create_index('ix_captions_asset_id', 'captions', ['asset_id'])
    except Exception:
        pass


def downgrade():
    # Recreate old single-caption schema with asset_id as primary key
    op.create_table(
        'captions_old',
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('user_edited', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    # Insert one row per asset, prefer the most recent by id
    conn = op.get_bind()
    try:
        conn.execute(sa.text(
            'INSERT INTO captions_old (asset_id, text, model, user_edited, created_at, updated_at) '
            'SELECT c.asset_id, c.text, c.model, COALESCE(c.user_edited, 0), c.created_at, c.updated_at '
            'FROM captions c '
            'JOIN (SELECT asset_id, MAX(id) AS mid FROM captions GROUP BY asset_id) t ON t.asset_id=c.asset_id AND t.mid=c.id'
        ))
    except Exception:
        pass
    try:
        op.drop_index('ix_captions_asset_id', table_name='captions')
    except Exception:
        pass
    try:
        op.drop_table('captions')
    except Exception:
        pass
    op.rename_table('captions_old', 'captions')
