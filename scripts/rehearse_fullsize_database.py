#!/usr/bin/env python3
"""Disk-backed, copy-only preparation. Never activate a database or stop a worker.

snapshot accepts a live WAL source; rehearse accepts only a reviewed offline copy.
Outputs and partial failures are retained privately, never overwritten or removed.
"""
import argparse
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_access_database as small

QUARANTINE_TABLES = {'access_accounts', 'access_libraries', 'access_sessions',
    'access_invitations', 'access_admission_key', 'access_attempts', 'access_kdf_slot'}


class Budget:
    def __init__(self, max_bytes, seconds):
        if not 1024 * 1024 <= max_bytes <= 8 * 1024**3 or not 1 <= seconds <= 1800:
            raise small.Refused('Invalid explicit resource budget')
        self.max_bytes = max_bytes
        self.deadline = time.monotonic() + seconds

    def check(self):
        if time.monotonic() >= self.deadline:
            raise small.Refused('Preparation time budget exceeded')

    def configure(self, db):
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('PRAGMA cache_size=-8192')
        db.execute('PRAGMA temp_store=FILE')
        db.execute('PRAGMA mmap_size=0')
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 16 * 1024**2)
        db.set_progress_handler(lambda: time.monotonic() >= self.deadline, 10000)

    def size(self, db):
        self.check()
        size = db.execute('PRAGMA page_size').fetchone()[0] * db.execute('PRAGMA page_count').fetchone()[0]
        if size > self.max_bytes:
            raise small.Refused('Database exceeds explicit size budget')
        return size


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def schema(db):
    tables = db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    if any('VIRTUAL TABLE' in (sql or '').upper() for _, sql in tables):
        raise small.Refused('Virtual tables need separate review')
    return {name: [row[1] for row in db.execute('PRAGMA table_info(' + quoted(name) + ')')]
            for name, _ in tables}


def fingerprint(db, tables, budget):
    """Stream bounded rows; stable across copies and additive column migrations.

    Sorting uses disk-backed SQLite temporary storage. Never emit values or table
    hashes to stdout. A single value/row over 16 MiB is deliberately refused.
    """
    digest = hashlib.sha256(b'photohouse-disk-snapshot-v1\0')
    counts = {}
    for name, columns in sorted(tables.items()):
        budget.check()
        digest.update(json.dumps([name, columns], ensure_ascii=True).encode())
        selection = ','.join(map(quoted, columns))
        cursor = db.execute(f'SELECT {selection} FROM {quoted(name)} ORDER BY {selection}')
        count = 0
        for row in cursor:
            budget.check()
            digest.update(b'R')
            for value in row:
                if value is None:
                    kind, data = b'n', b''
                elif isinstance(value, bytes):
                    kind, data = b'b', value
                elif isinstance(value, str):
                    kind, data = b's', value.encode('utf-8')
                elif isinstance(value, int):
                    kind, data = b'i', str(value).encode('ascii')
                else:
                    kind, data = b'f', struct.pack('!d', value)
                digest.update(kind + struct.pack('!Q', len(data))); digest.update(data)
            count += 1
        counts[name] = count
    return digest.hexdigest(), counts


def validate(db, budget):
    budget.size(db)
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise small.Refused('Integrity verification failed')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise small.Refused('Foreign-key verification failed')
    return small.revision(db)


@contextmanager
def read_source(path, budget, *, offline=False):
    before = small.identity(path)
    if offline:
        small.no_sidecars(path)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)) as db:
        budget.configure(db); db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
        # Establish one pinned read snapshot before inspecting/copying anything.
        budget.size(db)
        if offline and db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
            raise small.Refused('Reviewed offline snapshot required')
        yield db
        budget.check()
        if small.identity(path) != before:
            raise small.Refused('Source identity changed')
        if offline:
            small.no_sidecars(path)


@contextmanager
def new_database(path, budget, size):
    small.direct(path); small.no_sidecars(path)
    if shutil.disk_usage(path.parent).free < 3 * size + 256 * 1024**2:
        raise small.Refused('Insufficient disk space for preparation')
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(path, flags, 0o600), 'r+b') as reserved:
        expected = small.identity(path)
        with closing(sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=3)) as db:
            budget.configure(db)
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA max_page_count=' + str(budget.max_bytes // 4096))
            if small.identity(path) != expected:
                raise small.Refused('Output identity changed')
            yield db
        os.fsync(reserved.fileno())
        if small.identity(path) != expected:
            raise small.Refused('Output identity changed')
        small.no_sidecars(path)


def copy(source, destination, budget):
    page_size = source.execute('PRAGMA page_size').fetchone()[0]
    def progress(status, remaining, total):
        budget.check()
        if total * page_size > budget.max_bytes:
            raise small.Refused('Copy exceeds size budget')
    source.backup(destination, pages=256, progress=progress, sleep=0.05)
    if destination.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
        raise small.Refused('Output journal verification failed')
    budget.configure(destination)
    destination.execute('PRAGMA max_page_count=' + str(budget.max_bytes // destination.execute('PRAGMA page_size').fetchone()[0]))
    budget.size(destination)


def snapshot(source_path, out, budget):
    with read_source(source_path, budget) as source:
        revision = validate(source, budget)
        tables = schema(source)
        # Hashing/copying the same read transaction includes committed WAL content.
        expected, counts = fingerprint(source, tables, budget)
        with new_database(out, budget, budget.size(source)) as output:
            copy(source, output, budget)
            if validate(output, budget) != revision or fingerprint(output, tables, budget)[0] != expected:
                raise small.Refused('Snapshot mismatch')
    return dict(snapshot_digest=expected, source_revision=revision, tables_verified=len(counts),
                rows_verified=sum(counts.values()), online_snapshot=True,
                suitable_for_cutover=False, source_modified=False)


def upgrade_copy(db, budget):
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    from alembic import command
    from app.access.runtime import REQUIRED_REVISION, REQUIRED_TABLES
    # Separate owned connection to the exclusively-created output; never ambient
    # DATABASE_URL or the source. The caller retains its own verification handle.
    path = Path(db.execute('PRAGMA database_list').fetchone()[2])
    expected_identity = small.identity(path)
    def connect():
        if small.identity(path) != expected_identity:
            raise small.Refused('Candidate identity changed')
        connection = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=3)
        budget.configure(connection)
        return connection
    engine = create_engine('sqlite://', creator=connect, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            config = small.migration_config(); config.attributes['connection'] = connection
            command.upgrade(config, REQUIRED_REVISION)
        if validate(db, budget) != REQUIRED_REVISION or not REQUIRED_TABLES <= set(schema(db)):
            raise small.Refused('Migrated schema incomplete')
    finally:
        engine.dispose()


def rehearse(source_path, out, restored, digest, budget):
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise small.Refused('Reviewed snapshot digest required')
    from app.access.recovery import _quarantine_access_state, _assert_quarantined
    with read_source(source_path, budget, offline=True) as source:
        previous = validate(source, budget)
        tables = schema(source)
        if fingerprint(source, tables, budget)[0] != digest:
            raise small.Refused('Reviewed snapshot changed')
        preserved = {name: cols for name, cols in tables.items()
                     if name != 'alembic_version' and name not in QUARANTINE_TABLES}
        expected, counts = fingerprint(source, preserved, budget)
        with new_database(out, budget, budget.size(source)) as output:
            copy(source, output, budget)
            upgrade_copy(output, budget)
            output.execute('BEGIN IMMEDIATE')
            try:
                key = _quarantine_access_state(output)
                _assert_quarantined(output, key)
                output.commit()
            except BaseException:
                output.rollback(); raise
            current = validate(output, budget)
            if fingerprint(output, preserved, budget)[0] != expected:
                raise small.Refused('Pre-existing data changed')
            full_schema = schema(output)
            migrated, _ = fingerprint(output, full_schema, budget)
            with new_database(restored, budget, budget.size(output)) as restore:
                copy(output, restore, budget)
                if validate(restore, budget) != current or fingerprint(restore, full_schema, budget)[0] != migrated:
                    raise small.Refused('Disk restore mismatch')
                _assert_quarantined(restore, key)
    return dict(source_revision=previous, revision=current, source_snapshot_digest=digest,
                tables_preserved=len(counts), rows_preserved=sum(counts.values()),
                disk_restore_verified=True, candidate_quarantined=True,
                suitable_for_cutover=False, source_modified=False)


def main(argv=None):
    parser = small.Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument('command', choices=('snapshot', 'rehearse'))
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--restore-out', type=Path)
    parser.add_argument('--reviewed-snapshot-digest')
    parser.add_argument('--max-bytes', type=int, required=True)
    parser.add_argument('--timeout-seconds', type=int, required=True)
    try:
        args = parser.parse_args(argv)
        budget = Budget(args.max_bytes, args.timeout_seconds)
        if args.command == 'snapshot':
            if args.restore_out is not None or args.reviewed_snapshot_digest is not None:
                raise small.Refused('Unexpected snapshot arguments')
            result = snapshot(args.database, args.out, budget)
        else:
            if args.restore_out is None or args.reviewed_snapshot_digest is None:
                raise small.Refused('Explicit restore and review required')
            result = rehearse(args.database, args.out, args.restore_out, args.reviewed_snapshot_digest, budget)
        print(json.dumps(dict(completed=True, command=args.command, **result)))
        return 0
    except KeyboardInterrupt:
        print('Interrupted; retain and inspect partial outputs.', file=sys.stderr)
        return 130
    except Exception:
        print('Preparation refused or incomplete; retain and inspect partial outputs.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
