"""Member uploads: an account display name, and per-upload provenance.

Both changes are additive. `display_name` is **nullable on purpose**: accounts created before
this revision have no name, and the deployed owner is one of them. The application requires a
name at registration and lets an operator set one afterwards, and the incoming-folder label
falls back to the account id while a name is absent — so no existing account is invalidated by
this migration, and none is silently given a name it did not choose.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column, Integer, MetaData, Table, Text
from app.access.upload_schema import add_upload_tables

revision = 'f2a6d8b4c915'
down_revision = 'd8e5b2f7a904'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('access_accounts', sa.Column('display_name', sa.Text(), nullable=True))
    metadata = MetaData()
    Table('assets', metadata, Column('id', Integer, primary_key=True))
    Table('access_accounts', metadata, Column('id', Text, primary_key=True))
    for table in add_upload_tables(metadata):
        table.create(op.get_bind())


def downgrade():
    raise RuntimeError('Upload provenance downgrade requires reviewed offline backup restoration')
