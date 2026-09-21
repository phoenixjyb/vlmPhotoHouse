#!/usr/bin/env python3
"""Derive one reviewed discovery index for one protected library; never approves.

Offline operator tool. Opens an existing database read-only, projects exactly the
bounded source the protected discovery service reads, and writes one new
ReviewedIndex artifact. It reads through the service's own scoped_source and
digest and its own default read budget, so the artifact it emits is one the
service can consume rather than a parallel reimplementation of that projection.

By default this producer supplies no people, places, face or region review and
enables date and media only. An explicit ``--review`` JSON file may add reviewed
people, aliases, pins, manual face assignments, places and regions. It may also
explicitly declare ``caption`` and ``tags`` as ``current_source`` fields; these
are native values already projected by the service, not inferred approvals.
The review file is bound to its library and the current source digest. It is not
incremental: scope_ids is the full ordered visible asset set and the digest
covers the whole library projection, so stale review input is refused.

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
REVIEW_FIELDS = frozenset(('people', 'date', 'caption', 'tags', 'locations', 'media'))
REVIEW_KEYS = frozenset(('library_id', 'source_digest', 'indexed_ids', 'enabled',
                         'people', 'pinned_ids', 'assignments', 'places', 'regions',
                         'source_fields'))
SOURCE_FIELD_KEYS = frozenset(('caption', 'tags'))
REVIEW_BYTES = 1024 * 1024
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


def review_json(path):
    """Read one explicit review envelope without accepting duplicate keys."""
    direct(path)
    record = path.lstat()
    if not stat.S_ISREG(record.st_mode) or path.resolve(strict=True) != path:
        raise Refused('Direct regular review file required')
    if record.st_size > REVIEW_BYTES:
        raise Refused('Review file too large')
    try:
        with path.open('rb') as handle:
            raw = handle.read(REVIEW_BYTES + 1)
        if len(raw) > REVIEW_BYTES:
            raise Refused('Review file too large')
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique,
                          parse_constant=_reject_constant)
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise Refused('Invalid review file') from None


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError('non-finite number')


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
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)
    try:
        configure(db, start)
        found = dict(db.execute("SELECT name,type FROM sqlite_master WHERE name IN ({})".format(
            ','.join('?' * len(REQUIRED_TABLES))), REQUIRED_TABLES))
        if found != {name: 'table' for name in REQUIRED_TABLES}:
            raise Refused('Reviewed library schema required')
        db.set_authorizer(authorize)
        return db
    except BaseException:
        db.close()
        raise


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


def _review_string(value, maximum, *, nonempty=True):
    if type(value) is not str or len(value.encode('utf-8')) > maximum:
        raise Refused('Invalid review value')
    if any(ord(c) < 32 and c not in '\n\t' for c in value) or (nonempty and not value.strip()):
        raise Refused('Invalid review value')
    return value


def _review_ids(value, maximum):
    if type(value) is not list or len(value) > maximum:
        raise Refused('Invalid review ids')
    result = []
    for item in value:
        if type(item) is not str or re.fullmatch(r'[1-9][0-9]{0,18}', item) is None:
            raise Refused('Invalid review id')
        result.append(item)
    if len(set(result)) != len(result):
        raise Refused('Duplicate review id')
    return tuple(result)


def reviewed_index(value, identifier, revision_value, scope, source_digest, source):
    """Convert explicit JSON review data through the service's provider types."""
    from app.access.discovery_provider import ReviewedFace, ReviewedPerson, ReviewedPlace
    if type(value) is not dict or set(value) != REVIEW_KEYS:
        raise Refused('Review fields are incomplete')
    if value['library_id'] != identifier or value['source_digest'] != source_digest:
        raise Refused('Review is for a different source')
    for key in ('indexed_ids', 'pinned_ids', 'people', 'assignments', 'places', 'regions'):
        if type(value[key]) is not list:
            raise Refused('Invalid review arrays')
    indexed = _review_ids(value['indexed_ids'], len(scope))
    if not set(indexed) <= set(scope):
        raise Refused('Review scope is not current')
    enabled = value['enabled']
    if type(enabled) is not list or not enabled or any(type(field) is not str for field in enabled):
        raise Refused('Invalid review fields')
    if len(set(enabled)) != len(enabled):
        raise Refused('Duplicate review field')
    if any(type(field) is not str or field not in REVIEW_FIELDS for field in enabled) or 'media' not in enabled:
        raise Refused('Invalid review fields')
    source_fields = value['source_fields']
    if type(source_fields) is not dict or set(source_fields) - SOURCE_FIELD_KEYS:
        raise Refused('Invalid source field declarations')
    if any(field in enabled and source_fields.get(field) != 'current_source' for field in ('caption', 'tags')):
        raise Refused('Caption and tag review declarations required')
    people = []
    for item in value['people']:
        if type(item) is not dict or set(item) != {'id', 'label', 'aliases', 'allow_zero'}:
            raise Refused('Invalid reviewed person')
        aliases = item['aliases']
        if type(aliases) is not list or len(aliases) > 8:
            raise Refused('Invalid reviewed aliases')
        if type(item['allow_zero']) is not bool:
            raise Refused('Invalid reviewed person')
        people.append(ReviewedPerson(identifier, _review_string(item['id'], 19),
            _review_string(item['label'], 256), tuple(_review_string(alias, 128) for alias in aliases),
            item['allow_zero']))
    places = []
    for item in value['places']:
        if type(item) is not dict or set(item) != {'id', 'label'}:
            raise Refused('Invalid reviewed place')
        places.append(ReviewedPlace(identifier, _review_string(item['id'], 19), _review_string(item['label'], 256)))
    assignments = []
    for item in value['assignments']:
        if type(item) is not dict or set(item) != {'id', 'asset_id', 'person_id', 'source'}:
            raise Refused('Invalid reviewed assignment')
        assignments.append(ReviewedFace(_review_string(item['id'], 19), _review_string(item['asset_id'], 19),
                                        _review_string(item['person_id'], 19), item['source']))
    regions = []
    for item in value['regions']:
        if type(item) is not list or len(item) != 2:
            raise Refused('Invalid reviewed region')
        regions.append((_review_string(item[0], 19), _review_string(item[1], 19)))
    from app.access.discovery_provider import ReviewedIndex
    face_rows = {str(row[0]): (str(row[1]), str(row[2]), row[3]) for row in source['faces']}
    for assignment in assignments:
        if face_rows.get(assignment.id) != (assignment.asset_id, assignment.person_id, assignment.source):
            raise Refused('Reviewed assignment does not match source')
    assigned_people = {assignment.person_id for assignment in assignments}
    if any(not person.allow_zero and person.id not in assigned_people for person in people):
        raise Refused('Reviewed person has no approved assignment')
    return ReviewedIndex(identifier, revision_value, tuple(scope), indexed, source_digest,
                         tuple(people), _review_ids(value['pinned_ids'], 32), tuple(assignments),
                         tuple(places), tuple(regions), tuple(enabled))


def derive(db, identifier, revision_value, review=None):
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
    index = (reviewed_index(review, identifier, revision_value, scope, source_digest, source)
             if review is not None else
             ReviewedIndex(library_id=identifier, revision=revision_value, scope_ids=scope,
                           indexed_ids=scope, source_digest=source_digest, enabled=ENABLED))
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
    parser.add_argument('--review', type=Path)
    completed = False
    try:
        args = parser.parse_args(argv)
        identifier, revision_value = library(args.library), revision(args.revision)
        review = review_json(args.review) if args.review is not None else None
        start = time.monotonic()
        with closing(open_read_only(args.database, start)) as db:
            index, catalog_assets = derive(db, identifier, revision_value, review)
        payload = json.dumps(asdict(index), sort_keys=True, ensure_ascii=True,
                             separators=(',', ':'), allow_nan=False).encode()
        digest = write_new(args.out, payload)
        completed = True
        print(json.dumps({'command': 'prepare-access-discovery-index', 'completed': True,
                          'existing_database_modified': False, 'library_id': identifier,
                          'revision': revision_value, 'enabled': list(index.enabled),
                          'catalog_assets': catalog_assets, 'indexed_assets': len(index.indexed_ids),
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
