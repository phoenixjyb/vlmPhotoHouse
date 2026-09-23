#!/usr/bin/env python3
"""Bounded strict-CLIP embed worker for approved videos with prepared keyframes."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import stat
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_approved_image_embed_worker as image_worker

REVISION = 'a8d4c2e6f901'
MAX_SOURCE_BYTES = 16 * 1024**3
MAX_CHECKPOINT_BYTES = image_worker.MAX_CHECKPOINT_BYTES
MAX_FRAMES = 32
MAX_FRAME_BYTES = 16 * 1024**2
MAX_TOTAL_FRAME_BYTES = 128 * 1024**2
MAX_TASK_SECONDS = image_worker.MAX_TASK_SECONDS
MAX_ATTEMPTS = image_worker.MAX_ATTEMPTS
POLL_SECONDS = image_worker.POLL_SECONDS
MAX_VECTOR_BYTES = image_worker.MAX_VECTOR_BYTES
MAX_PAYLOAD_BYTES = 2048
SUPPORTED_VIDEO_MIME_PREFIX = 'video/'


class Refused(ValueError):
    pass


def _connect(database, *, writable=False):
    return image_worker._sqlite(database, writable=writable)


def _validate_schema(db):
    revision = db.execute('SELECT version_num FROM alembic_version').fetchall()
    if len(revision) != 1 or revision[0][0] != REVISION:
        raise Refused('Supported v36 migrated database required')
    required = {
        'tasks': {'id','type','payload_json','state','priority','retry_count','cancel_requested',
                  'scheduled_at','started_at','finished_at','last_error'},
        'assets': {'id','path','hash_sha256','file_size','mime','status'},
        'access_uploads': {'asset_id','state','sha256','bytes'},
        'access_asset_libraries': {'asset_id','library_id'},
        'access_libraries': {'id','state'},
    }
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required.keys() <= tables:
        raise Refused('Required v36 tables missing')
    for table, columns in required.items():
        actual = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
        if not columns <= actual:
            raise Refused('Required v36 columns missing')


def _video_asset(db, asset_id):
    rows = db.execute('''SELECT a.id,a.path,a.hash_sha256,a.file_size,a.mime,a.status,
          u.sha256,u.bytes,m.library_id,
          (SELECT count(*) FROM access_asset_libraries x WHERE x.asset_id=a.id)
        FROM assets a JOIN access_uploads u ON u.asset_id=a.id AND u.state='assigned'
        JOIN access_asset_libraries m ON m.asset_id=a.id
        JOIN access_libraries l ON l.id=m.library_id AND l.state='active'
        WHERE a.id=?''', (asset_id,)).fetchall()
    if len(rows) != 1:
        return None
    row = rows[0]
    if (row[5] != 'active' or not isinstance(row[4], str)
            or not row[4].lower().startswith(SUPPORTED_VIDEO_MIME_PREFIX)
            or type(row[3]) is not int or not 0 < row[3] <= MAX_SOURCE_BYTES
            or row[2] != row[6] or row[3] != row[7] or row[9] != 1):
        return None
    return {'asset_id': row[0], 'path': row[1], 'sha256': row[2], 'bytes': row[3],
            'mime': row[4], 'library_id': row[8]}


def _frame_files(derived, asset_id, *, inspect_images=True):
    base = derived / 'video_frames'
    if not base.is_dir() or base.is_symlink() or base.resolve(strict=True) != base:
        return None
    folder = base / str(asset_id)
    if not folder.is_dir() or folder.is_symlink() or folder.resolve(strict=True) != folder:
        return None
    entries = list(folder.iterdir())
    if not 1 <= len(entries) <= MAX_FRAMES:
        return None
    entries.sort(key=lambda p: p.name)
    total = 0
    frames = []
    for index, path in enumerate(entries, 1):
        if path.name != f'frame_{index:05d}.jpg':
            return None
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > MAX_FRAME_BYTES:
            return None
        total += info.st_size
        if total > MAX_TOTAL_FRAME_BYTES:
            return None
        if inspect_images:
            try:
                from PIL import Image
                with Image.open(path) as image:
                    if (image.format != 'JPEG' or image.width <= 0 or image.height <= 0
                            or image.width > 1024 or image.height > 1024
                            or image.width * image.height > 1024**2):
                        return None
                    image.verify()
            except Exception:
                return None
        frames.append(path)
    return frames


def _fingerprint(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise ValueError('keyframe_changed')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns):
            raise ValueError('keyframe_changed')
        while chunk := stream.read(1024**2):
            digest.update(chunk)
    after = path.stat(follow_symlinks=False)
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns):
        raise ValueError('keyframe_changed')
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, digest.hexdigest())


def _due_tasks(db):
    return db.execute('''SELECT id,payload_json,retry_count,priority FROM tasks
        WHERE type='video_embed' AND state='pending' AND cancel_requested=0
          AND (scheduled_at IS NULL OR scheduled_at<=CURRENT_TIMESTAMP)
        ORDER BY priority,id''').fetchall()


def matching_candidates(db, derived):
    candidates = []
    skipped = 0
    for task_id, raw_payload, retries, priority in _due_tasks(db):
        if not isinstance(raw_payload, str) or len(raw_payload.encode('utf-8')) > MAX_PAYLOAD_BYTES:
            skipped += 1; continue
        try:
            payload = json.loads(raw_payload)
        except (TypeError, ValueError):
            skipped += 1; continue
        if (type(payload) is not dict or set(payload) != {'asset_id'}
                or type(payload.get('asset_id')) is not int or payload['asset_id'] <= 0):
            skipped += 1; continue
        asset = _video_asset(db, payload['asset_id'])
        if asset is None or _frame_files(derived, payload['asset_id'], inspect_images=False) is None:
            skipped += 1; continue
        candidates.append({'task_id': task_id, 'retry_count': retries, 'priority': priority, **asset})
    return candidates, skipped


def _source_path(candidate, originals):
    path = image_worker.direct_path(candidate['path'])
    if path == originals or not path.is_relative_to(originals):
        raise ValueError('source_scope')
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_size != candidate['bytes']:
        raise ValueError('source_file_changed')
    return path, (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def preflight(database, originals, derived, checkpoint, checkpoint_sha256,
              image_model, model_version, device, expected_gpu_uuid=None):
    database = image_worker.direct_path(database)
    originals = image_worker.direct_path(originals, directory=True)
    derived = image_worker.direct_path(derived, directory=True)
    checkpoint = image_worker.direct_path(checkpoint)
    if (checkpoint.stat().st_size > MAX_CHECKPOINT_BYTES or len(checkpoint_sha256) != 64
            or any(c not in '0123456789abcdef' for c in checkpoint_sha256)
            or image_worker.sha256_file(checkpoint, MAX_CHECKPOINT_BYTES) != checkpoint_sha256):
        raise Refused('Local checkpoint identity is invalid')
    if not image_model.startswith('clip-') or not image_model or len(image_model) > image_worker.MODEL_NAME_MAX:
        raise Refused('Explicit supported image model required')
    if not model_version or len(model_version) > image_worker.MODEL_VERSION_MAX:
        raise Refused('Explicit model version required')
    if device not in ('cpu', 'cuda:0', 'cuda:1'):
        raise Refused('Explicit CPU, cuda:0 or cuda:1 device required')
    if device == 'cpu' and expected_gpu_uuid:
        raise Refused('GPU UUID must be omitted for CPU execution')
    if device != 'cpu' and (not isinstance(expected_gpu_uuid, str)
                            or not expected_gpu_uuid.startswith('GPU-') or len(expected_gpu_uuid) > 64):
        raise Refused('Explicit expected GPU UUID required for CUDA execution')
    with closing(_connect(database)) as db:
        _validate_schema(db)
        if db.execute("SELECT 1 FROM tasks WHERE type='video_embed' AND state='running' LIMIT 1").fetchone():
            raise Refused('Existing running video embed task requires inspection')
        candidates, skipped = matching_candidates(db, derived)
        pending = db.execute("SELECT count(*) FROM tasks WHERE type='video_embed' AND state='pending'").fetchone()[0]
    return {'preflight': 'pass', 'activated': False, 'schema_revision': REVISION,
            'approved_claimable': len(candidates), 'pending_video_embed_all': pending,
            'skipped_due_video_embed': skipped, 'image_model': image_model,
            'model_version': model_version, 'requested_device': device,
            'expected_gpu_uuid': expected_gpu_uuid, 'checkpoint_sha256': checkpoint_sha256,
            'checkpoint_verified_local': True, 'execution': 'requires --execute'}


def _claim_one(database, derived):
    with closing(_connect(database, writable=True)) as db:
        db.execute('BEGIN IMMEDIATE'); _validate_schema(db)
        if db.execute("SELECT 1 FROM tasks WHERE type='video_embed' AND state='running' LIMIT 1").fetchone():
            db.rollback(); raise Refused('Existing running video embed task requires inspection')
        candidates, _ = matching_candidates(db, derived)
        for candidate in candidates:
            changed = db.execute('''UPDATE tasks SET state='running',started_at=CURRENT_TIMESTAMP,last_error=NULL
                WHERE id=? AND type='video_embed' AND state='pending' AND cancel_requested=0''',
                (candidate['task_id'],)).rowcount
            if changed == 1:
                db.commit(); return candidate
        db.rollback()
    return None


def _child(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--checkpoint', required=True); parser.add_argument('--model', required=True)
    parser.add_argument('--checkpoint-sha256', required=True)
    parser.add_argument('--device', required=True, choices=('cpu', 'cuda:0'))
    parser.add_argument('--stage', required=True); parser.add_argument('--model-version', required=True)
    parser.add_argument('--frame', action='append', required=True)
    values = parser.parse_args(argv)
    checkpoint = image_worker.direct_path(values.checkpoint)
    if image_worker.sha256_file(checkpoint, MAX_CHECKPOINT_BYTES) != values.checkpoint_sha256:
        raise RuntimeError('checkpoint_changed')
    stage = image_worker.direct_path(values.stage, directory=True)
    frames = [image_worker.direct_path(v) for v in values.frame]
    if not 1 <= len(frames) <= MAX_FRAMES or any(not p.is_relative_to(stage.parent / 'video_frames') for p in frames):
        raise Refused('Video frame child input scope refused')
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.vector_index import EmbeddingService
    service = EmbeddingService(values.model, 'stub-clip', 512, values.device, strict=True)
    runtime = service.describe_runtime()
    actual = str(next(service._clip_model.parameters()).device)
    if runtime.get('effective_provider') != 'open_clip' or actual != values.device:
        raise RuntimeError('Strict provider or device mismatch')
    vectors = []
    import numpy as np
    from PIL import Image
    for frame in frames:
        with Image.open(frame) as image:
            if (image.format != 'JPEG' or image.width > 1024 or image.height > 1024
                    or image.width * image.height > 1024**2):
                raise ValueError('bounded_keyframe_invalid')
            image.verify()
        vector = np.asarray(service.embed_image(str(frame)), dtype=np.float32)
        if vector.ndim != 1 or not np.isfinite(vector).all() or float(np.linalg.norm(vector)) == 0:
            raise RuntimeError('Invalid frame embedding')
        vectors.append(vector)
    if any(item.shape != vectors[0].shape for item in vectors[1:]):
        raise RuntimeError('Frame embedding dimensions differ')
    mean = np.mean(np.stack(vectors, axis=0), axis=0).astype(np.float32)
    norm = float(np.linalg.norm(mean))
    if not np.isfinite(mean).all() or not norm:
        raise RuntimeError('Invalid video embedding')
    vector = (mean / norm).astype(np.float32)
    vector_path = stage / 'vector.npy'
    with vector_path.open('xb') as stream:
        np.save(stream, vector, allow_pickle=False)
    receipt = {'provider': runtime['effective_provider'], 'effective_device': actual,
               'dimension': int(vector.shape[0]), 'frame_count': len(vectors),
               'normalized': True, 'model_version': values.model_version}
    with (stage / 'receipt.json').open('xb') as stream:
        stream.write(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode())
    return 0


def _run_inference(frames, stage, args, checkpoint, deadline):
    image_worker.gpu_free_memory(args.device, getattr(args, 'expected_gpu_uuid', None))
    argv = [sys.executable, '-I', str(Path(__file__).resolve()), '_video_embed',
            '--checkpoint', str(checkpoint), '--model', args.image_model,
            '--checkpoint-sha256', args.checkpoint_sha256,
            '--device', 'cpu' if args.device == 'cpu' else 'cuda:0',
            '--stage', str(stage), '--model-version', args.model_version]
    for frame in frames:
        argv.extend(('--frame', str(frame)))
    image_worker.run_supervised(argv, env=image_worker._child_environment(args.device, checkpoint),
        derived=args.derived_root, deadline=deadline)
    vector_path, receipt_path = stage / 'vector.npy', stage / 'receipt.json'
    if (not vector_path.is_file() or vector_path.is_symlink() or vector_path.stat().st_size > MAX_VECTOR_BYTES
            or not receipt_path.is_file() or receipt_path.is_symlink() or receipt_path.stat().st_size > 8192):
        raise ValueError('video_embedding_output_invalid')
    import numpy as np
    vector = np.load(vector_path, allow_pickle=False)
    receipt = json.loads(receipt_path.read_bytes())
    if (vector.ndim != 1 or vector.dtype != np.float32 or not np.isfinite(vector).all()
            or abs(float(np.linalg.norm(vector)) - 1.0) > 1e-4
            or receipt.get('provider') != 'open_clip'
            or receipt.get('effective_device') != ('cpu' if args.device == 'cpu' else 'cuda:0')
            or receipt.get('frame_count') != len(frames) or receipt.get('normalized') is not True
            or receipt.get('dimension') != len(vector)
            or receipt.get('model_version') != args.model_version):
        raise ValueError('video_embedding_output_invalid')
    return vector, hashlib.sha256(vector_path.read_bytes()).hexdigest()


def _process(candidate, database, originals, derived, args, checkpoint, checkpoint_identity, stop_file):
    source, source_identity = _source_path(candidate, originals)
    if image_worker.identity(checkpoint) != checkpoint_identity:
        raise RuntimeError('checkpoint_changed')
    deadline = time.monotonic() + MAX_TASK_SECONDS
    if image_worker.sha256_file(source, MAX_SOURCE_BYTES) != candidate['sha256']:
        raise ValueError('source_fingerprint_mismatch')
    frames = _frame_files(derived, candidate['asset_id'])
    if frames is None:
        raise ValueError('keyframe_output_invalid')
    fingerprints = [_fingerprint(frame) for frame in frames]
    stage = Path(tempfile.mkdtemp(prefix='.video-embed-', dir=derived))
    published = None; committed = False
    try:
        vector, checksum = _run_inference(frames, stage, args, checkpoint, deadline)
        if image_worker.identity(source) != source_identity or image_worker.identity(checkpoint) != checkpoint_identity:
            raise ValueError('source_or_checkpoint_changed')
        if image_worker.sha256_file(source, MAX_SOURCE_BYTES) != candidate['sha256']:
            raise ValueError('source_fingerprint_mismatch')
        if [_fingerprint(frame) for frame in frames] != fingerprints:
            raise ValueError('keyframe_changed')
        out_dir = image_worker._safe_output_dir(derived, 'video_embeddings')
        target = out_dir / f"{candidate['asset_id']}.npy"
        if os.path.lexists(target):
            raise ValueError('embedding_artifact_already_exists')
        with closing(_connect(database, writable=True)) as db:
            db.execute('BEGIN IMMEDIATE'); _validate_schema(db)
            asset = _video_asset(db, candidate['asset_id'])
            task = db.execute("SELECT state,cancel_requested FROM tasks WHERE id=? AND type='video_embed'",
                              (candidate['task_id'],)).fetchone()
            if os.path.lexists(stop_file):
                db.rollback(); raise RuntimeError('worker_stop_requested')
            if (asset is None or asset['path'] != candidate['path']
                    or asset['sha256'] != candidate['sha256'] or asset['bytes'] != candidate['bytes']
                    or asset['library_id'] != candidate['library_id'] or task != ('running', 0)
                    or os.path.lexists(target)):
                db.rollback(); raise ValueError('approval_scope_changed')
            if [image_worker.identity(frame) for frame in frames] != [item[:4] for item in fingerprints]:
                db.rollback(); raise ValueError('keyframe_changed')
            if image_worker.identity(source) != source_identity:
                db.rollback(); raise ValueError('source_or_checkpoint_changed')
            os.replace(stage / 'vector.npy', target); published = target
            changed = db.execute('''UPDATE tasks SET state='finished',finished_at=CURRENT_TIMESTAMP,last_error=NULL
                WHERE id=? AND type='video_embed' AND state='running' AND cancel_requested=0''',
                (candidate['task_id'],)).rowcount
            if changed != 1:
                db.rollback(); raise ValueError('task_ownership_lost')
            db.commit(); committed = True
        return True
    finally:
        if published is not None and not committed:
            try: published.unlink()
            except OSError: pass
        shutil.rmtree(stage, ignore_errors=True)


def _failure_code(error):
    code = str(error)
    allowed = {'source_fingerprint_mismatch','source_or_checkpoint_changed','checkpoint_changed',
        'keyframe_changed','keyframe_output_invalid','bounded_keyframe_invalid',
        'video_embedding_output_invalid','embedding_artifact_already_exists','approval_scope_changed',
        'task_ownership_lost','source_scope','source_file_changed'}
    if isinstance(error, TimeoutError): return 'task_timeout'
    if isinstance(error, RuntimeError) and code in {'worker_stop_requested','memory_budget','memory_floor','disk_reserve',
            'resource_observation_failed','hard_child_memory_cap_unavailable','gpu_memory_floor',
            'gpu_device_unverifiable'}: return code
    return code if isinstance(error, ValueError) and code in allowed else 'video_embed_worker_failure'


def _record_failure(database, candidate, error):
    tries = candidate['retry_count'] + 1
    safe_code = _failure_code(error)
    permanent = safe_code in {'source_fingerprint_mismatch','source_or_checkpoint_changed',
        'checkpoint_changed','keyframe_changed','keyframe_output_invalid','bounded_keyframe_invalid',
        'video_embedding_output_invalid','embedding_artifact_already_exists','approval_scope_changed',
        'task_ownership_lost','source_scope','source_file_changed'}
    state = 'failed' if permanent else 'pending' if tries < MAX_ATTEMPTS else 'dead'
    with closing(_connect(database, writable=True)) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('''UPDATE tasks SET state=?,retry_count=?,last_error=?,started_at=NULL,
            finished_at=CASE WHEN ? IN ('failed','dead') THEN CURRENT_TIMESTAMP ELSE NULL END,
            scheduled_at=CASE WHEN ?='pending' THEN datetime('now','+60 seconds') ELSE scheduled_at END
            WHERE id=? AND type='video_embed' AND state='running' ''',
            (state, tries, safe_code, state, state, candidate['task_id']))
        db.commit()


def run(args):
    database = image_worker.direct_path(args.database); originals = image_worker.direct_path(args.originals_root, directory=True)
    derived = image_worker.direct_path(args.derived_root, directory=True); checkpoint = image_worker.direct_path(args.checkpoint)
    stop_file = image_worker.direct_path(args.stop_file, new=True)
    if (stop_file in (database, checkpoint)
            or stop_file.parent.resolve(strict=True) != stop_file.parent):
        raise Refused('Stop path must be separate')
    checkpoint_identity = image_worker.identity(checkpoint)
    result = preflight(database, originals, derived, checkpoint, args.checkpoint_sha256,
        args.image_model, args.model_version, args.device, getattr(args, 'expected_gpu_uuid', None))
    if not args.execute:
        with image_worker.kernel_lock(database, blocking=True):
            provider = image_worker._probe_provider(args, checkpoint, deadline=time.monotonic()+MAX_TASK_SECONDS)
        result.update({'provider': provider['effective_provider'], 'effective_device': provider['effective_device'],
                       'selected_physical_device': provider['selected_physical_device'],
                       'selected_gpu_uuid': provider['selected_gpu_uuid']})
        return result
    if os.path.lexists(stop_file): raise Refused('Stop request already present')
    with image_worker.kernel_lock(database, blocking=True):
        provider = image_worker._probe_provider(args, checkpoint, deadline=time.monotonic()+MAX_TASK_SECONDS)
    stop = threading.Event(); previous = {}
    def request_stop(*_): stop.set()
    for sig in (signal.SIGINT, signal.SIGTERM, *([signal.SIGBREAK] if hasattr(signal, 'SIGBREAK') else [])):
        previous[sig] = signal.signal(sig, request_stop)
    attempted = completed = 0
    try:
        while not stop.is_set() and not os.path.lexists(stop_file):
            candidate = None
            try:
                with image_worker.kernel_lock(database, blocking=True):
                    candidate = _claim_one(database, derived)
                    if candidate is not None:
                        attempted += 1
                        completed += int(_process(candidate, database, originals, derived, args,
                                                  checkpoint, checkpoint_identity, stop_file))
            except Exception as error:
                if candidate is None: raise
                _record_failure(database, candidate, error)
                if args.once: break
            if candidate is None:
                if args.once: break
                stop.wait(POLL_SECONDS); continue
            if args.once: break
    finally:
        for sig, handler in previous.items(): signal.signal(sig, handler)
    return {'worker':'stopped','attempted':attempted,'completed':completed,
            'stopped_by_operator':stop.is_set() or os.path.lexists(stop_file),
            'provider':provider['effective_provider'],'effective_device':provider['effective_device'],
            'selected_physical_device':provider['selected_physical_device'],
            'selected_gpu_uuid':provider['selected_gpu_uuid']}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == '_video_embed':
        try: return _child(argv[1:])
        except Exception: return 2
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database','originals-root','derived-root','checkpoint','checkpoint-sha256',
                 'image-model','model-version','device','stop-file'):
        parser.add_argument('--'+name, required=True, choices=('cpu','cuda:0','cuda:1') if name=='device' else None)
    parser.add_argument('--expected-gpu-uuid'); parser.add_argument('--execute',action='store_true')
    parser.add_argument('--once',action='store_true')
    try:
        print(json.dumps(run(parser.parse_args(argv)), sort_keys=True)); return 0
    except Exception:
        print(json.dumps({'worker':'refused-or-interrupted','inspect_task_state':True}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
