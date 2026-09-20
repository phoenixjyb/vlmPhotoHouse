#!/usr/bin/env python3
"""Offline private index from existing ready preparation receipts; never re-encode.

Reads a selected preparation workspace and asset database. Verifies current source
and prepared output hashes using bounded reads, then writes one NEW private index.
It does not copy media, edit either database, publish Home assets or start services.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
import re
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.prepared_video import PreparedVideos, direct, MAX_INDEX
from app.home_catalog import CHUNK_BYTES, identity, validate_video
from app.home_feed import bounded_read, unique


def hash_file(path, maximum, seconds, *, chunks=False):
    before = identity(path)
    if not 0 < before[2] <= maximum: raise ValueError('File outside budget')
    deadline = time.monotonic() + seconds
    digest, parts = hashlib.sha256(), []
    flags = os.O_RDONLY | getattr(os,'O_BINARY',0) | getattr(os,'O_NOFOLLOW',0) | getattr(os,'O_NONBLOCK',0)
    fd = os.open(path,flags)
    with os.fdopen(fd,'rb') as stream:
        from app.access.prepared_video import pin
        if pin(os.fstat(stream.fileno())) != before: raise ValueError('File changed')
        remaining = before[2]
        while remaining:
            if time.monotonic() > deadline: raise ValueError('Hash deadline reached')
            data = stream.read(min(CHUNK_BYTES, remaining))
            if not data: raise ValueError('File changed')
            digest.update(data)
            if chunks: parts.append(hashlib.sha256(data).hexdigest())
            remaining -= len(data)
    if identity(path) != before or time.monotonic() > deadline: raise ValueError('File changed or deadline reached')
    return digest.hexdigest(), parts, before


def export(database, workspace, output, *, seconds=900):
    if type(seconds) is not int or not 1 <= seconds <= 3600: raise ValueError('Invalid hash deadline')
    direct(database); direct(workspace); direct(output.parent)
    if not output.is_absolute() or '..' in output.parts or output.exists(): raise ValueError('New absolute output required')
    job_raw = bounded_read(workspace/'job.json', 1024**2)
    job = json.loads(job_raw, object_pairs_hook=unique)
    source_root = direct(Path(job['source_root']))
    if job['version'] != 1 or Path(job['database']) != database:
        raise ValueError('Preparation provenance mismatch')
    if any(output.is_relative_to(p) or p.is_relative_to(output) for p in (source_root, workspace, database)):
        raise ValueError('Index must be separate')
    state = direct(workspace/'state.sqlite')
    entries = []
    with closing(sqlite3.connect(state.as_uri()+'?mode=ro', uri=True, timeout=3, isolation_level=None)) as prepared, \
         closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True, timeout=3, isolation_level=None)) as assets:
        prepared.row_factory = sqlite3.Row
        for db in (prepared, assets):
            db.execute('PRAGMA query_only=ON')
        row = prepared.execute("SELECT value FROM meta WHERE key='job_sha256'").fetchone()
        if row is None or json.loads(row[0]) != hashlib.sha256(job_raw).hexdigest():
            raise ValueError('Preparation job changed')
        # Materialize only IDs, then release the SQLite read statement before
        # slow file hashing. Never hold a live DB snapshot/WAL reader for hours.
        ids = prepared.execute("SELECT id FROM items WHERE kind='video' AND status='ready' ORDER BY id LIMIT 100001").fetchall()
        if len(ids) > 100000: raise ValueError('Too many assets')
        for selected in ids:
            item = prepared.execute("SELECT * FROM items WHERE id=? AND kind='video' AND status='ready'",(selected[0],)).fetchone()
            if item is None: raise ValueError('Preparation changed')
            aid, name = item['id'], item['directory']
            if type(aid) is not int or type(name) is not str or not re.fullmatch(r'asset-'+str(aid)+r'-[a-z0-9_]{8}',name):
                raise ValueError('Invalid attempt directory')
            directory = direct(workspace/name)
            receipt = json.loads(bounded_read(directory/'receipt.json', 1024**2), object_pairs_hook=unique)
            result = json.loads(item['result'], object_pairs_hook=unique)
            if (receipt['job_sha256'] != hashlib.sha256(job_raw).hexdigest()
                    or receipt['metadata_hash'] != item['metadata_hash'] or receipt['result'] != result
                    or item['source_hash'] != result['source_sha256']):
                raise ValueError('Ready receipt mismatch')
            row = assets.execute("SELECT path,mime,width,height,status FROM assets WHERE id=?", (aid,)).fetchone()
            if (row is None or row[4] not in (None, 'active') or not (row[1] or '').startswith('video/')
                    or hashlib.sha256(json.dumps(row).encode()).hexdigest() != item['metadata_hash']):
                raise ValueError('Source metadata changed')
            source = direct(Path(row[0]))
            if not source.is_relative_to(source_root): raise ValueError('Source outside root')
            source_hash, _, source_pin = hash_file(source, 128*1024**3, seconds)
            if source_hash != result['source_sha256']: raise ValueError('Source changed')
            video = result['video']; validate_video(video)
            if video['state'] != 'ready': raise ValueError('Video not ready')
            sha, chunks, output_pin = hash_file(directory/'video.mp4', video['bytes'], seconds, chunks=True)
            chunk_raw = bounded_read(directory/'video.chunks.json', 1024**2)
            if (output_pin[2] != video['bytes'] or sha != video['sha256'] or hashlib.sha256(chunk_raw).hexdigest() != video['chunks_sha256']
                    or json.loads(chunk_raw) != chunks): raise ValueError('Prepared bytes changed')
            if (identity(source) != source_pin or assets.execute('SELECT path,mime,width,height,status FROM assets WHERE id=?',(aid,)).fetchone() != row):
                raise ValueError('Source changed')
            latest = prepared.execute('SELECT * FROM items WHERE id=?',(aid,)).fetchone()
            if latest is None or tuple(latest) != tuple(item): raise ValueError('Preparation changed')
            entries.append(dict(id=aid,source_identity=list(source_pin),directory=name,video=video))
    raw = json.dumps({'version':1,'assets':entries},separators=(',',':')).encode()
    if len(raw) > MAX_INDEX: raise ValueError('Index too large')
    digest = hashlib.sha256(raw).hexdigest()
    with os.fdopen(os.open(output, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    # Reuse the runtime validator; this neither mounts a route nor touches media.
    PreparedVideos(output, digest, workspace)
    return {'version':1, 'ready_videos':len(entries), 'index_sha256':digest,
            'bytes':len(raw), 'activated':False, 'media_copied':False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--hash-seconds', type=int, default=900)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(export(args.database,args.workspace,args.out,seconds=args.hash_seconds)))
        return 0
    except Exception:
        print('Prepared export refused; no service or source media changed.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
