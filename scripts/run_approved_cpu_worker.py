#!/usr/bin/env python3
"""Bounded CPU worker for approved member-upload thumbnails and perceptual hashes.

Default mode is read-only preflight. Execution is explicit and claims only
approved, library-mapped ``thumb`` and ``phash`` tasks. It never imports the
application executor or model/runtime packages.
"""
import argparse
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MEDIA_CHILD = ROOT / 'scripts' / 'home_media_worker.py'
RESOURCE_HELPER = ROOT / 'scripts' / 'home_preparation_resources.py'
sys.path.insert(0, str(ROOT / 'scripts'))
from home_preparation_resources import memory as observe_memory
REVISIONS = {'a8d4c2e6f901'}
KINDS = {'thumb', 'phash'}
MAX_INPUT = 256 * 1024**2
MAX_PIXELS = 64_000_000
MAX_DECODED_PIXELS = 64_000_000
MAX_JPEG_SOURCE_PIXELS = 64_000_000
MAX_OUTPUT = 2 * 1024**2
MAX_TASK_SECONDS = 120
MAX_TASK_RETRIES = 3
POLL_SECONDS = 2.0
MIN_FREE_RAM = 8 * 1024**3
MAX_CHILD_RSS = 1536 * 1024**2
LIMITS = {'256': (256, 256**2, MAX_OUTPUT), '1024': (1024, 1024**2, MAX_OUTPUT)}
POLICY = {'pixels': MAX_PIXELS, 'decoded_pixels': MAX_DECODED_PIXELS,
          'jpeg_source_pixels': MAX_JPEG_SOURCE_PIXELS}


class Refused(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('Invalid worker arguments')


def direct_path(value, *, directory=False, new=False):
    path = Path(value)
    if (not path.is_absolute() or path == Path(path.anchor) or '..' in path.parts
            or path.anchor.startswith(('//', '\\\\')) or len(str(value)) > 4096
            or any(ord(c) < 32 for c in str(value))):
        raise Refused('Explicit direct local path required')
    if path.parent.resolve(strict=True) != path.parent:
        raise Refused('Symlinked path component refused')
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


@contextmanager
def kernel_lock(database):
    lock = direct_path(str(database) + '.approved-cpu-worker.lock', new=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(lock, flags, 0o600), 'r+b', buffering=0) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != identity(lock)[:2]:
            raise Refused('Lock target changed')
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise Refused('Another approved CPU worker owns this database') from None
            try:
                yield
            finally:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise Refused('Another approved CPU worker owns this database') from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def connect(path, readonly=True):
    mode = 'ro' if readonly else 'rw'
    db = sqlite3.connect(path.as_uri() + f'?mode={mode}', uri=True, timeout=3)
    db.execute('PRAGMA trusted_schema=OFF')
    db.execute('PRAGMA foreign_keys=ON')
    if readonly:
        db.execute('PRAGMA query_only=ON')
    return db


def validate_schema(db):
    row = db.execute('SELECT version_num FROM alembic_version').fetchone()
    if not row or row[0] not in REVISIONS:
        raise Refused('Supported migrated database required')
    required = {'tasks', 'assets', 'access_uploads', 'access_asset_libraries', 'access_libraries'}
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required <= names:
        raise Refused('Required schema missing')
    columns = {table: {r[1] for r in db.execute(f'PRAGMA table_info({table})')} for table in required}
    required_columns = {
        'tasks': {'id', 'type', 'state', 'payload_json', 'retry_count', 'cancel_requested', 'scheduled_at', 'started_at', 'finished_at', 'last_error'},
        'assets': {'id', 'path', 'file_size', 'hash_sha256', 'mime', 'status', 'perceptual_hash'},
        'access_uploads': {'asset_id', 'state', 'sha256', 'bytes'},
        'access_asset_libraries': {'asset_id', 'library_id'},
        'access_libraries': {'id', 'state'},
    }
    if any(not required_columns[table] <= columns[table] for table in required):
        raise Refused('Required current schema columns missing')


def eligible(db):
    return db.execute('''SELECT t.id,t.type,t.payload_json,t.retry_count
      FROM tasks t
      WHERE t.state='pending' AND t.cancel_requested=0
        AND (t.scheduled_at IS NULL OR t.scheduled_at<=CURRENT_TIMESTAMP)
        AND t.type IN ('thumb','phash')
      ORDER BY t.priority,t.id''').fetchall()


def matching_candidates(db):
    result = []
    for row in eligible(db):
        try:
            payload = json.loads(row[2])
        except (TypeError, ValueError):
            continue
        if type(payload) is not dict or set(payload) != {'asset_id'} or type(payload['asset_id']) is not int:
            continue
        asset = db.execute('''SELECT a.id,a.path,a.file_size,a.hash_sha256,a.mime,a.status
            FROM assets a JOIN access_uploads u ON u.asset_id=a.id AND u.state='assigned'
              AND u.sha256=a.hash_sha256 AND u.bytes=a.file_size
            JOIN access_asset_libraries m ON m.asset_id=a.id
            JOIN access_libraries l ON l.id=m.library_id AND l.state='active'
            WHERE a.id=? AND (SELECT count(*) FROM access_asset_libraries x WHERE x.asset_id=a.id)=1''',
            (payload['asset_id'],)).fetchone()
        if asset:
            result.append((*row, *asset))
    return result


def preflight(database, originals, derived, stop_file):
    direct_path(database); originals = direct_path(originals, directory=True)
    derived = direct_path(derived, directory=True); direct_path(stop_file, new=True)
    with closing(connect(database)) as db:
        validate_schema(db)
        running = db.execute("SELECT count(*) FROM tasks WHERE state='running' AND type IN ('thumb','phash')").fetchone()[0]
        counts = dict(db.execute("SELECT type,count(*) FROM tasks WHERE state='pending' AND type IN ('thumb','phash') GROUP BY type"))
        approved = len(matching_candidates(db))
    return {'preflight': 'pass', 'activated': False, 'approved_claimable': approved,
            'pending_thumb': counts.get('thumb', 0), 'pending_phash': counts.get('phash', 0),
            'running_supported_tasks': running, 'execution': 'requires --execute'}


def source_info(row, originals):
    path = Path(row[5])
    direct_path(path)
    if not path.is_relative_to(originals) or path == originals:
        raise ValueError('source_scope')
    if type(row[6]) is not int or not 0 < row[6] <= MAX_INPUT:
        raise ValueError('source_size_policy')
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_size != row[6]:
        raise ValueError('source_file_changed')
    if row[8] not in ('image/jpeg', 'image/png') or row[9] != 'active':
        raise ValueError('source_media_profile')
    return path, info


def safe_output_dir(root, *parts):
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
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or current.resolve(strict=True) != current:
            raise ValueError('output_path_unsafe')
    return current


def _guard_resources(derived, stop_file, child, deadline):
    if os.path.lexists(stop_file):
        raise RuntimeError('operator_stop')
    if time.monotonic() >= deadline:
        raise RuntimeError('task_time_limit')
    if shutil.disk_usage(derived).free < 256 * 1024**2:
        raise RuntimeError('disk_reserve')
    try:
        if sys.platform.startswith('linux'):
            avail = int(dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())['MemAvailable'].split()[0]) * 1024
            rss = int(next(x.split()[1] for x in Path(f'/proc/{child.pid}/status').read_text().splitlines() if x.startswith('VmRSS:'))) * 1024
        elif sys.platform == 'darwin':
            avail, rss = observe_memory(child)
        elif sys.platform == 'win32':
            avail, rss = observe_memory(child)
        else:
            raise OSError('resource observation unsupported')
    except Exception as error:
        raise RuntimeError('resource_observation_failed') from error
    if avail < MIN_FREE_RAM or rss > MAX_CHILD_RSS:
        raise RuntimeError('memory_budget')


def run_child(args, cwd, derived, stop_file, deadline):
    if sys.platform.startswith('linux'):
        values = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        if int(values['MemAvailable'].split()[0]) * 1024 < MIN_FREE_RAM:
            raise RuntimeError('memory_floor')
    else:
        available, _ = observe_memory(None)
        if available < MIN_FREE_RAM:
            raise RuntimeError('memory_floor')
    job = None
    popen_options = {}
    if sys.platform == 'win32':
        from home_memory_envelope import WindowsJob
        job = WindowsJob(MAX_CHILD_RSS // 1024**2)
        popen_options['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    elif sys.platform.startswith('linux'):
        import resource
        if not hasattr(resource, 'RLIMIT_AS'):
            raise RuntimeError('hard_child_memory_cap_unavailable')
        def limits():
            resource.setrlimit(resource.RLIMIT_AS, (MAX_CHILD_RSS, MAX_CHILD_RSS))
        popen_options['preexec_fn'] = limits
    try:
        process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True, close_fds=True, **popen_options)
    except BaseException:
        if job is not None:
            job.close()
        raise
    try:
        while process.poll() is None:
            _guard_resources(derived, stop_file, process, deadline)
            time.sleep(0.1)
        out = process.stdout.read(64 * 1024)
        if process.returncode != 0:
            raise ValueError('bounded_decoder_failed')
        return json.loads(out)
    except BaseException:
        if process.poll() is None:
            process.kill(); process.wait()
        raise
    finally:
        process.stdout.close()
        if job is not None:
            job.close()


def sha_and_verify(path, expected_size, expected_hash, derived, stop_file, deadline):
    result = run_child([sys.executable, '-I', str(MEDIA_CHILD), 'hash', str(path), str(MAX_INPUT), 'false'],
                       ROOT, derived, stop_file, deadline)
    if result.get('bytes') != expected_size or result.get('sha256') != expected_hash:
        raise ValueError('source_fingerprint_mismatch')
    return result


def phash_from_image(path):
    import imagehash
    from PIL import Image
    with Image.open(path) as source:
        if source.format != 'JPEG' or source.size[0] * source.size[1] > 1024**2:
            raise ValueError('derived_profile')
        return str(imagehash.phash(source, hash_size=8, highfreq_factor=4))


def claim_one(database):
    with closing(connect(database, readonly=False)) as db:
        db.execute('BEGIN IMMEDIATE')
        validate_schema(db)
        if db.execute("SELECT 1 FROM tasks WHERE state='running' AND type IN ('thumb','phash') LIMIT 1").fetchone():
            db.rollback(); raise Refused('Existing running media task requires inspection')
        for row in matching_candidates(db):
            changed = db.execute("UPDATE tasks SET state='running',started_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=? AND state='pending' AND cancel_requested=0", (row[0],)).rowcount
            if changed == 1:
                db.commit(); return row
        db.rollback()
    return None


def approved_mapping(db, asset_id, size, digest):
    return db.execute('''SELECT 1 FROM access_uploads u JOIN access_asset_libraries m ON m.asset_id=u.asset_id
      JOIN access_libraries l ON l.id=m.library_id
      WHERE u.asset_id=? AND u.state='assigned' AND l.state='active'
        AND u.bytes=? AND u.sha256=?
        AND (SELECT count(*) FROM access_asset_libraries x WHERE x.asset_id=u.asset_id)=1
      LIMIT 1''', (asset_id, size, digest)).fetchone() is not None


def process_task(row, database, originals, derived, stop_file):
    task_id, kind, payload, retries, asset_id, path_value, size, digest, mime, status = row
    path, before = source_info(row, originals)
    deadline = time.monotonic() + MAX_TASK_SECONDS
    sha_and_verify(path, size, digest, derived, stop_file, deadline)
    stage = Path(tempfile.mkdtemp(prefix='.approved-cpu-', dir=derived))
    try:
        outputs = {}
        pending_publish = []
        if kind == 'thumb':
            outputs = run_child([sys.executable, '-I', str(MEDIA_CHILD), 'photo', str(path),
                json.dumps(POLICY, separators=(',', ':')), str(stage), json.dumps(LIMITS, separators=(',', ':'))],
                ROOT, derived, stop_file, deadline)
            if outputs.get('reason'):
                raise ValueError('decoder_profile:' + str(outputs['reason']))
            sha_and_verify(path, size, digest, derived, stop_file, deadline)
            for variant, (edge, _pixels, maximum) in LIMITS.items():
                candidate = stage / f'{variant}.jpg'
                if not candidate.is_file() or candidate.is_symlink() or candidate.stat().st_size > maximum:
                    raise ValueError('thumbnail_validation')
                from PIL import Image
                with Image.open(candidate) as image:
                    image.verify()
                    if image.format != 'JPEG' or max(image.size) > edge:
                        raise ValueError('thumbnail_validation')
                pending_publish.append((candidate, variant))
        elif kind == 'phash':
            one = {'512': (512, 512**2, MAX_OUTPUT)}
            outputs = run_child([sys.executable, '-I', str(MEDIA_CHILD), 'photo', str(path),
                json.dumps(POLICY, separators=(',', ':')), str(stage), json.dumps(one, separators=(',', ':'))],
                ROOT, derived, stop_file, deadline)
            if outputs.get('reason'):
                raise ValueError('decoder_profile:' + str(outputs['reason']))
            value = phash_from_image(stage / '512.jpg')
            if len(value) != 16:
                raise ValueError('phash_validation')
            sha_and_verify(path, size, digest, derived, stop_file, deadline)
        if identity(path) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise ValueError('source_changed_during_processing')
        with closing(connect(database, readonly=False)) as db:
            db.execute('BEGIN IMMEDIATE')
            validate_schema(db)
            if not approved_mapping(db, asset_id, size, digest):
                db.execute("UPDATE tasks SET state='pending',started_at=NULL,scheduled_at=CURRENT_TIMESTAMP,last_error='approval_scope_changed' WHERE id=? AND state='running'", (task_id,))
                db.commit(); return False
            current_asset = db.execute('SELECT path,hash_sha256,file_size,status FROM assets WHERE id=?', (asset_id,)).fetchone()
            if current_asset != (str(path), digest, size, 'active'):
                db.rollback(); raise ValueError('asset_record_changed')
            if os.path.lexists(stop_file):
                db.rollback(); raise RuntimeError('operator_stop')
            # Keep the approval mapping locked through publication so revocation
            # or unassignment cannot race derivative exposure.
            for candidate, variant in pending_publish:
                target = safe_output_dir(derived, 'thumbnails', variant) / f'{asset_id}.jpg'
                os.replace(candidate, target)
            if kind == 'phash':
                changed_asset = db.execute('UPDATE assets SET perceptual_hash=? WHERE id=? AND hash_sha256=? AND file_size=?', (value, asset_id, digest, size)).rowcount
                if changed_asset != 1:
                    db.rollback(); raise ValueError('asset_record_changed')
            done = db.execute("UPDATE tasks SET state='finished',finished_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=? AND state='running'", (task_id,)).rowcount
            if done != 1:
                db.rollback(); raise ValueError('task_ownership_lost')
            db.commit()
        return True
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def record_failure(database, task_id, retries, error):
    retry = retries + 1
    state = 'pending' if retry < MAX_TASK_RETRIES else 'failed'
    if isinstance(error, Refused):
        code = 'worker_refused'
    elif isinstance(error, TimeoutError):
        code = 'task_timeout'
    elif isinstance(error, (PermissionError, FileNotFoundError)):
        code = 'filesystem_access'
    elif isinstance(error, ValueError):
        code = 'input_or_output_validation'
    elif isinstance(error, RuntimeError):
        code = 'resource_or_operator_stop'
    else:
        code = 'worker_error'
    with closing(connect(database, readonly=False)) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('''UPDATE tasks SET state=?,retry_count=?,last_error=?,started_at=NULL,
          finished_at=CASE WHEN ?='failed' THEN CURRENT_TIMESTAMP ELSE NULL END,
          scheduled_at=CASE WHEN ?='pending' THEN datetime('now','+60 seconds') ELSE scheduled_at END
          WHERE id=? AND state='running' ''', (state, retry, code, state, state, task_id))
        db.commit()


def run(args):
    database = direct_path(args.database); originals = direct_path(args.originals_root, directory=True)
    derived = direct_path(args.derived_root, directory=True); stop_file = direct_path(args.stop_file, new=True)
    identities = (identity(database), identity(originals), identity(derived))
    result = preflight(database, originals, derived, stop_file)
    if not args.execute:
        return result
    if os.path.lexists(stop_file):
        raise Refused('Stop file present')
    with kernel_lock(database):
        if identities != (identity(database), identity(originals), identity(derived)) or os.path.lexists(stop_file):
            raise Refused('Worker target changed')
        if any(name in sys.modules for name in ('app.tasks', 'app.main', 'torch', 'transformers', 'onnxruntime', 'insightface')):
            raise Refused('Fresh isolated CPU process required')
        completed = attempted = 0
        while not os.path.lexists(stop_file):
            row = claim_one(database)
            if row is None:
                if args.once:
                    break
                if os.path.lexists(stop_file):
                    break
                time.sleep(POLL_SECONDS)
                continue
            attempted += 1
            try:
                completed += int(process_task(row, database, originals, derived, stop_file))
            except Exception as error:
                record_failure(database, row[0], row[3], error)
                if args.once:
                    break
            if args.once:
                break
        return {'worker': 'stopped', 'attempted': attempted, 'completed': completed,
                'stopped_by_operator': os.path.lexists(stop_file)}


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('--database', required=True); parser.add_argument('--originals-root', required=True)
    parser.add_argument('--derived-root', required=True); parser.add_argument('--stop-file', required=True)
    parser.add_argument('--execute', action='store_true'); parser.add_argument('--once', action='store_true')
    try:
        print(json.dumps(run(parser.parse_args(argv)), sort_keys=True)); return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({'worker': 'refused-or-interrupted', 'inspect_task_state': True}), file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
