"""Migration-only story metadata. Never create tables on application startup."""
from sqlalchemy import Column, ForeignKey, Index, Integer, Table, Text, CheckConstraint


def add_story_tables(metadata):
    stories = Table('access_stories', metadata,
        Column('id', Text, primary_key=True, nullable=False),
        Column('asset_id', Integer, ForeignKey('assets.id'), nullable=False),
        Column('library_id', Text, ForeignKey('access_libraries.id'), nullable=False),
        Column('author_id', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('revision', Integer, nullable=False),
        Column('title', Text, nullable=False), Column('text', Text, nullable=False),
        Column('language', Text, nullable=False), Column('byline', Text, nullable=False),
        Column('created_at', Integer, nullable=False), Column('updated_at', Integer, nullable=False),
        Column('deleted', Integer, nullable=False),
        CheckConstraint('revision > 0'), CheckConstraint('deleted IN (0,1)'))
    Index('ix_access_stories_asset', stories.c.library_id, stories.c.asset_id, stories.c.id)
    revisions = Table('access_story_revisions', metadata,
        Column('story_id', Text, ForeignKey('access_stories.id'), primary_key=True, nullable=False),
        Column('revision', Integer, primary_key=True, nullable=False),
        Column('editor_id', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('mutation_id', Text, nullable=False),
        Column('request_digest', Text, nullable=False),
        Column('title', Text, nullable=False), Column('text', Text, nullable=False),
        Column('language', Text, nullable=False), Column('byline', Text, nullable=False),
        Column('occurred_at', Integer, nullable=False), Column('deleted', Integer, nullable=False),
        CheckConstraint('revision > 0'), CheckConstraint('deleted IN (0,1)'))
    Index('ix_access_story_mutation', revisions.c.editor_id, revisions.c.mutation_id, unique=True)
    return stories, revisions
