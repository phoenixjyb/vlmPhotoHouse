"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2025-08-11

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('assets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('path', sa.String(), nullable=False, unique=True),
        sa.Column('hash_sha256', sa.String(64), nullable=False),
        sa.Column('perceptual_hash', sa.String(32)),
        sa.Column('mime', sa.String(64)),
        sa.Column('width', sa.Integer()),
        sa.Column('height', sa.Integer()),
        sa.Column('orientation', sa.Integer()),
        sa.Column('taken_at', sa.DateTime()),
        sa.Column('camera_make', sa.String(64)),
        sa.Column('camera_model', sa.String(64)),
        sa.Column('lens', sa.String(64)),
        sa.Column('iso', sa.Integer()),
        sa.Column('f_stop', sa.Float()),
        sa.Column('exposure', sa.String(32)),
        sa.Column('focal_length', sa.Float()),
        sa.Column('gps_lat', sa.Float()),
        sa.Column('gps_lon', sa.Float()),
        sa.Column('file_size', sa.Integer()),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('imported_at', sa.DateTime()),
        sa.Column('status', sa.String(16), index=True, default='active'),
    )
    op.create_index('ix_assets_path', 'assets', ['path'])
    op.create_index('ix_assets_hash', 'assets', ['hash_sha256'])

    op.create_table('embeddings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('modality', sa.String(16), nullable=False),
        sa.Column('model', sa.String(64), nullable=False),
        sa.Column('dim', sa.Integer(), nullable=False),
        sa.Column('storage_path', sa.String(), nullable=False),
        sa.Column('vector_checksum', sa.String(64)),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_index('idx_embeddings_asset_mod', 'embeddings', ['asset_id','modality'], unique=True)

    op.create_table('captions',
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('model', sa.String(64), nullable=False),
        sa.Column('user_edited', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table('persons',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('display_name', sa.String(128)),
        sa.Column('embedding_path', sa.String()),
        sa.Column('face_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table('face_detections',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('bbox_x', sa.Float(), nullable=False),
        sa.Column('bbox_y', sa.Float(), nullable=False),
        sa.Column('bbox_w', sa.Float(), nullable=False),
        sa.Column('bbox_h', sa.Float(), nullable=False),
        sa.Column('person_id', sa.Integer(), sa.ForeignKey('persons.id', ondelete='SET NULL'), index=True),
        sa.Column('embedding_path', sa.String()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('tasks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('type', sa.String(32), nullable=False, index=True),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('state', sa.String(16), nullable=False, server_default='pending', index=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text()),
        sa.Column('scheduled_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )
    op.create_index('idx_task_state_priority', 'tasks', ['state','priority','scheduled_at'])
    op.create_index('idx_task_type_state', 'tasks', ['type','state'])


def downgrade():
    op.drop_table('tasks')
    op.drop_table('face_detections')
    op.drop_table('persons')
    op.drop_table('captions')
    op.drop_index('idx_embeddings_asset_mod', table_name='embeddings')
    op.drop_table('embeddings')
    op.drop_index('ix_assets_hash', table_name='assets')
    op.drop_index('ix_assets_path', table_name='assets')
    op.drop_table('assets')
