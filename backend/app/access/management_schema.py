"""Migration-only ownership for retained people and albums; no startup DDL."""
from sqlalchemy import Column, ForeignKey, Index, Integer, Table, Text, CheckConstraint


def add_management_tables(metadata):
    result = []
    for kind, target in (('person', 'persons'), ('album', 'albums')):
        table = Table('access_' + kind + '_libraries', metadata,
            Column(kind + '_id', Integer, ForeignKey(target + '.id'), primary_key=True, nullable=False),
            Column('library_id', Text, ForeignKey('access_libraries.id'), nullable=False),
            Column('creator_id', Text, ForeignKey('access_accounts.id'), nullable=False),
            *([Column('mutation_id', Text, unique=True), Column('creation_digest', Text)] if kind == 'album' else []),
            Column('revision', Integer, nullable=False), CheckConstraint('revision > 0'))
        Index('ix_access_' + kind + '_library', table.c.library_id, table.c[kind + '_id'])
        result.append(table)
    return result
