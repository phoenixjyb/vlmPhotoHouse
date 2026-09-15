"""Independent family stories and atomic revisions; preserves every AI/legacy row."""
from alembic import op
from sqlalchemy import MetaData, Column, Integer, Text, Table
from app.access.story_schema import add_story_tables

revision = 'c7f4a9e2b610'
down_revision = 'b6e3f9a5c721'
branch_labels = None
depends_on = None


def upgrade():
    metadata = MetaData()
    # Foreign-key targets only: never create or modify these existing tables.
    Table('assets', metadata, Column('id', Integer, primary_key=True))
    for name in ('access_libraries', 'access_accounts'):
        Table(name, metadata, Column('id', Text, primary_key=True))
    for table in add_story_tables(metadata):
        table.create(op.get_bind())


def downgrade():
    raise RuntimeError('Story downgrade requires reviewed offline backup restoration; keep access closed')
