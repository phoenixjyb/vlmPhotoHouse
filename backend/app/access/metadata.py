"""SQLAlchemy migration metadata matching the explicitly migrated access schema.

Keep security tables out of legacy Base.metadata.create_all() call sites. Alembic
uses a combined copy; application imports do not import SQLAlchemy or this module.
"""
from sqlalchemy import (Column, ForeignKey, Index, Integer, LargeBinary, MetaData,
                        Table, Text, CheckConstraint, text)


def migration_metadata(legacy_metadata):
    metadata = MetaData()
    for table in legacy_metadata.sorted_tables:
        table.to_metadata(metadata)

    Table('access_accounts', metadata,
        Column('id', Text, primary_key=True, nullable=False),
        Column('phone_login', Text, nullable=False, unique=True),
        Column('password_hash', Text, nullable=False),
        Column('state', Text, nullable=False, server_default=text("'active'")),
        CheckConstraint("state IN ('active','disabled')"))
    Table('access_sessions', metadata,
        Column('digest', Text, primary_key=True, nullable=False),
        Column('account_id', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('expires_at', Integer, nullable=False),
        Column('revoked', Integer, nullable=False, server_default=text('0')),
        CheckConstraint('revoked IN (0,1)'))
    Table('access_operators', metadata,
        Column('account_id', Text, ForeignKey('access_accounts.id'), primary_key=True, nullable=False))
    Table('access_libraries', metadata,
        Column('id', Text, primary_key=True, nullable=False),
        Column('state', Text, nullable=False, server_default=text("'active'")),
        Column('bootstrap_operator', Text, ForeignKey('access_accounts.id'), nullable=False),
        CheckConstraint("state IN ('active','closed')"))
    Table('access_memberships', metadata,
        Column('account_id', Text, ForeignKey('access_accounts.id'), primary_key=True, nullable=False),
        Column('library_id', Text, ForeignKey('access_libraries.id'), primary_key=True, nullable=False),
        Column('status', Text, nullable=False), Column('role', Text, nullable=False),
        Column('revision', Integer, nullable=False), Column('expires_at', Integer),
        Column('originals', Integer, nullable=False, server_default=text('0')),
        Column('approved_by', Text, ForeignKey('access_accounts.id')),
        CheckConstraint("status IN ('requested','approved','rejected','revoked')"),
        CheckConstraint("role IN ('viewer','contributor','owner')"),
        CheckConstraint('revision > 0'), CheckConstraint('originals IN (0,1)'),
        CheckConstraint("status != 'approved' OR approved_by IS NOT NULL"))
    invitations = Table('access_invitations', metadata,
        Column('digest', Text, primary_key=True, nullable=False),
        Column('library_id', Text, ForeignKey('access_libraries.id'), nullable=False),
        Column('target_phone', Text, nullable=False),
        Column('target_account', Text, ForeignKey('access_accounts.id')),
        Column('inviter_account', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('inviter_revision', Integer, nullable=False), Column('target_revision', Integer, nullable=False),
        Column('expires_at', Integer, nullable=False),
        Column('consumed', Integer, nullable=False, server_default=text('0')),
        Column('cancelled', Integer, nullable=False, server_default=text('0')),
        CheckConstraint('consumed IN (0,1)'), CheckConstraint('cancelled IN (0,1)'))
    Index('ix_access_invitation_target', invitations.c.library_id, invitations.c.target_phone)
    assets = Table('access_asset_libraries', metadata,
        # Match existing SQLite INTEGER PRIMARY KEY DDL and reflection exactly.
        Column('asset_id', Integer, ForeignKey('assets.id'), primary_key=True, nullable=True),
        Column('library_id', Text, ForeignKey('access_libraries.id'), nullable=False))
    Index('ix_access_assets_library', assets.c.library_id, assets.c.asset_id)
    Table('access_audit', metadata,
        Column('id', Integer, primary_key=True, nullable=True),
        Column('actor_account', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('action', Text, nullable=False),
        Column('library_id', Text, ForeignKey('access_libraries.id')),
        Column('target_account', Text, ForeignKey('access_accounts.id')),
        Column('occurred_at', Integer, nullable=False))
    Table('access_admission_key', metadata,
        Column('id', Integer, primary_key=True, nullable=True),
        Column('secret', LargeBinary, nullable=False),
        CheckConstraint('id=1'), CheckConstraint('length(secret)=32'))
    Table('access_attempts', metadata,
        Column('bucket', Text, primary_key=True, nullable=False),
        Column('expires_at', Integer, nullable=False),
        Column('attempts', Integer, nullable=False), CheckConstraint('attempts > 0'))
    Table('access_kdf_slot', metadata,
        Column('id', Integer, primary_key=True, nullable=True),
        Column('claim', Text, nullable=False), CheckConstraint('id=1'))
    Table('access_provisioning_receipts', metadata,
        Column('plan_id', Text, primary_key=True, nullable=False),
        Column('plan_digest', Text, nullable=False, unique=True),
        Column('receipt', Text, nullable=False))
    return metadata
