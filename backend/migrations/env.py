"""Explicit migration target and transactional SQLite DDL/revision bookkeeping."""
from contextlib import nullcontext
import os
from pathlib import Path
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config
supplied_connection = config.attributes.get('connection')
# A supplied connection is authoritative. Tests/embedded callers cannot be
# redirected to a real database by an unrelated DATABASE_URL environment value.
if supplied_connection is None:
    runtime_db_url = os.getenv('DATABASE_URL')
    if runtime_db_url:
        config.set_main_option('sqlalchemy.url', runtime_db_url.replace('%', '%%'))
    if not config.get_main_option('sqlalchemy.url'):
        raise RuntimeError('Explicit migration database URL or connection required')

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

backend_dir = str(Path(__file__).resolve().parents[1])
if backend_dir not in sys.path:
    sys.path.append(backend_dir)
from app import db
from app.access.metadata import migration_metadata

target_metadata = migration_metadata(db.Base.metadata)


def migrate_connection(connection):
    sqlite = connection.dialect.name == 'sqlite'
    if sqlite:
        driver = connection.connection.driver_connection
        if not driver.in_transaction:
            driver.execute('PRAGMA foreign_keys=ON')
        if driver.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
            raise RuntimeError('SQLite migrations require foreign_keys=ON before the transaction')
    # Respect an embedding caller's transaction; otherwise own and commit one.
    with nullcontext() if connection.in_transaction() else connection.begin():
        if sqlite and not driver.in_transaction:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        context.configure(connection=connection, target_metadata=target_metadata,
                          transactional_ddl=True if sqlite else None)
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_online():
    if supplied_connection is not None:
        migrate_connection(supplied_connection)
        return
    engine = engine_from_config(config.get_section(config.config_ini_section, {}),
                                prefix='sqlalchemy.', poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            migrate_connection(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError('Offline SQL generation is unsupported; rehearse on explicit synthetic SQLite')
else:
    run_migrations_online()
