"""Migration-only resumable transfer ledger; never created at application startup."""
from sqlalchemy import Column, ForeignKey, Index, Integer, Table, Text, CheckConstraint, UniqueConstraint


def add_resumable_table(metadata):
    table = Table('access_upload_transfers', metadata,
        Column('id', Text, primary_key=True, nullable=False),
        Column('account_id', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('request_id', Text, nullable=False), Column('batch', Text, nullable=False),
        Column('filename', Text, nullable=False), Column('bytes', Integer, nullable=False),
        Column('sha256', Text, nullable=False), Column('kind', Text, nullable=False),
        Column('offset', Integer, nullable=False), Column('state', Text, nullable=False),
        Column('asset_id', Integer, ForeignKey('assets.id')), Column('created_at', Integer, nullable=False),
        UniqueConstraint('account_id', 'request_id'),
        CheckConstraint("state IN ('uploading','complete','cancelled')"),
        CheckConstraint("kind IN ('image','video')"),
        CheckConstraint('bytes > 0 AND offset >= 0 AND offset <= bytes'),
        CheckConstraint("(state='complete' AND asset_id IS NOT NULL) OR (state!='complete' AND asset_id IS NULL)"))
    Index('ix_access_upload_transfers_account', table.c.account_id, table.c.created_at)
    return table
