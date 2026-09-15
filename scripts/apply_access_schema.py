#!/usr/bin/env python3
"""Explicit offline additive schema application, with transactional rollback.

Read-only review by default. Does not stop services, checkpoint WAL, make backups,
provision accounts, start listeners, replace files or activate an HTTP application.
"""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rehearse_fullsize_database as full

FROM_REVISION = 'd2b7e4f6a901'
TO_REVISION = 'c7f4a9e2b610'


def _source(db, budget):
    if full.validate(db, budget) != FROM_REVISION:
        raise full.small.Refused('Reviewed pre-access revision required')
    tables = full.schema(db)
    if any(name.startswith('access_') for name in tables):
        raise full.small.Refused('Existing authentication state requires separate review')
    if 'tasks' not in tables or db.execute("SELECT 1 FROM tasks WHERE state='running' LIMIT 1").fetchone():
        raise full.small.Refused('All running tasks must be drained')
    return tables


def review(database, backup, digest, budget):
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise full.small.Refused('Exact reviewed backup digest required')
    identity = full.small.identity(database)
    backup_identity = full.small.identity(backup)
    if identity == backup_identity or database == backup:
        raise full.small.Refused('Separate backup required')
    with full.read_source(database, budget, offline=True) as source:
        tables = _source(source, budget)
        if full.fingerprint(source, tables, budget)[0] != digest:
            raise full.small.Refused('Source changed since backup')
        with full.read_source(backup, budget, offline=True) as saved:
            if _source(saved, budget) != tables or full.fingerprint(saved, tables, budget)[0] != digest:
                raise full.small.Refused('Reviewed backup mismatch')
    return identity, backup_identity


def apply(database, backup, digest, budget, *, execute=False, all_writers_stopped=False):
    if execute and not all_writers_stopped:
        raise full.small.Refused('Independent all-writer shutdown confirmation required')
    identity, backup_identity = review(database, backup, digest, budget)
    if not execute:
        return {'reviewed': True, 'applied': False, 'source_revision': FROM_REVISION,
                'target_revision': TO_REVISION, 'operational_quiescence_verified': False}
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    from alembic import command
    from app.access.runtime import REQUIRED_REVISION, REQUIRED_TABLES
    if REQUIRED_REVISION != TO_REVISION:
        raise full.small.Refused('Unexpected application schema target')

    def connect():
        full.small.no_sidecars(database)
        if full.small.identity(database) != identity:
            raise full.small.Refused('Target replaced')
        db = sqlite3.connect(database.as_uri() + '?mode=rw', uri=True, timeout=3)
        budget.configure(db)
        db.execute('PRAGMA synchronous=FULL')
        if db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
            db.close()
            raise full.small.Refused('Offline DELETE journal required')
        return db

    engine = create_engine('sqlite://', creator=connect, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            driver = connection.connection.driver_connection
            # In DELETE mode this excludes both competing readers and writers.
            # Operational shutdown is still required: a blocked process could
            # reconnect immediately after this transaction commits.
            connection.exec_driver_sql('BEGIN EXCLUSIVE')
            try:
                tables = _source(driver, budget)
                if full.fingerprint(driver, tables, budget)[0] != digest:
                    raise full.small.Refused('Target changed after review')
                with full.read_source(backup, budget, offline=True) as saved:
                    if full.small.identity(backup) != backup_identity or full.fingerprint(saved, tables, budget)[0] != digest:
                        raise full.small.Refused('Backup changed after review')
                preserved = {name: columns for name, columns in tables.items() if name != 'alembic_version'}
                expected, counts = full.fingerprint(driver, preserved, budget)
                config = full.small.migration_config()
                config.attributes['connection'] = connection
                command.upgrade(config, TO_REVISION)
                if (not driver.in_transaction or full.validate(driver, budget) != TO_REVISION
                        or not REQUIRED_TABLES <= set(full.schema(driver))):
                    raise full.small.Refused('Incomplete transactional migration')
                if full.fingerprint(driver, preserved, budget)[0] != expected:
                    raise full.small.Refused('Existing data changed')
                for table in ('access_accounts', 'access_libraries', 'access_sessions', 'access_asset_libraries'):
                    if driver.execute('SELECT count(*) FROM ' + table).fetchone()[0]:
                        raise full.small.Refused('Unexpected access grant')
                if full.small.identity(database) != identity or full.small.identity(backup) != backup_identity:
                    raise full.small.Refused('Reviewed files replaced')
                budget.check()
                connection.commit()
            except BaseException:
                # A timed-out SQL progress handler must not interrupt rollback.
                driver.set_progress_handler(None, 0)
                connection.rollback()
                raise
    finally:
        engine.dispose()
    # Result output is not a liveness receipt. On lost output, inspect the actual
    # schema and private controller receipt; never blindly replay or restore.
    return {'reviewed': True, 'applied': True, 'revision': TO_REVISION,
            'tables_preserved': len(counts), 'rows_preserved': sum(counts.values()),
            'accounts_created': 0, 'assets_mapped': 0, 'http_activated': False}


def main(argv=None):
    parser = full.small.Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--reviewed-backup-digest', required=True)
    parser.add_argument('--max-bytes', type=int, required=True)
    parser.add_argument('--timeout-seconds', type=int, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--all-writers-stopped', action='store_true')
    try:
        args = parser.parse_args(argv)
        result = apply(args.database, args.backup, args.reviewed_backup_digest,
                       full.Budget(args.max_bytes, args.timeout_seconds),
                       execute=args.execute, all_writers_stopped=args.all_writers_stopped)
        print(json.dumps(result, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print('Migration interrupted; inspect schema and controller receipt before retrying.', file=sys.stderr)
        return 130
    except Exception:
        print('Migration refused or incomplete; inspect schema and controller receipt before retrying.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
