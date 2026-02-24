"""Add face assignment events audit table

Revision ID: a1c9d4e5f8b2
Revises: 9b1e7d2a5c6f
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa


revision = 'a1c9d4e5f8b2'
down_revision = '9b1e7d2a5c6f'
branch_labels = None
depends_on = None


def upgrade():  # pragma: no cover - migration side effects
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'face_assignment_events' in insp.get_table_names():
        return

    op.create_table(
        'face_assignment_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('face_id', sa.Integer(), nullable=True),
        sa.Column('asset_id', sa.Integer(), nullable=True),
        sa.Column('old_person_id', sa.Integer(), nullable=True),
        sa.Column('new_person_id', sa.Integer(), nullable=True),
        sa.Column('old_label_source', sa.String(length=16), nullable=True),
        sa.Column('new_label_source', sa.String(length=16), nullable=True),
        sa.Column('old_label_score', sa.Float(), nullable=True),
        sa.Column('new_label_score', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('reason', sa.String(length=64), nullable=True),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('actor', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    )
    op.create_index('ix_face_assignment_events_face_id', 'face_assignment_events', ['face_id'])
    op.create_index('ix_face_assignment_events_asset_id', 'face_assignment_events', ['asset_id'])
    op.create_index('ix_face_assignment_events_old_person_id', 'face_assignment_events', ['old_person_id'])
    op.create_index('ix_face_assignment_events_new_person_id', 'face_assignment_events', ['new_person_id'])
    op.create_index('ix_face_assignment_events_source', 'face_assignment_events', ['source'])
    op.create_index('ix_face_assignment_events_task_id', 'face_assignment_events', ['task_id'])
    op.create_index('ix_face_assignment_events_created_at', 'face_assignment_events', ['created_at'])
    op.create_index(
        'idx_face_assignment_events_face_created',
        'face_assignment_events',
        ['face_id', 'created_at'],
    )
    op.create_index(
        'idx_face_assignment_events_person_created',
        'face_assignment_events',
        ['new_person_id', 'created_at'],
    )


def downgrade():  # pragma: no cover - reversal best-effort
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'face_assignment_events' not in insp.get_table_names():
        return
    op.drop_table('face_assignment_events')

