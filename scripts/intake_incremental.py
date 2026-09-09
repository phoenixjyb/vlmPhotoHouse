"""Plan incremental intake; quarantine only verified, unregistered exact copies.

Runs on the media/database host. Audit is the default; --apply is explicit.
Never moves an existing database asset, follows a reparse point, deletes media,
or treats perceptual similarity as duplication. JSONL receipts support recovery.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time
import urllib.request
import urllib.parse

IMAGES = {'.jpg', '.jpeg', '.png', '.heic', '.webp'}
VIDEOS = {'.mp4', '.mov', '.mkv', '.avi', '.m4v'}


def key(path):
    return os.path.normcase(os.path.abspath(path))


def linked(path):
    info = Path(path).lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def checked_path(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    path.relative_to(root)
    for current in [path, *path.parents]:
        if linked(current):
            raise ValueError(f'Reparse/symlink refused: {current}')
        if current == root:
            return path
    raise ValueError('Outside intake root')


def signature(path):
    info = Path(path).stat()
    return [info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino]


def digest(path):
    before = signature(path)
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            sha.update(chunk)
    if signature(path) != before:
        raise ValueError('File changed while hashing')
    return sha.hexdigest()


def connect(database):
    return sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True, timeout=30)


def registered(database):
    with closing(connect(database)) as con:
        return con.execute('select id,path,hash_sha256,file_size,status from assets').fetchall()


def emit(log, event):
    log.write(json.dumps(event, ensure_ascii=True) + '\n')
    log.flush()
    os.fsync(log.fileno())


def audit(root, database, settle_seconds=600):
    root = Path(root).resolve()
    rows = registered(database)
    protected = {key(row[1]) for row in rows}
    hashes = defaultdict(list)
    sizes = set()
    for _, path, sha, size, status in rows:
        if status in (None, 'active'):
            hashes[sha].append(path)
            sizes.add(size)
    fresh, deferred, errors = [], [], []
    unsupported = Counter()
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not linked(Path(directory) / d))
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix.lower() not in IMAGES | VIDEOS:
                unsupported[path.suffix.lower()] += 1
                continue
            if key(path) in protected:
                continue
            try:
                checked_path(path, root)
                info = path.stat()
                item = {'path': str(path), 'signature': signature(path)}
                if max(info.st_mtime, getattr(info, 'st_birthtime', info.st_ctime)) > time.time() - settle_seconds or info.st_size == 0:
                    deferred.append(item)
                else:
                    fresh.append(item)
            except (OSError, ValueError) as exc:
                errors.append({'path': str(path), 'error': str(exc)})
    size_counts = Counter(item['signature'][0] for item in fresh)
    keepers, verified = {}, {}
    unique, duplicates = [], []
    for number, item in enumerate(fresh, 1):
        path = Path(item['path'])
        size = item['signature'][0]
        try:
            if signature(path) != item['signature']:
                raise ValueError('File changed after discovery')
            # No other file of this size can be an exact duplicate.
            if size not in sizes and size_counts[size] == 1:
                unique.append(item)
                continue
            sha = digest(path)
            item['sha256'] = sha
            keeper = keepers.get(sha)
            if keeper is None:
                for reference in hashes.get(sha, []):
                    try:
                        checked_path(reference, root)
                        if signature(reference)[0] != size:
                            continue
                        if reference not in verified:
                            verified[reference] = digest(reference)
                        if verified[reference] == sha:
                            keeper = reference
                            break
                    except (OSError, ValueError):
                        continue
            if keeper:
                item['keeper'] = keeper
                item['keeper_signature'] = signature(keeper)
                duplicates.append(item)
            else:
                keepers[sha] = str(path)
                unique.append(item)
        except (OSError, ValueError) as exc:
            errors.append({'path': str(path), 'error': str(exc)})
        if number % 25 == 0:
            print(json.dumps({'phase': 'hash-audit', 'checked': number, 'total': len(fresh), 'duplicates': len(duplicates)}), flush=True)
    return {'version': 1, 'root': str(root), 'database': str(Path(database).resolve()),
            'created_at': time.time(), 'unique': unique, 'duplicates': duplicates,
            'deferred': deferred, 'errors': errors, 'unsupported': dict(unsupported),
            'summary': {'unique': len(unique), 'duplicates': len(duplicates), 'deferred': len(deferred),
                        'errors': len(errors), 'duplicate_bytes': sum(i['signature'][0] for i in duplicates),
                        'new_images': sum(Path(i['path']).suffix.lower() in IMAGES for i in unique),
                        'new_videos': sum(Path(i['path']).suffix.lower() in VIDEOS for i in unique)}}


def quarantine(plan, destination, log):
    root, destination = Path(plan['root']), Path(destination).absolute()
    if destination.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(destination.resolve()):
        raise ValueError('Quarantine must be separate from the intake tree')
    # Refuse existing symlinks in destination ancestry before creating folders.
    for part in [destination, *destination.parents]:
        if part.exists() and linked(part):
            raise ValueError('Linked quarantine path refused')
    protected = {key(row[1]) for row in registered(plan['database'])}
    moved = 0
    for item in plan['duplicates']:
        source = checked_path(item['path'], root)
        keeper = checked_path(item['keeper'], root)
        if key(source) in protected:
            raise ValueError('Refusing to move a registered asset')
        if key(source) == key(keeper):
            raise ValueError('Source is its own keeper')
        if signature(source) != item['signature'] or signature(keeper) != item['keeper_signature']:
            raise ValueError('Duplicate or keeper changed since audit')
        # Re-read BOTH originals, not just old database hashes, before moving.
        if digest(source) != item['sha256'] or digest(keeper) != item['sha256']:
            raise ValueError('Exact duplicate verification failed')
        target = destination / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or source.stat().st_dev != target.parent.stat().st_dev:
            raise ValueError('Destination exists or is on a different volume')
        with closing(connect(plan['database'])) as con:
            if con.execute('select 1 from assets where path = ? collate nocase', (str(source),)).fetchone():
                raise ValueError('Asset became registered after audit')
        event = {'source': str(source), 'destination': str(target), 'keeper': str(keeper), 'sha256': item['sha256'], 'size': item['signature'][0]}
        emit(log, {'event': 'move-intent', **event})
        os.rename(source, target)  # Same-volume move; never a delete/copy fallback.
        emit(log, {'event': 'moved', **event})
        moved += 1
        if moved % 25 == 0 or moved == len(plan['duplicates']):
            print(json.dumps({'phase': 'quarantine', 'moved': moved, 'total': len(plan['duplicates'])}), flush=True)
    return moved


def ingest_selected(plan, log, *, defer_embeddings=False, api_url='http://127.0.0.1:8002'):
    # Use the project's importer and schema, not hand-written database inserts.
    root, database = Path(plan['root']), Path(plan['database'])
    os.environ['DATABASE_URL'] = 'sqlite:///' + database.as_posix()
    os.environ['VIDEO_ENABLED'] = 'true'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from app.ingest import ingest_paths
    from app.db import Asset
    if plan['unique'] and not defer_embeddings:
        parsed = urllib.parse.urlparse(api_url)
        if parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or parsed.scheme != 'http':
            raise ValueError('Use a loopback PhotoHouse API')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(api_url.rstrip('/') + '/embedding/backend', timeout=30) as response:
            backend = json.load(response)
        if any(str(backend.get(field, 'stub')).startswith('stub') for field in ('image_model', 'text_model')):
            raise ValueError('Live similarity embedding provider is a stub; use --defer-embeddings or configure a real provider first')
    engine = create_engine(os.environ['DATABASE_URL'], connect_args={'timeout': 30})
    sessions = sessionmaker(bind=engine)
    counts = Counter()
    for item in plan['unique']:
        path = checked_path(item['path'], root)
        try:
            if signature(path) != item['signature']:
                raise ValueError('File changed since audit; deferred')
            with sessions() as session:
                result = ingest_paths(session, [str(path)], enqueue_embeddings=not defer_embeddings)
                asset_id = session.scalar(select(Asset.id).where(Asset.path == str(path)))
            counts['new_assets'] += result['new_assets']
            counts['skipped'] += result['skipped']
            if defer_embeddings:
                counts['embedding_jobs_deferred'] += result['new_assets']
            emit(log, {'event': 'ingested', 'path': str(path), 'asset_id': asset_id,
                       'similarity_embedding_deferred': defer_embeddings, **result})
        except Exception as exc:
            counts['errors'] += 1
            emit(log, {'event': 'ingest-error', 'path': str(path), 'error': str(exc)})
        print(json.dumps({'phase': 'ingest', **counts}), flush=True)
    engine.dispose()
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--settle-seconds', type=int, default=600)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--quarantine', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--defer-embeddings', action='store_true', help='Do not enqueue general image/video embeddings; caption and face tasks remain enabled')
    parser.add_argument('--api-url', default='http://127.0.0.1:8002')
    args = parser.parse_args()
    if not args.apply:
        plan = audit(args.root, args.database, args.settle_seconds)
        with args.plan.open('x', encoding='utf-8') as out:
            json.dump(plan, out, ensure_ascii=True, indent=2)
        print(json.dumps({'phase': 'audit-complete', **plan['summary']}), flush=True)
        return
    if not args.quarantine or not args.receipt:
        parser.error('--apply requires --quarantine and --receipt')
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    if key(plan['root']) != key(args.root) or key(plan['database']) != key(args.database):
        raise ValueError('Plan root/database mismatch')
    with args.receipt.open('x', encoding='utf-8') as log:
        moved = quarantine(plan, args.quarantine, log)
        result = ingest_selected(plan, log, defer_embeddings=args.defer_embeddings, api_url=args.api_url)
        emit(log, {'event': 'complete', 'moved': moved, **result})
        print(json.dumps({'phase': 'complete', 'moved': moved, **result}), flush=True)


if __name__ == '__main__':
    main()
