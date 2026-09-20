#!/usr/bin/env python3
"""Plan or stage an explicit selection of prepared videos, without activating it.

Plan is read-only. Stage writes only new operator-owned paths and copies derived
playback files, never originals. The existing exporter verifies the selected
source hashes and staged outputs before producing a separate pinned index.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_protected_videos as exporter
from app.access.prepared_video import direct, pin
from app.home_catalog import CHUNK_BYTES, identity, validate_video
from app.home_feed import bounded_read, unique
from staging_app import delivery_paths, load_configuration

GIB = 1024**3
MAX_SELECTION = 100


def readonly(path):
    direct(path)
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def new_path(path):
    if not path.is_absolute() or '..' in path.parts or path.exists() or path.is_symlink():
        raise ValueError('New absolute destination required')
    direct(path.parent)


def separated(left, right):
    if left.is_relative_to(right) or right.is_relative_to(left):
        raise ValueError('Independent paths required')


def selection(config_path, workspace, destination, output, asset_ids, *, max_bytes=2*GIB,
              reserve_bytes=2*GIB):
    if (not asset_ids or len(asset_ids) > MAX_SELECTION or len(set(asset_ids)) != len(asset_ids)
            or any(type(a) is not int or not 1 <= a <= 2**63-1 for a in asset_ids)):
        raise ValueError('Select 1 to 100 distinct asset IDs')
    if (type(max_bytes) is not int or not 1 <= max_bytes <= 32*GIB
            or type(reserve_bytes) is not int or reserve_bytes < GIB):
        raise ValueError('Invalid disk budget')
    config = load_configuration(config_path)
    direct(workspace)
    new_path(destination); new_path(output)
    new_path(output.with_name(output.name+'.pending'))
    delivery_paths(config, prepared_index=output, prepared_root=destination, prepared_sha256='0'*64)
    for target in (destination, output):
        for protected in (workspace, config_path):
            separated(target, protected)
    # Resolve configured boundaries too; lexical checks must not hide aliases.
    for path in (*config.original_roots, config.derived_root, config.database,
                 config.tls_certificate, config.tls_private_key, *config.discovery_indexes,
                 *((config.incoming_root,) if config.incoming_root else ())):
        direct(path)
    job_raw = bounded_read(workspace/'job.json', 1024**2)
    job = json.loads(job_raw, object_pairs_hook=unique)
    if job['version'] != 1 or Path(job['database']) != config.database:
        raise ValueError('Preparation provenance mismatch')
    source_root = direct(Path(job['source_root']))
    if source_root not in config.original_roots:
        raise ValueError('Preparation source is not a configured original root')
    digest = hashlib.sha256(job_raw).hexdigest()
    items, byte_count = [], len(job_raw)
    with closing(readonly(workspace/'state.sqlite')) as db:
        row = db.execute("SELECT value FROM meta WHERE key='job_sha256'").fetchone()
        if row is None or json.loads(row[0]) != digest:
            raise ValueError('Preparation job changed')
        for aid in sorted(asset_ids):
            row = db.execute("SELECT * FROM items WHERE id=? AND kind='video' AND status='ready'", (aid,)).fetchone()
            if row is None:
                raise ValueError('Selected video is not ready')
            item = dict(row)
            name = item['directory']
            if not isinstance(name, str) or not re.fullmatch(r'asset-'+str(aid)+r'-[a-z0-9_]{8}', name):
                raise ValueError('Invalid attempt directory')
            directory = direct(workspace/name)
            receipt_raw = bounded_read(directory/'receipt.json', 1024**2)
            receipt = json.loads(receipt_raw, object_pairs_hook=unique)
            result = json.loads(item['result'], object_pairs_hook=unique)
            if (receipt['job_sha256'] != digest or receipt['metadata_hash'] != item['metadata_hash']
                    or receipt['result'] != result or item['source_hash'] != result['source_sha256']):
                raise ValueError('Ready receipt mismatch')
            video = result['video']; validate_video(video)
            if video['state'] != 'ready':
                raise ValueError('Selected video is not ready')
            if identity(directory/'video.mp4')[2] != video['bytes']:
                raise ValueError('Prepared size changed')
            chunks = bounded_read(directory/'video.chunks.json', 1024**2)
            if hashlib.sha256(chunks).hexdigest() != video['chunks_sha256']:
                raise ValueError('Prepared chunk manifest changed')
            byte_count += video['bytes'] + len(receipt_raw) + len(chunks)
            items.append((item, receipt_raw, chunks, video))
    # Includes conservative metadata/index allowance; no large in-memory buffers.
    required = byte_count + 16*1024**2
    if required > max_bytes:
        raise ValueError('Selected bytes exceed staging budget')
    if shutil.disk_usage(destination.parent).free < required + reserve_bytes:
        raise ValueError('Insufficient staging disk reserve')
    if shutil.disk_usage(output.parent).free < 16*1024**2 + reserve_bytes:
        raise ValueError('Insufficient index disk reserve')
    report = dict(asset_ids=sorted(asset_ids), ready_videos=len(items), copy_bytes=byte_count,
                  budget_bytes=max_bytes, reserve_bytes=reserve_bytes, estimated_bytes=required,
                  source_hashes_verified=False, activated=False)
    return config, job_raw, items, report


def copy_video(source, target, expected, seconds):
    before = identity(source)
    if before[2] != expected['bytes']:
        raise ValueError('Prepared size changed')
    digest = hashlib.sha256(); deadline = time.monotonic() + seconds
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(source, flags), 'rb') as incoming, target.open('xb') as outgoing:
        if pin(os.fstat(incoming.fileno())) != before:
            raise ValueError('Prepared file changed')
        remaining = before[2]
        while remaining:
            if time.monotonic() > deadline:
                raise ValueError('Copy deadline reached')
            chunk = incoming.read(min(CHUNK_BYTES, remaining))
            if not chunk:
                raise ValueError('Prepared file changed')
            outgoing.write(chunk); digest.update(chunk); remaining -= len(chunk)
        outgoing.flush(); os.fsync(outgoing.fileno())
        if pin(os.fstat(incoming.fileno())) != before or identity(source) != before:
            raise ValueError('Prepared file changed')
    if time.monotonic() > deadline or digest.hexdigest() != expected['sha256']:
        raise ValueError('Prepared hash changed or copy deadline reached')


def stage(config_path, workspace, destination, output, asset_ids, *, max_bytes=2*GIB,
          reserve_bytes=2*GIB, seconds=900, write=False):
    if type(seconds) is not int or not 1 <= seconds <= 3600:
        raise ValueError('Invalid file deadline')
    config, job_raw, items, report = selection(config_path, workspace, destination, output,
        asset_ids, max_bytes=max_bytes, reserve_bytes=reserve_bytes)
    if not write:
        return dict(report, staged=False)
    destination.mkdir(mode=0o700)
    # An incomplete marker survives failures. Never remove/reuse partial folders
    # automatically; only a fully verified separate index can be activated.
    marker = destination/'INCOMPLETE'
    marker.write_text('Staging incomplete; do not activate.\n')
    (destination/'job.json').write_bytes(job_raw)
    with closing(sqlite3.connect(destination/'state.sqlite')) as db:
        db.execute('CREATE TABLE meta(key,value)')
        db.execute('INSERT INTO meta VALUES (?,?)', ('job_sha256', json.dumps(hashlib.sha256(job_raw).hexdigest())))
        db.execute('CREATE TABLE items(id,kind,status,directory,result,metadata_hash,source_hash)')
        for item, receipt, chunks, video in items:
            target = destination/item['directory']; target.mkdir(mode=0o700)
            copy_video(workspace/item['directory']/'video.mp4', target/'video.mp4', video, seconds)
            (target/'receipt.json').write_bytes(receipt)
            (target/'video.chunks.json').write_bytes(chunks)
            with closing(readonly(workspace/'state.sqlite')) as live:
                current = live.execute('SELECT * FROM items WHERE id=?', (item['id'],)).fetchone()
                if current is None or dict(current) != item:
                    raise ValueError('Preparation changed during staging')
            db.execute('INSERT INTO items VALUES (?,?,?,?,?,?,?)', tuple(item[k] for k in
                ('id','kind','status','directory','result','metadata_hash','source_hash')))
        db.commit()
    if bounded_read(workspace/'job.json', 1024**2) != job_raw:
        raise ValueError('Preparation job changed')
    # Export to a new private intermediate name first; failure cannot leave an
    # apparently final index behind. Hard-link only this small owned index for
    # exclusive publication. Playback files are always independent byte copies.
    pending = output.with_name(output.name+'.pending')
    new_path(pending)
    result = exporter.export(config.database, destination, pending, seconds=seconds)
    # Failure to clear the incomplete state must precede final publication.
    marker.unlink()
    try:
        os.link(pending, output)  # atomic no-overwrite publication on the same volume
    except BaseException:
        marker.write_text('Index publication failed; do not activate.\n')
        raise
    pending_retained = False
    try:
        pending.unlink()
    except OSError:
        # A cleanup failure cannot undo the already completed publication.
        pending_retained = True
    return dict(report, staged=True, source_hashes_verified=True,
                index_sha256=result['index_sha256'], media_copied=True,
                pending_index_retained=pending_retained)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config','workspace','destination','out'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--asset-id', type=int, action='append', required=True)
    parser.add_argument('--max-bytes', type=int, default=2*GIB)
    parser.add_argument('--reserve-bytes', type=int, default=2*GIB)
    parser.add_argument('--file-seconds', type=int, default=900)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan', action='store_true')
    mode.add_argument('--stage', action='store_true')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(stage(args.config,args.workspace,args.destination,args.out,args.asset_id,
            max_bytes=args.max_bytes,reserve_bytes=args.reserve_bytes,seconds=args.file_seconds,write=args.stage)))
        return 0
    except Exception:
        print('Prepared staging refused; any partial destination is incomplete. No service was changed.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
