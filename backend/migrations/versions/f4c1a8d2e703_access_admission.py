"""Add durable account admission, without modifying accounts or granting access."""

revision = 'f4c1a8d2e703'
down_revision = 'e3a9b1c7d402'
branch_labels = None
depends_on = None


def upgrade():
    from alembic import op
    from app.access.admission import apply_schema

    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        raise RuntimeError('Access admission migration currently requires SQLite')
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    apply_schema(bind.exec_driver_sql)


def downgrade():
    raise RuntimeError('Access downgrade requires reviewed offline backup restoration; keep access closed')
