#!/usr/bin/env python3
"""Explicit offline initialization, backup, rehearsal and quarantined candidates.

No existing-database writes, implicit targets, service control or cutover.
Requires a trusted private directory and a quiescent rollback-journal database.
"""
import argparse
from contextlib import closing, contextmanager
import hashlib
import json
import os
import re
from pathlib import Path
import sqlite3
import stat
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
MAX_DATABASE_BYTES = 64 * 1024 * 1024
MAX_SECONDS = 30
SIDECARS = ('-wal', '-shm', '-journal')


class Refused(RuntimeError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('Invalid arguments')


def direct(path):
    if (not path.is_absolute() or '..' in path.parts or path.anchor.startswith(('//', '\\\\'))
            or path.parent.resolve(strict=True) != path.parent):
        raise Refused('Explicit direct local path required')
    return path


def no_sidecars(path):
    if any(os.path.lexists(str(path) + suffix) for suffix in SIDECARS):
        raise Refused('Quiescent database required')


def identity(path):
    direct(path)
    record = path.lstat()
    if not stat.S_ISREG(record.st_mode) or path.resolve(strict=True) != path:
        raise Refused('Direct regular database required')
    return record.st_dev, record.st_ino


def configure(db):
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA trusted_schema=OFF')
    db.execute('PRAGMA temp_store=MEMORY')
    deadline = time.monotonic() + MAX_SECONDS

    def expired():
        return time.monotonic() > deadline

    db.set_progress_handler(expired, 10000)
    return expired


def copy_database(source, destination):
    deadline = time.monotonic() + MAX_SECONDS

    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise Refused('Snapshot time budget exceeded')

    source.backup(destination, pages=128, progress=progress, sleep=0.01)


def migration_config():
    from alembic.config import Config
    config = Config()
    config.set_main_option('script_location', str(ROOT / 'backend/migrations'))
    return config


def revision(db):
    from alembic.script import ScriptDirectory
    versions = db.execute('SELECT version_num FROM alembic_version').fetchall()
    known = {item.revision for item in ScriptDirectory.from_config(migration_config()).walk_revisions()}
    if len(versions) != 1 or versions[0][0] not in known:
        raise Refused('Known single schema revision required')
    return versions[0][0]


def validate(db):
    if db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0] > MAX_DATABASE_BYTES:
        raise Refused('Database exceeds rehearsal size budget')
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise Refused('Database integrity failure')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise Refused('Database foreign key failure')
    return revision(db)


def snapshot_digest(db):
    digest = hashlib.sha256(b'photohouse-offline-snapshot-v1\0')
    for line in db.iterdump():
        digest.update(line.encode('utf-8')); digest.update(b'\n')
    return digest.hexdigest()


@contextmanager
def source_snapshot(path):
    before = identity(path)
    no_sidecars(path)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)) as source:
        configure(source)
        source.execute('PRAGMA query_only=ON')
        source.execute('BEGIN')
        if source.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
            raise Refused('Offline rollback journal database required')
        validate(source)
        with closing(sqlite3.connect(':memory:')) as snapshot:
            configure(snapshot)
            copy_database(source, snapshot)
            validate(snapshot)
            if snapshot_digest(source) != snapshot_digest(snapshot) or identity(path) != before:
                raise Refused('Source identity or snapshot mismatch')
            no_sidecars(path)
            yield snapshot
            if identity(path) != before:
                raise Refused('Source identity changed')
            no_sidecars(path)


def upgrade_memory(db):
    """Only called with an owned in-memory copy; supplied connection ignores env."""
    if any(row[2] for row in db.execute('PRAGMA database_list')):
        raise Refused('Migration requires an in-memory database')
    from alembic import command
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.access.runtime import REQUIRED_REVISION, REQUIRED_TABLES
    # SQLAlchemy owns a second in-memory connection, preserving caller ownership.
    engine = create_engine('sqlite://', poolclass=StaticPool)
    try:
        with engine.connect() as connection:
            driver = connection.connection.driver_connection
            configure(driver)
            copy_database(db, driver)
            config = migration_config()
            config.attributes['connection'] = connection
            command.upgrade(config, REQUIRED_REVISION)
            if validate(driver) != REQUIRED_REVISION:
                raise Refused('Unexpected migrated revision')
            tables = {row[0] for row in driver.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not REQUIRED_TABLES <= tables:
                raise Refused('Incomplete migrated schema')
            if driver.execute('SELECT typeof(secret),length(secret) FROM access_admission_key WHERE id=1').fetchone() != ('blob', 32):
                raise Refused('Invalid admission key')
            copy_database(driver, db)
    finally:
        engine.dispose()


def write_new(snapshot, path):
    direct(path)
    no_sidecars(path)
    expected = snapshot_digest(snapshot)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    # Retain a private incomplete file on failure: never delete or overwrite it.
    with os.fdopen(os.open(path, flags, 0o600), 'r+b') as reserved:
        record = os.fstat(reserved.fileno())
        expected_identity = record.st_dev, record.st_ino
        if identity(path) != expected_identity:
            raise Refused('Output identity changed')
        with closing(sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=3)) as output:
            configure(output)
            if identity(path) != expected_identity:
                raise Refused('Output identity changed')
            copy_database(snapshot, output)
            validate(output)
            # Restore into memory and check logical equality without activating it.
            with closing(sqlite3.connect(':memory:')) as restored:
                configure(restored)
                copy_database(output, restored)
                validate(restored)
                if snapshot_digest(restored) != expected:
                    raise Refused('Backup restoration mismatch')
        os.fsync(reserved.fileno())
        if identity(path) != expected_identity:
            raise Refused('Output identity changed')
        no_sidecars(path)
        reserved.seek(0)
        file_digest = hashlib.file_digest(reserved, 'sha256').hexdigest()
    return {'output_sha256': file_digest, 'snapshot_digest': expected,
            'restore_verified_in_memory': True}


def migrate_candidate(args):
    """Apply migration to a new quarantined copy of an exact reviewed snapshot.

    References record external review; they neither authenticate the operator nor
    stop writers. Both input snapshots stay pinned until output verification ends.
    """
    from app.access.provisioning_apply import _reference
    from app.access.recovery import _quarantine_access_state, _assert_quarantined
    if not re.fullmatch('[0-9a-f]{64}', args.reviewed_snapshot_digest):
        raise Refused('Exact reviewed snapshot digest required')
    authority = _reference(args.authority_reference)
    quiescence = _reference(args.quiescence_reference)
    if identity(args.database) == identity(args.backup):
        raise Refused('Physically separate matching backup required')
    with source_snapshot(args.database) as db, source_snapshot(args.backup) as backup:
        source_digest = snapshot_digest(db)
        if source_digest != args.reviewed_snapshot_digest or snapshot_digest(backup) != source_digest:
            raise Refused('Source or backup differs from reviewed snapshot')
        source_revision = validate(db)
        upgrade_memory(db)
        receipt = {
            'version': 1, 'operation': 'prepare_quarantined_migration_candidate',
            'receipt_id': str(uuid.uuid4()), 'receipt_kind': 'unsigned_local_preparation',
            'source_revision': source_revision, 'revision': validate(db),
            'source_snapshot_digest': source_digest, 'backup_snapshot_digest': source_digest,
            'authority_reference': authority, 'quiescence_reference': quiescence,
            'access_reopened': False, 'existing_database_modified': False,
        }
        encoded = json.dumps(receipt, sort_keys=True, separators=(',', ':'))
        receipt_digest = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
        db.execute('BEGIN IMMEDIATE')
        try:
            key = _quarantine_access_state(db)
            db.execute('INSERT INTO access_provisioning_receipts VALUES (?,?,?)',
                       (receipt['receipt_id'], receipt_digest, encoded))
            _assert_quarantined(db, key)
            validate(db)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        result = write_new(db, args.out)
        return {**result, 'source_revision': source_revision, 'revision': receipt['revision'],
                'source_snapshot_digest': source_digest, 'backup_verified': True,
                'receipt_id': receipt['receipt_id'], 'receipt_digest': receipt_digest,
                'candidate_quarantined': True, 'access_reopened': False,
                'migration_applied_to_source': False}


def main(argv=None):
    parser = Parser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    init = sub.add_parser('initialize', allow_abbrev=False)
    init.add_argument('--out', type=Path, required=True)
    backup = sub.add_parser('backup', allow_abbrev=False)
    backup.add_argument('--database', type=Path, required=True)
    backup.add_argument('--out', type=Path, required=True)
    rehearse = sub.add_parser('rehearse-migration', allow_abbrev=False)
    rehearse.add_argument('--database', type=Path, required=True)
    candidate = sub.add_parser('migrate-candidate', allow_abbrev=False)
    candidate.add_argument('--database', type=Path, required=True)
    candidate.add_argument('--backup', type=Path, required=True)
    candidate.add_argument('--out', type=Path, required=True)
    candidate.add_argument('--reviewed-snapshot-digest', required=True)
    candidate.add_argument('--authority-reference', required=True)
    candidate.add_argument('--quiescence-reference', required=True)
    completed = False
    try:
        args = parser.parse_args(argv)
        if args.command == 'migrate-candidate':
            result = migrate_candidate(args)
        elif args.command == 'initialize':
            with closing(sqlite3.connect(':memory:')) as db:
                configure(db)
                upgrade_memory(db)
                result = {'revision': validate(db), **write_new(db, args.out)}
        else:
            with source_snapshot(args.database) as db:
                result = {'source_revision': validate(db), 'source_snapshot_digest': snapshot_digest(db)}
                if args.command == 'backup':
                    result.update(write_new(db, args.out))
                else:
                    upgrade_memory(db)
                    result.update({'revision': validate(db), 'migration_applied_to_source': False})
        completed = True
        print(json.dumps({'command': args.command, 'completed': True,
                          'existing_database_modified': False, **result}))
        return 0
    except KeyboardInterrupt:
        print('Interrupted; inspect any new output before reuse.', file=sys.stderr)
        return 130
    except Exception:
        # Includes SQLAlchemy/Alembic failures. Never echo paths, SQL, data or argv.
        print('Output failed after completion.' if completed else
              'Database preparation refused or incomplete; inspect any new output before reuse.', file=sys.stderr)
        return 3 if completed else 2


if __name__ == '__main__':
    raise SystemExit(main())
