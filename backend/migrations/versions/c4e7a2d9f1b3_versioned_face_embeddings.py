"""Add landmarks and versioned face embedding artifacts.

Revision ID: c4e7a2d9f1b3
Revises: a1c9d4e5f8b2
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = 'c4e7a2d9f1b3'
down_revision = 'a1c9d4e5f8b2'
branch_labels = None
depends_on = None


def upgrade():  # pragma: no cover - migration side effects
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    face_columns = {column['name'] for column in inspector.get_columns('face_detections')}
    if 'landmarks_json' not in face_columns:
        op.add_column('face_detections', sa.Column('landmarks_json', sa.JSON(), nullable=True))
    if 'landmark_model' not in face_columns:
        op.add_column('face_detections', sa.Column('landmark_model', sa.String(length=64), nullable=True))

    if 'face_embedding_artifacts' not in tables:
        op.create_table(
            'face_embedding_artifacts',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('face_id', sa.Integer(), sa.ForeignKey('face_detections.id', ondelete='CASCADE'), nullable=False),
            sa.Column('model', sa.String(length=128), nullable=False),
            sa.Column('model_version', sa.String(length=96), nullable=False),
            sa.Column('dim', sa.Integer(), nullable=False),
            sa.Column('alignment', sa.String(length=64), nullable=True),
            sa.Column('storage_path', sa.String(), nullable=False),
            sa.Column('vector_checksum', sa.String(length=64), nullable=True),
            sa.Column('status', sa.String(length=16), nullable=False, server_default='shadow'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
            sa.UniqueConstraint('face_id', 'model_version', name='uq_face_embedding_artifact_version'),
        )
        op.create_index('ix_face_embedding_artifacts_face_id', 'face_embedding_artifacts', ['face_id'])
        op.create_index('ix_face_embedding_artifacts_model_version', 'face_embedding_artifacts', ['model_version'])
        op.create_index('ix_face_embedding_artifacts_status', 'face_embedding_artifacts', ['status'])

    if 'person_embedding_artifacts' not in tables:
        op.create_table(
            'person_embedding_artifacts',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('person_id', sa.Integer(), sa.ForeignKey('persons.id', ondelete='CASCADE'), nullable=False),
            sa.Column('model', sa.String(length=128), nullable=False),
            sa.Column('model_version', sa.String(length=96), nullable=False),
            sa.Column('dim', sa.Integer(), nullable=False),
            sa.Column('source_face_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('storage_path', sa.String(), nullable=False),
            sa.Column('vector_checksum', sa.String(length=64), nullable=True),
            sa.Column('status', sa.String(length=16), nullable=False, server_default='shadow'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
            sa.UniqueConstraint('person_id', 'model_version', name='uq_person_embedding_artifact_version'),
        )
        op.create_index('ix_person_embedding_artifacts_person_id', 'person_embedding_artifacts', ['person_id'])
        op.create_index('ix_person_embedding_artifacts_model_version', 'person_embedding_artifacts', ['model_version'])
        op.create_index('ix_person_embedding_artifacts_status', 'person_embedding_artifacts', ['status'])


def downgrade():  # pragma: no cover - reversal best-effort
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if 'person_embedding_artifacts' in tables:
        op.drop_table('person_embedding_artifacts')
    if 'face_embedding_artifacts' in tables:
        op.drop_table('face_embedding_artifacts')

    face_columns = {column['name'] for column in inspector.get_columns('face_detections')}
    if 'landmark_model' in face_columns:
        op.drop_column('face_detections', 'landmark_model')
    if 'landmarks_json' in face_columns:
        op.drop_column('face_detections', 'landmarks_json')
