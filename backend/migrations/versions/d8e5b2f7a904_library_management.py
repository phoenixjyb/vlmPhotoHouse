"""Explicit people/album ownership; existing unowned records stay unclaimed."""
from alembic import op
from sqlalchemy import MetaData, Table, Column, Integer, Text
from app.access.management_schema import add_management_tables

revision = 'd8e5b2f7a904'
down_revision = 'c7f4a9e2b610'
branch_labels = None
depends_on = None


def upgrade():
    metadata = MetaData()
    for name in ('persons', 'albums'):
        Table(name, metadata, Column('id', Integer, primary_key=True))
    for name in ('access_libraries', 'access_accounts'):
        Table(name, metadata, Column('id', Text, primary_key=True))
    for table in add_management_tables(metadata):
        table.create(op.get_bind())


def downgrade():
    raise RuntimeError('Management ownership downgrade requires reviewed offline backup restoration')
