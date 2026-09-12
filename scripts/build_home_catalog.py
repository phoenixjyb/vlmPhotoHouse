#!/usr/bin/env python3
"""Export all active/legacy-active catalog IDs to a NEW private TV publication.

Read-only SQLite, no app import, models, file enumeration, media decoding or
source copying. Every derivative starts explicitly unavailable. Operators must
prepare/verify bytes separately before marking any item ready; this is metadata
export, not full-library playback readiness.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.home_catalog import MAX_ASSETS, MAX_CATALOG, validate_catalog
from app.home_feed import direct_path, integer


def export(database, output, revision, library_id='home-library', title='PhotoHouse'):
    direct_path(database); direct_path(output)
    if database.resolve(strict=True) != database or not database.is_file(): raise ValueError('Direct database required')
    if output.exists() or not integer(revision, 1, 2**31-1): raise ValueError('New output and positive revision required')
    start = time.monotonic()
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=2)) as conn:
        conn.execute('PRAGMA query_only=ON')
        conn.set_progress_handler(lambda: int(time.monotonic() - start > 60), 10000)
        # One read snapshot; fail on excess instead of publishing a truncated library.
        rows = conn.execute("SELECT id,mime,width,height FROM assets WHERE status='active' OR status IS NULL ORDER BY id DESC LIMIT ?", (MAX_ASSETS+1,)).fetchall()
    if len(rows) > MAX_ASSETS: raise ValueError('Catalog exceeds reviewed limit')
    assets = []
    for aid, mime, width, height in rows:
        kind = 'photo' if (mime or '').startswith('image/') else 'video' if (mime or '').startswith('video/') else 'unsupported'
        unavailable = {'state': 'unavailable', 'reason': 'unsupported' if kind == 'unsupported' else 'not_prepared'}
        assets.append({'id': aid, 'kind': kind, 'label': f'Asset {aid}',
            'width': width if integer(width, 1, 1000000) else None,
            'height': height if integer(height, 1, 1000000) else None,
            'previews': {'grid': dict(unavailable), 'display': dict(unavailable)},
            'video': dict(unavailable) if kind == 'video' else None})
    catalog = validate_catalog({'version': 2, 'revision': revision, 'library_id': library_id, 'title': title, 'assets': assets})
    raw = json.dumps(catalog, ensure_ascii=True, separators=(',', ':')).encode()
    if len(raw) > MAX_CATALOG: raise ValueError('Catalog exceeds byte limit')
    control = {'version': 2, 'enabled': False, 'revision': revision, 'catalog_sha256': hashlib.sha256(raw).hexdigest()}
    output.mkdir(mode=0o700)  # Never overwrite an existing publication.
    (output / 'catalog.json').write_bytes(raw)
    (output / 'control.json').write_text(json.dumps(control) + '\n')
    (output / 'prepared').mkdir()
    return {'assets': len(assets), 'catalog_sha256': control['catalog_sha256'], 'enabled': False,
            'prepared_media': 0, 'live_database_changed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', type=int, required=True)
    args = parser.parse_args(argv)
    try: result = export(args.database, args.output, args.revision)
    except Exception:
        print('Catalog export failed; no active publication was changed', file=sys.stderr)
        return 2
    print(json.dumps(result)); return 0


if __name__ == '__main__': raise SystemExit(main())
