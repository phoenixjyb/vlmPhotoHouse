"""Durable offline provisioning receipts; no access or asset grants."""
from alembic import op
import sqlalchemy as sa

revision = 'b6e3f9a5c721'
down_revision = 'a5d2e8f4b610'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('access_provisioning_receipts',
        sa.Column('plan_id', sa.Text(), primary_key=True, nullable=False),
        sa.Column('plan_digest', sa.Text(), nullable=False, unique=True),
        sa.Column('receipt', sa.Text(), nullable=False))


def downgrade():
    raise RuntimeError('Receipt downgrade requires reviewed offline backup restoration; keep access closed')
