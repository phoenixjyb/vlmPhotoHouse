"""Add persistent draft albums and ordered album assets.

Revision ID: d2b7e4f6a901
Revises: c4e7a2d9f1b3
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = 'd2b7e4f6a901'
down_revision = 'c4e7a2d9f1b3'
branch_labels = None
depends_on = None


def upgrade():  # pragma: no cover - migration side effects
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if 'albums' not in tables:
        op.create_table(
            'albums',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('title', sa.String(length=160), nullable=False),
            sa.Column('title_zh', sa.String(length=160), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('theme', sa.String(length=32), nullable=False, server_default='custom'),
            sa.Column('status', sa.String(length=16), nullable=False, server_default='draft'),
            sa.Column('cover_asset_id', sa.Integer(), sa.ForeignKey('assets.id', ondelete='SET NULL'), nullable=True),
            sa.Column('source_kind', sa.String(length=32), nullable=True),
            sa.Column('source_ref', sa.String(length=160), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        )
        op.create_index('ix_albums_theme', 'albums', ['theme'])
        op.create_index('ix_albums_status', 'albums', ['status'])
        op.create_index('ix_albums_cover_asset_id', 'albums', ['cover_asset_id'])

    tables = set(sa.inspect(bind).get_table_names())
    if 'album_assets' not in tables:
        op.create_table(
            'album_assets',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('album_id', sa.Integer(), sa.ForeignKey('albums.id', ondelete='CASCADE'), nullable=False),
            sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('position', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
            sa.UniqueConstraint('album_id', 'asset_id', name='uq_album_asset'),
            sa.UniqueConstraint('album_id', 'position', name='uq_album_asset_position'),
        )
        op.create_index('ix_album_assets_album_id', 'album_assets', ['album_id'])
        op.create_index('ix_album_assets_asset_id', 'album_assets', ['asset_id'])


def downgrade():  # pragma: no cover - migration side effects
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if 'album_assets' in tables:
        op.drop_table('album_assets')
    if 'albums' in tables:
        op.drop_table('albums')
