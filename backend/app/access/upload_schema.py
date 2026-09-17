"""Migration-only schema for member uploads; no startup DDL.

An upload writes an `assets` row and this provenance row, and deliberately writes **no**
`access_asset_libraries` row: an incoming photo is in no library, so it is invisible to every
member until an operator promotes and assigns it.
"""
from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, Table, Text


def add_upload_tables(metadata):
    """The provenance row for one accepted upload.

    `incoming_label` is *stored*, not derived. It is a path component, so it must not change
    when an account is renamed: recomputing it would either move a folder or leave the stored
    path pointing at a name that no longer matches.

    `asset_id` is unique, so one asset has at most one provenance row and a retried upload can
    be recognised rather than duplicated.
    """
    uploads = Table('access_uploads', metadata,
        Column('id', Integer, primary_key=True, nullable=False),
        Column('asset_id', Integer, ForeignKey('assets.id'), nullable=False, unique=True),
        Column('account_id', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('incoming_label', Text, nullable=False),
        Column('batch', Text, nullable=False),
        Column('original_name', Text, nullable=False),
        Column('sha256', Text, nullable=False),
        Column('bytes', Integer, nullable=False),
        Column('state', Text, nullable=False),
        Column('created_at', Integer, nullable=False),
        CheckConstraint("state IN ('incoming','assigned')"),
        CheckConstraint('bytes >= 0'))
    Index('ix_access_uploads_account', uploads.c.account_id, uploads.c.id)
    Index('ix_access_uploads_state', uploads.c.state, uploads.c.id)
    return [uploads]
