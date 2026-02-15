"""Add caption processing status fields and caption variant metadata

Revision ID: 9b1e7d2a5c6f
Revises: 8a2f1c3d4b5e
Create Date: 2025-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = '9b1e7d2a5c6f'
down_revision = '8a2f1c3d4b5e'
branch_labels = None
depends_on = None


def upgrade():  # pragma: no cover - migration side effects
    # Asset caption status fields
    with op.batch_alter_table('assets') as b:
        try:
            b.add_column(sa.Column('caption_processed', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        except Exception:
            pass
        try:
            b.add_column(sa.Column('caption_variant_count', sa.Integer(), nullable=False, server_default='0'))
        except Exception:
            pass
        try:
            b.add_column(sa.Column('caption_processed_at', sa.DateTime(), nullable=True))
        except Exception:
            pass
        try:
            b.add_column(sa.Column('caption_error_last', sa.Text(), nullable=True))
        except Exception:
            pass
        try:
            b.add_column(sa.Column('caption_model_profile_last', sa.String(length=32), nullable=True))
        except Exception:
            pass

    # Caption variant metadata (quality tier + superseded flag + model version)
    with op.batch_alter_table('captions') as b:
        try:
            b.add_column(sa.Column('quality_tier', sa.String(length=16), nullable=True))
        except Exception:
            pass
        try:
            b.add_column(sa.Column('model_version', sa.String(length=64), nullable=True))
        except Exception:
            pass
        try:
            b.add_column(sa.Column('superseded', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        except Exception:
            pass

    # Simple backfill: set caption_processed=true where captions exist
    try:
        op.execute("UPDATE assets SET caption_processed=1, caption_variant_count=(SELECT COUNT(1) FROM captions c WHERE c.asset_id=assets.id) WHERE EXISTS (SELECT 1 FROM captions c2 WHERE c2.asset_id=assets.id)")
    except Exception:
        pass


def downgrade():  # pragma: no cover - reversal best-effort
    with op.batch_alter_table('captions') as b:
        for col in ('quality_tier','model_version','superseded'):
            try:
                b.drop_column(col)
            except Exception:
                pass
    with op.batch_alter_table('assets') as b:
        for col in ('caption_processed','caption_variant_count','caption_processed_at','caption_error_last','caption_model_profile_last'):
            try:
                b.drop_column(col)
            except Exception:
                pass
