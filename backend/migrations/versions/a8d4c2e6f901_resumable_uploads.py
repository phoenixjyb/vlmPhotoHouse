"""Account-bound resumable uploads; additive ledger, no media or account changes."""
from alembic import op
from sqlalchemy import MetaData, Table, Column, Integer, Text
from app.access.resumable_schema import add_resumable_table
revision = 'a8d4c2e6f901'
down_revision = 'f2a6d8b4c915'
branch_labels = None
depends_on = None


def upgrade():
    metadata = MetaData()
    Table('assets', metadata, Column('id', Integer, primary_key=True))
    Table('access_accounts', metadata, Column('id', Text, primary_key=True))
    add_resumable_table(metadata).create(op.get_bind())


def downgrade():
    raise RuntimeError('Upload transfer ledger downgrade requires reviewed offline backup restoration')
