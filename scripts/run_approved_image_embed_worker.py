#!/usr/bin/env python3
"""Bounded image-embedding worker for approved member uploads.

Preflight is read-only. The worker claims only due ``embed`` tasks whose exact
image payload belongs to an active, approved upload mapped to one active library.
It uses the strict local-checkpoint EmbeddingService in a supervised child and
never imports the mixed TaskExecutor.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
MEDIA_CHILD = ROOT / 'scripts' / 'home_media_worker.py'
sys.path.insert(0, str(ROOT / 'scripts'))
from home_preparation_resources import memory as observe_memory

REVISIONS = {'a8d4c2e6f901'}  # v36 resumable-upload schema
MAX_INPUT_BYTES = 256 * 1024**2
MAX_CHECKPOINT_BYTES = 8 * 1024**3
MAX_SOURCE_PIXELS = 64_000_000
MAX_DECODED_PIXELS = 64_000_000
MAX_DERIVATIVE_BYTES = 2 * 1024**2
MAX_VECTOR_BYTES = 128 * 1024
MAX_CHILD_RSS = 2 * 1024**3  # WindowsJob supports at most 2048 MiB.
MIN_FREE_RAM = 8 * 1024**3
MIN_FREE_VRAM = 2 * 1024**3
MAX_TASK_SECONDS = 600
MAX_ATTEMPTS = 3
POLL_SECONDS = 2.0
SUPPORTED_MIME = {'image/jpeg', 'image/png'}
MODEL_NAME_MAX = 64
MODEL_VERSION_MAX = 64


class Refused(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise Refused('Invalid worker arguments')


def direct_path(value, *, directory=False, new=False):
    path = Path(value)
    raw = str(value)
    if (not path.is_absolute() or path == Path(path.anchor) or '..' in path.parts
            or path.anchor.startswith(('//', '\\\\')) or len(raw) > 4096
            or any(ord(char) < 32 for char in raw)):
        raise Refused('Explicit absolute local path required')
    try:
        if path.parent.resolve(strict=True) != path.parent:
            raise Refused('Symlinked path component refused')
    except OSError as error:
        raise Refused('Path parent unavailable') from error
    if new and not os.path.lexists(path):
        return path
    try:
        info = path.lstat()
    except OSError as error:
        raise Refused('Required path unavailable') from error
    if stat.S_ISLNK(info.st_mode) or path.resolve(strict=True) != path:
        raise Refused('Symlinked path refused')
    if not (path.is_dir() if directory else path.is_file()):
        raise Refused('Unexpected path type')
    return path


def identity(path):
    info = path.lstat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def sha256_file(path, maximum):
    before = path.stat(follow_symlinks=False)
    pin = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
        raise ValueError('file_size_or_type')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != pin:
            raise ValueError('file_changed')
        while chunk := stream.read(4 * 1024**2):
            digest.update(chunk)
    after = path.stat(follow_symlinks=False)
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != pin:
        raise ValueError('file_changed')
    return digest.hexdigest()


def _sqlite(path, *, writable=False):
    mode = 'rw' if writable else 'ro'
    db = sqlite3.connect(path.as_uri() + f'?mode={mode}', uri=True, timeout=3)
    db.execute('PRAGMA trusted_schema=OFF')
    db.execute('PRAGMA foreign_keys=ON')
    if not writable:
        db.execute('PRAGMA query_only=ON')
    return db


def validate_schema(db):
    row = db.execute('SELECT version_num FROM alembic_version').fetchall()
    if len(row) != 1 or row[0][0] not in REVISIONS:
        raise Refused('Supported v36 migrated database required')
    required = {
        'tasks': {'id', 'type', 'payload_json', 'state', 'priority', 'retry_count',
                  'cancel_requested', 'scheduled_at', 'started_at', 'finished_at', 'last_error'},
        'assets': {'id', 'path', 'hash_sha256', 'file_size', 'mime', 'status'},
        'access_uploads': {'asset_id', 'state', 'sha256', 'bytes'},
        'access_asset_libraries': {'asset_id', 'library_id'},
        'access_libraries': {'id', 'state'},
        'embeddings': {'asset_id', 'modality', 'model', 'dim', 'storage_path',
                       'vector_checksum', 'device', 'model_version'},
    }
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required.keys() <= tables:
        raise Refused('Required v36 tables missing')
    for table, columns in required.items():
        actual = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
        if not columns <= actual:
            raise Refused('Required v36 columns missing')


def _upload_asset(db, asset_id):
    rows = db.execute('''SELECT a.id,a.path,a.hash_sha256,a.file_size,a.mime,a.status,
          u.sha256,u.bytes,m.library_id,l.state,
          (SELECT count(*) FROM access_asset_libraries m2 WHERE m2.asset_id=a.id),
          (SELECT count(*) FROM embeddings e WHERE e.asset_id=a.id AND e.modality='image')
      FROM assets a
      JOIN access_uploads u ON u.asset_id=a.id AND u.state='assigned'
      JOIN access_asset_libraries m ON m.asset_id=a.id
      JOIN access_libraries l ON l.id=m.library_id AND l.state='active'
      WHERE a.id=?''', (asset_id,)).fetchall()
    if len(rows) != 1:
        return None
    row = rows[0]
    if (row[5] != 'active' or row[4] not in SUPPORTED_MIME
            or type(row[3]) is not int or not 0 < row[3] <= MAX_INPUT_BYTES
            or row[2] != row[6] or row[3] != row[7]
            or row[10] != 1 or row[11] != 0):
        return None
    return {
        'asset_id': row[0], 'path': row[1], 'sha256': row[2], 'bytes': row[3],
        'mime': row[4], 'library_id': row[8],
    }


def _pending_due(db):
    return db.execute('''SELECT id,payload_json,retry_count,priority FROM tasks
        WHERE type='embed' AND state='pending' AND cancel_requested=0
          AND (scheduled_at IS NULL OR scheduled_at<=CURRENT_TIMESTAMP)
        ORDER BY priority,id''').fetchall()


def matching_candidates(db):
    return matching_candidates_with_skips(db)[0]


def matching_candidates_with_skips(db):
    candidates = []
    skipped = 0
    for task_id, raw_payload, retry_count, priority in _pending_due(db):
        try:
            payload = json.loads(raw_payload)
        except (TypeError, ValueError):
            skipped += 1
            continue
        if (type(payload) is not dict or set(payload) != {'asset_id', 'modality'}
                or type(payload.get('asset_id')) is not int or payload.get('modality') != 'image'):
            skipped += 1
            continue
        asset = _upload_asset(db, payload['asset_id'])
        if asset is None:
            skipped += 1
            continue
        candidates.append({
            'task_id': task_id, 'retry_count': retry_count, 'priority': priority,
            **asset,
        })
    return candidates, skipped


def validate_source(candidate, originals):
    path = direct_path(candidate['path'])
    try:
        if not path.is_relative_to(originals) or path == originals:
            raise ValueError('source_scope')
    except AttributeError:
        if originals not in path.parents:
            raise ValueError('source_scope')
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_size != candidate['bytes']:
        raise ValueError('source_file_changed')
    if path.suffix.lower() not in ('.jpg', '.jpeg', '.png'):
        raise ValueError('source_media_profile')
    return path, (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)


def _scope_still_valid(db, candidate):
    asset = _upload_asset(db, candidate['asset_id'])
    return bool(asset and asset['path'] == candidate['path']
                and asset['sha256'] == candidate['sha256']
                and asset['bytes'] == candidate['bytes']
                and asset['library_id'] == candidate['library_id'])


def preflight(database, originals, derived, checkpoint, checkpoint_sha256,
              image_model, model_version, device, expected_gpu_uuid=None):
    database = direct_path(database); originals = direct_path(originals, directory=True)
    derived = direct_path(derived, directory=True); checkpoint = direct_path(checkpoint)
    if (checkpoint.stat().st_size > MAX_CHECKPOINT_BYTES
            or len(checkpoint_sha256) != 64
            or any(ch not in '0123456789abcdef' for ch in checkpoint_sha256)):
        raise Refused('Invalid local checkpoint identity')
    if sha256_file(checkpoint, MAX_CHECKPOINT_BYTES) != checkpoint_sha256:
        raise Refused('Local checkpoint checksum mismatch')
    if not image_model.startswith('clip-') or len(image_model) > MODEL_NAME_MAX:
        raise Refused('Explicit supported image model required')
    if (not model_version or len(model_version) > MODEL_VERSION_MAX
            or any(ord(ch) < 33 for ch in model_version)):
        raise Refused('Explicit model version required')
    if device not in ('cpu', 'cuda:0', 'cuda:1'):
        raise Refused('Explicit CPU, cuda:0 or cuda:1 device required')
    if device == 'cpu':
        if expected_gpu_uuid:
            raise Refused('GPU UUID must be omitted for CPU execution')
    elif (not isinstance(expected_gpu_uuid, str) or not expected_gpu_uuid.startswith('GPU-')
          or len(expected_gpu_uuid) > 64):
        raise Refused('Explicit expected GPU UUID required for CUDA execution')
    with closing(_sqlite(database)) as db:
        validate_schema(db)
        running = db.execute("SELECT count(*) FROM tasks WHERE type='embed' AND state='running'").fetchone()[0]
        if running:
            raise Refused('Existing running embed task requires independent inspection')
        tasks, skipped = matching_candidates_with_skips(db)
        pending = db.execute("SELECT count(*) FROM tasks WHERE type='embed' AND state='pending'").fetchone()[0]
    return {
        'preflight': 'pass', 'activated': False, 'schema_revision': 'a8d4c2e6f901',
        'approved_claimable': len(tasks), 'pending_embed_all_states': pending,
        'skipped_due_embed': skipped,
        'image_model': image_model, 'model_version': model_version,
        'requested_device': device, 'checkpoint_sha256': checkpoint_sha256,
        'expected_gpu_uuid': expected_gpu_uuid,
        'checkpoint_verified_local': True, 'execution': 'requires --execute',
    }


@contextmanager
def kernel_lock(database, *, blocking=False):
    # Shared resource lock used by approved inference workers for this database.
    lock = direct_path(str(database) + '.approved-gpu-worker.lock', new=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(lock, flags, 0o600), 'r+b', buffering=0) as stream:
        opened = os.fstat(stream.fileno())
        current = lock.lstat()
        if (not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)):
            raise Refused('Worker lock target changed')
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
            except OSError:
                raise Refused('Another approved image embedding worker owns this database') from None
            try:
                yield
            finally:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise Refused('Another approved image embedding worker owns this database') from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _child_environment(device, checkpoint):
    keep = {
        'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA',
        'APPDATA', 'PROGRAMDATA', 'VIRTUAL_ENV', 'PATHEXT', 'NUMBER_OF_PROCESSORS',
        'PROCESSOR_ARCHITECTURE', 'HOME', 'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH',
        'CUDA_PATH', 'CUDA_PATH_V12_0', 'CUDA_PATH_V12_1', 'CUDA_PATH_V12_2',
        'CUDA_PATH_V12_3', 'CUDA_PATH_V12_4', 'CUDA_PATH_V12_5', 'CUDA_PATH_V12_6',
        'CUDA_PATH_V12_8', 'CUDNN_PATH',
    }
    env = {key: value for key, value in os.environ.items() if key in keep}
    env.update({
        'PHOTOHOUSE_NO_DOTENV': '1', 'PHOTOHOUSE_STRICT_INFERENCE': '1',
        'PHOTOHOUSE_IMAGE_EMBEDDING_CHECKPOINT': str(checkpoint),
        'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
        'HF_HUB_DISABLE_TELEMETRY': '1', 'CUDA_VISIBLE_DEVICES': '' if device == 'cpu' else device.split(':')[1],
        'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
        'NUMEXPR_NUM_THREADS': '1',
    })
    return env


def _check_resources(process, derived, deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError('task_time_limit')
    if shutil.disk_usage(derived).free < 256 * 1024**2:
        raise RuntimeError('disk_reserve')
    try:
        available, rss = observe_memory(process)
    except Exception as error:
        raise RuntimeError('resource_observation_failed') from error
    if available < MIN_FREE_RAM or rss > MAX_CHILD_RSS:
        raise RuntimeError('memory_budget')


def gpu_free_memory(device, expected_gpu_uuid=None):
    if device == 'cpu':
        return None
    try:
        physical_index = int(device.partition(':')[2])
        if physical_index not in (0, 1):
            raise ValueError
    except (ValueError, TypeError):
        raise RuntimeError('gpu_device_unverifiable') from None
    executable = shutil.which('nvidia-smi') or shutil.which('nvidia-smi.exe')
    if not executable:
        raise RuntimeError('gpu_device_unverifiable')
    try:
        if not isinstance(expected_gpu_uuid, str) or not expected_gpu_uuid.startswith('GPU-'):
            raise ValueError
        process = subprocess.Popen(
            [executable, f'--id={physical_index}', '--query-gpu=uuid,memory.free',
             '--format=csv,noheader,nounits'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        output = []
        reader = threading.Thread(target=lambda: output.append(process.stdout.read(4097)), daemon=True)
        reader.start()
        try:
            returncode = process.wait(timeout=3)
            reader.join(timeout=1)
        except BaseException:
            process.kill(); process.wait()
            reader.join(timeout=1)
            raise
        finally:
            if process.stdout is not None:
                process.stdout.close()
        raw = output[0] if output else b''
        if returncode != 0 or reader.is_alive() or len(raw) > 4096:
            raise ValueError
        lines = raw.decode('ascii', errors='strict').splitlines()
        if len(lines) != 1:
            raise ValueError
        fields = [field.strip() for field in lines[0].split(',')]
        if (len(fields) != 2 or not fields[0].startswith('GPU-')
                or not fields[1].isdecimal()):
            raise ValueError
        actual_uuid, free_bytes = fields[0], int(fields[1]) * 1024**2
        if actual_uuid != expected_gpu_uuid:
            raise ValueError
    except Exception as error:
        raise RuntimeError('gpu_device_unverifiable') from error
    if free_bytes < MIN_FREE_VRAM:
        raise RuntimeError('gpu_memory_floor')
    return free_bytes


def run_supervised(argv, *, env, derived, deadline, capture_stdout=False):
    if sys.platform == 'win32' or sys.platform == 'darwin':
        try:
            available, _ = observe_memory(None)
        except Exception as error:
            raise RuntimeError('resource_observation_failed') from error
    elif sys.platform.startswith('linux'):
        values = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        available = int(values['MemAvailable'].split()[0]) * 1024
    else:
        raise RuntimeError('resource_observation_unsupported')
    if available < MIN_FREE_RAM:
        raise RuntimeError('memory_floor')
    job = None
    options = {}
    if sys.platform == 'win32':
        try:
            from home_memory_envelope import WindowsJob
            job = WindowsJob(MAX_CHILD_RSS // 1024**2)
        except Exception as error:
            raise RuntimeError('hard_child_memory_cap_unavailable') from error
        options['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    try:
        proc = subprocess.Popen(
            argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True, **options,
        )
    except BaseException:
        if job is not None:
            job.close()
        raise
    try:
        while proc.poll() is None:
            _check_resources(proc, derived, deadline)
            time.sleep(0.1)
        output = proc.stdout.read(64 * 1024) if capture_stdout else b''
        if proc.returncode != 0:
            raise ValueError('child_process_failed')
        return output
    except BaseException:
        if proc.poll() is None:
            proc.kill(); proc.wait()
        raise
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        if job is not None:
            job.close()


def _probe_provider(args, checkpoint, *, deadline):
    free_vram = gpu_free_memory(args.device, getattr(args, 'expected_gpu_uuid', None))
    fd, receipt_name = tempfile.mkstemp(prefix='.embed-probe-', suffix='.json', dir=args.derived_root)
    os.close(fd)
    receipt = Path(receipt_name)
    receipt.unlink()
    try:
        argv = [sys.executable, '-I', str(Path(__file__).resolve()), '_probe',
                '--checkpoint', str(checkpoint), '--image-model', args.image_model,
                '--device', args.device, '--receipt', str(receipt)]
        run_supervised(argv, env=_child_environment(args.device, checkpoint),
                       derived=args.derived_root, deadline=deadline)
        raw = receipt.read_bytes()
        if len(raw) > 8192:
            raise Refused('Provider preflight receipt too large')
        result = json.loads(raw)
        if (result.get('provider') != 'open_clip'
                or result.get('effective_device') != ('cpu' if args.device == 'cpu' else 'cuda:0')
                or result.get('dimension') not in (512, 768, 1024, 1280, 2560)):
            raise Refused('Strict image provider/device preflight did not match configuration')
        result['selected_physical_device'] = args.device
        result['selected_gpu_uuid'] = getattr(args, 'expected_gpu_uuid', None)
        result['free_vram_bytes_at_preflight'] = free_vram
        return result
    finally:
        try: receipt.unlink()
        except OSError: pass


def _claim_one(database):
    with closing(_sqlite(database, writable=True)) as db:
        db.execute('BEGIN IMMEDIATE')
        validate_schema(db)
        if db.execute("SELECT 1 FROM tasks WHERE type='embed' AND state='running' LIMIT 1").fetchone():
            db.rollback(); raise Refused('Existing running embed task requires independent inspection')
        for candidate in matching_candidates(db):
            changed = db.execute('''UPDATE tasks SET state='running',started_at=CURRENT_TIMESTAMP,
                last_error=NULL WHERE id=? AND type='embed' AND state='pending'
                  AND cancel_requested=0''', (candidate['task_id'],)).rowcount
            if changed == 1:
                db.commit(); return candidate
        db.rollback()
    return None


def _run_bounded_decoder(source, stage, derived, deadline, stop_file):
    policy = {'pixels': MAX_SOURCE_PIXELS, 'decoded_pixels': MAX_DECODED_PIXELS,
              'jpeg_source_pixels': MAX_SOURCE_PIXELS}
    limits = {'1024': (1024, 1024**2, MAX_DERIVATIVE_BYTES)}
    argv = [sys.executable, '-I', str(MEDIA_CHILD), 'photo', str(source),
            json.dumps(policy, separators=(',', ':')), str(stage),
            json.dumps(limits, separators=(',', ':'))]
    decoder_env = {key: value for key, value in os.environ.items()
                   if key in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'HOME', 'USERPROFILE'}}
    decoder_env.update({'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'})
    output = run_supervised(argv, env=decoder_env,
                            derived=derived, deadline=deadline, capture_stdout=True)
    if len(output) > 8192:
        raise ValueError('decoder_receipt')
    result = json.loads(output)
    if result.get('reason'):
        raise ValueError('unsupported_image_profile')
    candidate = stage / '1024.jpg'
    if not candidate.is_file() or candidate.is_symlink() or candidate.stat().st_size > MAX_DERIVATIVE_BYTES:
        raise ValueError('bounded_image_validation')
    import numpy as np
    from PIL import Image
    with Image.open(candidate) as image:
        image.verify()
        if image.format != 'JPEG' or image.width * image.height > 1024**2 or max(image.size) > 1024:
            raise ValueError('bounded_image_validation')
    return candidate


def _run_embed_child(image, stage, args, checkpoint, deadline):
    gpu_free_memory(args.device, getattr(args, 'expected_gpu_uuid', None))
    vector_path = stage / 'vector.npy'
    receipt = stage / 'result.json'
    argv = [sys.executable, '-I', str(Path(__file__).resolve()), '_embed',
            '--image', str(image), '--stage', str(stage), '--checkpoint', str(checkpoint),
            '--image-model', args.image_model, '--device', args.device,
            '--model-version', args.model_version, '--receipt', str(receipt)]
    run_supervised(argv, env=_child_environment(args.device, checkpoint),
                   derived=args.derived_root, deadline=deadline)
    if (not vector_path.is_file() or vector_path.is_symlink()
            or vector_path.stat().st_size > MAX_VECTOR_BYTES):
        raise ValueError('embedding_output_validation')
    if not receipt.is_file() or receipt.is_symlink() or receipt.stat().st_size > 8192:
        raise ValueError('embedding_receipt_validation')
    metadata = json.loads(receipt.read_bytes())
    if (metadata.get('provider') != 'open_clip'
            or metadata.get('effective_device') != ('cpu' if args.device == 'cpu' else 'cuda:0')
            or metadata.get('model_version') != args.model_version):
        raise ValueError('embedding_provider_validation')
    import numpy as np
    vector = np.load(vector_path, allow_pickle=False)
    if (vector.ndim != 1 or vector.dtype != np.float32
            or vector.shape[0] != metadata.get('dimension')
            or not np.isfinite(vector).all() or float(np.linalg.norm(vector)) == 0.0):
        raise ValueError('embedding_output_validation')
    return vector, metadata, hashlib.sha256(vector_path.read_bytes()).hexdigest()


def _process_task(candidate, database, originals, derived, args, checkpoint,
                  checkpoint_identity, stop_file):
    source, source_identity = validate_source(candidate, originals)
    if identity(checkpoint) != checkpoint_identity:
        raise RuntimeError('checkpoint_changed')
    deadline = time.monotonic() + MAX_TASK_SECONDS
    if sha256_file(checkpoint, MAX_CHECKPOINT_BYTES) != args.checkpoint_sha256:
        raise RuntimeError('checkpoint_changed')
    if sha256_file(source, MAX_INPUT_BYTES) != candidate['sha256']:
        raise ValueError('source_fingerprint_mismatch')
    stage = Path(tempfile.mkdtemp(prefix='.approved-embed-', dir=derived))
    published = None
    committed = False
    try:
        bounded_image = _run_bounded_decoder(source, stage, derived, deadline, stop_file)
        if sha256_file(source, MAX_INPUT_BYTES) != candidate['sha256']:
            raise ValueError('source_fingerprint_mismatch')
        vector, runtime, vector_checksum = _run_embed_child(
            bounded_image, stage, args, checkpoint, deadline)
        if identity(source) != source_identity or identity(checkpoint) != checkpoint_identity:
            raise ValueError('source_or_checkpoint_changed')
        if sha256_file(source, MAX_INPUT_BYTES) != candidate['sha256']:
            raise ValueError('source_fingerprint_mismatch')
        embedding_dir = _safe_output_dir(derived, 'embeddings')
        final_path = embedding_dir / f"{candidate['asset_id']}.npy"
        if os.path.lexists(final_path):
            raise ValueError('embedding_artifact_already_exists')
        with closing(_sqlite(database, writable=True)) as db:
            db.execute('BEGIN IMMEDIATE')
            validate_schema(db)
            if not _scope_still_valid(db, candidate):
                db.execute("UPDATE tasks SET state='failed',finished_at=CURRENT_TIMESTAMP,last_error='approval_scope_changed' WHERE id=? AND state='running'",
                           (candidate['task_id'],))
                db.commit(); return False
            task = db.execute('''SELECT state,cancel_requested FROM tasks WHERE id=? AND type='embed' ''',
                              (candidate['task_id'],)).fetchone()
            if task != ('running', 0):
                db.rollback(); raise ValueError('task_state_changed')
            if db.execute("SELECT 1 FROM embeddings WHERE asset_id=? AND modality='image'",
                          (candidate['asset_id'],)).fetchone():
                db.rollback(); raise ValueError('embedding_record_already_exists')
            if os.path.lexists(final_path) or os.path.lexists(stop_file):
                db.rollback(); raise RuntimeError('publish_target_or_stop_request')
            os.replace(stage / 'vector.npy', final_path)
            published = final_path
            db.execute('''INSERT INTO embeddings
                (asset_id,modality,model,dim,storage_path,vector_checksum,device,model_version)
                VALUES (?,'image',?,?,?,?,?,?)''',
                (candidate['asset_id'], args.image_model, int(vector.shape[0]), str(final_path),
                 vector_checksum, args.device, args.model_version))
            done = db.execute("UPDATE tasks SET state='finished',finished_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=? AND state='running' AND cancel_requested=0",
                              (candidate['task_id'],)).rowcount
            if done != 1:
                db.rollback(); raise ValueError('task_ownership_lost')
            db.commit(); committed = True
        return True
    finally:
        if published is not None and not committed:
            try: published.unlink()
            except OSError: pass
        shutil.rmtree(stage, ignore_errors=True)


def _safe_output_dir(root, *parts):
    current = root
    for part in parts:
        if part in ('', '.', '..') or '/' in part or '\\' in part:
            raise ValueError('output_path_invalid')
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            current.mkdir()
            info = current.lstat()
        if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode)
                or current.resolve(strict=True) != current):
            raise ValueError('output_path_unsafe')
    return current


def _failure_code(error):
    if isinstance(error, TimeoutError): return 'task_timeout'
    if isinstance(error, PermissionError): return 'filesystem_access'
    if isinstance(error, ValueError): return str(error) if str(error) in {
        'source_fingerprint_mismatch', 'unsupported_image_profile',
        'bounded_image_validation', 'embedding_output_validation',
        'embedding_provider_validation', 'embedding_artifact_already_exists',
        'embedding_record_already_exists', 'task_state_changed', 'task_ownership_lost',
        'source_or_checkpoint_changed', 'file_size_or_type', 'file_changed',
        'source_scope', 'source_file_changed', 'source_media_profile',
    } else 'input_or_output_validation'
    if isinstance(error, RuntimeError): return str(error) if str(error) in {
        'memory_budget', 'memory_floor', 'resource_observation_failed',
        'resource_observation_unsupported', 'disk_reserve', 'checkpoint_changed',
        'publish_target_or_stop_request', 'hard_child_memory_cap_unavailable',
        'gpu_device_unverifiable', 'gpu_memory_floor',
    } else 'provider_or_worker_failure'
    if isinstance(error, FileNotFoundError): return 'filesystem_access'
    return 'worker_error'


def record_failure(database, task_id, retry_count, error):
    code = _failure_code(error)
    permanent = isinstance(error, (ValueError, PermissionError, FileNotFoundError))
    attempts = retry_count + 1
    state = 'failed' if permanent else 'pending' if attempts < MAX_ATTEMPTS else 'dead'
    with closing(_sqlite(database, writable=True)) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('''UPDATE tasks SET state=?,retry_count=?,last_error=?,started_at=NULL,
          finished_at=CASE WHEN ? IN ('failed','dead') THEN CURRENT_TIMESTAMP ELSE NULL END,
          scheduled_at=CASE WHEN ?='pending' THEN datetime('now','+60 seconds') ELSE scheduled_at END
          WHERE id=? AND state='running' AND type='embed' ''',
          (state, attempts, code, state, state, task_id))
        db.commit()


def _probe_or_embed_child(args):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('operation', choices=('_probe', '_embed'))
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--image-model', required=True)
    parser.add_argument('--device', required=True)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--image')
    parser.add_argument('--stage')
    parser.add_argument('--model-version')
    values = parser.parse_args(args)
    checkpoint = direct_path(values.checkpoint)
    if not values.image_model.startswith('clip-') or values.device not in ('cpu', 'cuda:0'):
        raise Refused('Unsupported child model or device')
    if values.operation == '_embed':
        image = direct_path(values.image)
        stage = direct_path(values.stage, directory=True)
        if not image.is_relative_to(stage) or not Path(values.receipt).is_relative_to(stage):
            raise Refused('Child artifact path outside private stage')
        if not values.model_version:
            raise Refused('Model version required')
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.vector_index import EmbeddingService
    service = EmbeddingService(values.image_model, 'stub-clip', 512,
                               values.device, strict=True)
    runtime = service.describe_runtime()
    try:
        actual_device = str(next(service._clip_model.parameters()).device)
    except Exception as error:
        raise RuntimeError('Effective model device could not be verified') from error
    expected_device = values.device
    if runtime.get('effective_provider') != 'open_clip' or actual_device != expected_device:
        raise RuntimeError('Strict provider or device preflight mismatch')
    runtime['effective_device'] = actual_device
    if values.operation == '_probe':
        _write_json_receipt(Path(values.receipt), runtime)
        return 0
    import numpy as np
    from PIL import Image
    with Image.open(image) as opened:
        if opened.format != 'JPEG' or opened.width * opened.height > 1024**2:
            raise ValueError('bounded_image_validation')
        opened.verify()
    vector = np.asarray(service.embed_image(str(image)), dtype=np.float32)
    if (vector.ndim != 1 or not np.isfinite(vector).all()
            or float(np.linalg.norm(vector)) == 0.0):
        raise RuntimeError('Invalid strict image vector')
    vector_path = stage / 'vector.npy'
    with vector_path.open('xb') as stream:
        np.save(stream, vector, allow_pickle=False)
    runtime.update({'dimension': int(vector.shape[0]), 'model_version': values.model_version})
    _write_json_receipt(Path(values.receipt), runtime)
    return 0


def _write_json_receipt(path, value):
    if os.path.lexists(path):
        raise Refused('Receipt already exists')
    raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')
    if len(raw) > 8192:
        raise ValueError('receipt_too_large')
    with path.open('xb') as stream:
        stream.write(raw)


def run(args):
    database = direct_path(args.database); originals = direct_path(args.originals_root, directory=True)
    derived = direct_path(args.derived_root, directory=True); checkpoint = direct_path(args.checkpoint)
    stop_file = direct_path(args.stop_file, new=True)
    if stop_file in (database, checkpoint) or stop_file.parent.resolve(strict=True) != stop_file.parent:
        raise Refused('Stop path must be separate')
    checkpoint_identity = identity(checkpoint)
    targets = (identity(database)[:2], identity(originals)[:2], identity(derived)[:2])
    result = preflight(database, originals, derived, checkpoint, args.checkpoint_sha256,
                       args.image_model, args.model_version, args.device,
                       getattr(args, 'expected_gpu_uuid', None))
    if not args.execute:
        with kernel_lock(database, blocking=True):
            provider = _probe_provider(args, checkpoint,
                                       deadline=time.monotonic() + MAX_TASK_SECONDS)
        result.update({'provider': provider['effective_provider'],
                       'effective_device': provider['effective_device'],
                       'selected_physical_device': provider['selected_physical_device'],
                       'selected_gpu_uuid': provider['selected_gpu_uuid']})
        return result
    if os.path.lexists(stop_file):
        raise Refused('Stop request already present')
    if targets != (identity(database)[:2], identity(originals)[:2], identity(derived)[:2]):
        raise Refused('Worker target changed')
    if os.path.lexists(stop_file):
        raise Refused('Stop request arrived before startup')
    # Verify the exact model and actual provider/device before any task claim.
    with kernel_lock(database, blocking=True):
        provider = _probe_provider(args, checkpoint,
                                   deadline=time.monotonic() + MAX_TASK_SECONDS)
    stop = threading.Event()
    previous = {}
    def request_stop(*_): stop.set()
    for sig in (signal.SIGINT, signal.SIGTERM, *([signal.SIGBREAK] if hasattr(signal, 'SIGBREAK') else [])):
        previous[sig] = signal.signal(sig, request_stop)
    attempted = completed = 0
    try:
        while not stop.is_set() and not os.path.lexists(stop_file):
            candidate = None
            try:
                with kernel_lock(database, blocking=True):
                    candidate = _claim_one(database)
                    if candidate is None:
                        if args.once:
                            break
                    else:
                        attempted += 1
                        completed += int(_process_task(candidate, database, originals, derived,
                                                       args, checkpoint, checkpoint_identity, stop_file))
            except Exception as error:
                if candidate is None:
                    raise
                record_failure(database, candidate['task_id'], candidate['retry_count'], error)
                if args.once:
                    break
            if candidate is None:
                stop.wait(POLL_SECONDS)
                continue
            if args.once:
                break
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return {
        'worker': 'stopped', 'attempted': attempted, 'completed': completed,
        'stopped_by_operator': stop.is_set() or os.path.lexists(stop_file),
        'provider': provider['effective_provider'],
        'effective_device': provider['effective_device'],
        'selected_physical_device': provider['selected_physical_device'],
        'selected_gpu_uuid': provider['selected_gpu_uuid'],
    }


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in ('_probe', '_embed'):
        try:
            return _probe_or_embed_child(argv)
        except Exception:
            return 2
    parser = Parser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--originals-root', required=True)
    parser.add_argument('--derived-root', required=True)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--checkpoint-sha256', required=True)
    parser.add_argument('--image-model', required=True)
    parser.add_argument('--model-version', required=True)
    parser.add_argument('--device', required=True, choices=('cpu', 'cuda:0', 'cuda:1'))
    parser.add_argument('--expected-gpu-uuid')
    parser.add_argument('--stop-file', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--once', action='store_true')
    try:
        print(json.dumps(run(parser.parse_args(argv)), sort_keys=True)); return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({'worker': 'refused-or-interrupted', 'inspect_task_state': True}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
