#!/usr/bin/env python3
"""Derive one reviewed discovery index for one protected library; never approves.

Offline operator tool. Opens an existing database read-only, projects exactly the
bounded source the protected discovery service reads, and writes one new
ReviewedIndex artifact. It reads through the service's own scoped_source and
digest and its own default read budget, so the artifact it emits is one the
service can consume rather than a parallel reimplementation of that projection.

This producer supplies no people, places, face or region review. It enables the
date and media filters only, whose values are native library fields rather than
operator assertions, so there is nothing here for an operator to approve. It is
not incremental: scope_ids is the full ordered visible asset set and the digest
covers the whole library projection, so any ingest, caption, tag or face
assignment change invalidates the artifact and it must be re-derived. The
service refuses a stale artifact with 409 instead of serving older results.

One library per invocation. Output is written once and never overwritten.
"""
import argparse
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

MAX_SECONDS = 30
MAX_REVISION = 2 ** 63 - 1
REQUIRED_TABLES = ('assets', 'captions', 'face_detections', 'tags', 'asset_tags',
                   'asset_tag_blocks', 'access_asset_libraries')
ENABLED = ('date', 'media')
ALLOWED_FUNCTIONS = frozenset({'length'})


class Refused(RuntimeError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('Invalid arguments')


def direct(path):
    if (not path.is_absolute() or '..' in path.parts or path.anchor.startswith(('//', '\\\\'))
            or not path.parent.is_dir() or path.parent.resolve(strict=True) != path.parent):
        raise Refused('Explicit direct local path required')
    return path


def library(value):
    if not (type(value) is str and 1 <= len(value) <= 128) or any(ord(c) < 32 for c in value):
        raise Refused('Explicit library identifier required')
    return value


def revision(value):
    if type(value) is not str or re.fullmatch(r'[1-9][0-9]{0,18}', value) is None or int(value) > MAX_REVISION:
        raise Refused('Positive decimal revision required')
    return value


def configure(db, start):
    # Pragmas and schema checks run before the authorizer exists; it denies them.
    db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
    db.execute('PRAGMA query_only=ON')
    db.execute('PRAGMA trusted_schema=OFF')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA cache_size=-4096')
    db.execute('BEGIN')
    db.set_progress_handler(lambda: int(time.monotonic() - start > MAX_SECONDS), 1000)
    return db


def open_read_only(path, start):
    direct(path)
    record = path.lstat()
    if not stat.S_ISREG(record.st_mode) or path.resolve(strict=True) != path:
        raise Refused('Direct regular database required')
    db = configure(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3), start)
    found = dict(db.execute("SELECT name,type FROM sqlite_master WHERE name IN ({})".format(
        ','.join('?' * len(REQUIRED_TABLES))), REQUIRED_TABLES))
    if found != {name: 'table' for name in REQUIRED_TABLES}:
        raise Refused('Reviewed library schema required')
    db.set_authorizer(authorize)
    return db


def authorize(action, first, second, *rest):
    """Read-only by construction, and only the one function the projection uses.

    A new function in `scoped_source` therefore refuses here instead of silently
    running unreviewed SQL: the operator must re-review this tool alongside it.
    """
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_TRANSACTION):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and second in ALLOWED_FUNCTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def derive(db, identifier, revision_value):
    """Project and validate through the service's own code and read budget."""
    from app.access import discovery as d
    from app.access.discovery_provider import ReviewedIndex
    budget = d.ReadBudget()
    with budget.attempt(db, lambda: False) as (check, read):
        source = d.scoped_source(identifier, read)
        check()
        scope = tuple(str(row[0]) for row in source['assets'])
        if not scope:
            raise Refused('No visible assets for this library')
        source_digest = d.digest(source)
    index = ReviewedIndex(library_id=identifier, revision=revision_value, scope_ids=scope,
                          indexed_ids=scope, source_digest=source_digest, enabled=ENABLED)
    # Refuse to emit an artifact the service would itself reject.
    d.validate(index, identifier, budget.rows)
    if len(d.packed(asdict(index))) > budget.index_bytes:
        raise Refused('Reviewed index exceeds the service budget')
    return index, len(scope)


def write_new(path, payload):
    direct(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(path, flags, 0o600), 'wb') as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(payload).hexdigest()


def main(argv=None):
    parser = Parser(allow_abbrev=False, description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--library', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--out', type=Path, required=True)
    completed = False
    try:
        args = parser.parse_args(argv)
        identifier, revision_value = library(args.library), revision(args.revision)
        start = time.monotonic()
        with closing(open_read_only(args.database, start)) as db:
            index, catalog_assets = derive(db, identifier, revision_value)
        payload = json.dumps(asdict(index), sort_keys=True, ensure_ascii=True,
                             separators=(',', ':'), allow_nan=False).encode()
        digest = write_new(args.out, payload)
        completed = True
        print(json.dumps({'command': 'prepare-access-discovery-index', 'completed': True,
                          'existing_database_modified': False, 'library_id': identifier,
                          'revision': revision_value, 'enabled': list(ENABLED),
                          'catalog_assets': catalog_assets, 'indexed_assets': catalog_assets,
                          'source_digest': index.source_digest, 'output_sha256': digest,
                          'output_bytes': len(payload)}, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print('Interrupted; inspect any new output before reuse.', file=sys.stderr)
        return 130
    except Exception:
        # Never echo paths, SQL, data or argv: refusals are deliberately opaque.
        print('Discovery index refused or incomplete; inspect any new output before reuse.'
              if not completed else 'Output failed after completion.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
