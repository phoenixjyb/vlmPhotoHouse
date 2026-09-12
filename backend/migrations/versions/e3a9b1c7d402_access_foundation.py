"""Add dormant account/library access records; do not grant legacy media access.

Revision ID: e3a9b1c7d402
Revises: d2b7e4f6a901
"""

revision = 'e3a9b1c7d402'
down_revision = 'd2b7e4f6a901'
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op
    from app.access.schema import apply_schema

    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        raise RuntimeError('Access foundation migration currently requires SQLite')
    # sqlite3 legacy transaction mode does not BEGIN for CREATE TABLE. Keep DDL
    # and the revision ledger in the same transaction. Alembic owns the commit.
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    apply_schema(bind.exec_driver_sql)


def downgrade():
    # Dropping membership/revocation history can reopen access through older code.
    raise RuntimeError('Access downgrade requires reviewed offline backup restoration; keep access closed')
