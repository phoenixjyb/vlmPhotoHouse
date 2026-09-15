#!/usr/bin/env python3
"""Explicit caption-only worker; read-only preflight unless --execute is supplied.

No HTTP listener, schema creation/migration, queue repair, or service control.
Run in a dedicated process, never import into the protected web application.
"""
import argparse
from contextlib import closing, contextmanager
import json
import math
import os
from pathlib import Path
import signal
import sqlite3
import sys
import threading
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
REVISIONS = ('d2b7e4f6a901', 'c7f4a9e2b610')
NUMBERS = {
    'CAPTION_WORD_LIMIT': (0, 10000, int), 'CAPTION_MAX_VARIANTS': (1, 100, int),
    'CAPTION_POLICY_MAX_RETRIES': (0, 10, int), 'CAPTION_HTTP_RETRIES': (1, 10, int),
    'CAPTION_HTTP_TIMEOUT_SEC': (5, 1800, float), 'CAPTION_HTTP_RETRY_DELAY_SEC': (0, 60, float),
    'CAPTION_HTTP_MAX_IMAGE_EDGE': (64, 8192, int), 'MAX_TASK_RETRIES': (1, 100, int),
    'RETRY_BACKOFF_BASE_SECONDS': (0, 3600, float),
    'RETRY_BACKOFF_CAP_SECONDS': (0, 86400, float), 'RETRY_BACKOFF_JITTER': (0, 1, float),
}
TEXT = {'CAPTION_PROMPT', 'CAPTION_PROFILE', 'CAPTION_INFANT_CARE_ASSET_IDS'}


class Refused(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('Invalid worker arguments')  # do not echo accidental secrets


def direct_path(value, *, directory=False, new=False):
    path = Path(value)
    if (not path.is_absolute() or '..' in path.parts or path.anchor.startswith(('//', '\\\\'))
            or path.parent.resolve(strict=True) != path.parent):
        raise Refused('Explicit direct local path required')
    if new and not os.path.lexists(path):
        return path
    if path.resolve(strict=True) != path or not (path.is_dir() if directory else path.is_file()):
        raise Refused('Unexpected path type')
    return path


def reviewed_environment(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Refused('Duplicate configuration key')
            result[key] = value
        return result
    with direct_path(path).open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise Refused('Configuration too large')
    values = json.loads(raw, object_pairs_hook=unique)
    if type(values) is not dict or not set(values) <= (NUMBERS.keys() | TEXT):
        raise Refused('Unsupported worker configuration')
    for key, value in values.items():
        if type(value) is not str or '\x00' in value:
            raise Refused('Configuration values must be strings')
        if key in NUMBERS:
            low, high, kind = NUMBERS[key]
            number = kind(value)
            if not math.isfinite(number) or not low <= number <= high:
                raise Refused('Configuration outside supported range')
    return values


def caption_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1'
            or parsed.port is None or not 1 <= parsed.port <= 65535
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise Refused('Explicit loopback caption endpoint required')
    return value.rstrip('/')


def preflight(database, revision):
    database = direct_path(database)
    if revision not in REVISIONS:
        raise Refused('Unqualified schema revision')
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True, timeout=3)) as db:
        db.execute('PRAGMA query_only=ON')
        if db.execute('SELECT version_num FROM alembic_version').fetchall() != [(revision,)]:
            raise Refused('Database revision does not match explicit selection')
        if db.execute("SELECT 1 FROM tasks WHERE type='caption' AND state='running' LIMIT 1").fetchone():
            raise Refused('Running caption task requires independent drain or recovery review')
    return {'preflight': 'pass', 'revision': revision, 'task_type': 'caption', 'activated': False}


def connect_existing(database):
    db = sqlite3.connect(database.as_uri()+'?mode=rw', uri=True, timeout=3)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        return db
    except BaseException:
        db.close()
        raise


@contextmanager
def worker_lock(database):
    """OS-held lock shared by this launcher only; never delete the lock inode.

    The legacy API does not honor this lock. Its shutdown is an external gate.
    Lock contents are not a liveness receipt; the kernel releases it on exit.
    """
    path = direct_path(str(database)+'.caption-worker.lock', new=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path, flags, 0o600), 'r+b', buffering=0) as stream:
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise Refused('Another caption-only worker owns this database') from None
            try:
                yield
            finally:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise Refused('Another caption-only worker owns this database') from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def drain_loop(executor, stop, stop_file, *, once=False, poll_seconds=1.0):
    """Synchronous execution: stop requests never interrupt an in-flight handler."""
    completed = 0
    while not stop.is_set() and not os.path.lexists(stop_file):
        worked = executor.run_once()
        completed += int(bool(worked))
        if once:
            break
        if not worked:
            stop.wait(poll_seconds)
    return completed


def configure_process(database, derived, temporary, endpoint, values):
    if any(name in sys.modules for name in ('app.config', 'app.tasks', 'app.dependencies', 'app.main')):
        raise Refused('Worker requires a fresh dedicated process')
    # Do not inherit caption policy/provider or retry values from an unrelated shell.
    for key in list(os.environ):
        if key.startswith(('CAPTION_', 'RETRY_BACKOFF')) or key == 'MAX_TASK_RETRIES':
            del os.environ[key]
    os.environ.update(values)
    os.environ.update({
        'PHOTOHOUSE_NO_DOTENV': '1', 'DATABASE_URL': 'sqlite:///'+database.as_posix(),
        'DERIVED_PATH': str(derived), 'VLM_TMP_DIR': str(temporary),
        'CAPTION_PROVIDER': 'http', 'CAPTION_SERVICE_URL': endpoint, 'CAPTION_EXTERNAL_DIR': '',
        'CAPTION_ENABLE_STUB_FALLBACK': 'false', 'CAPTION_AUTO_TAG_ENABLE': 'false',
        'ENABLE_INLINE_WORKER': 'false', 'AUTO_MIGRATE': 'false', 'RUN_MODE': 'worker',
        'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
        'NUMEXPR_NUM_THREADS': '1', 'CUDA_VISIBLE_DEVICES': '',
    })
    os.environ.setdefault('CAPTION_WORD_LIMIT', '0')


def run(args):
    database = direct_path(args.database)
    derived = direct_path(args.derived, directory=True)
    temporary = direct_path(args.temporary, directory=True)
    stop_file = direct_path(args.stop_file, new=True)
    if stop_file in (database, Path(str(database)+'.caption-worker.lock')):
        raise Refused('Stop path must be separate from database and lock')
    endpoint = caption_url(args.caption_url)
    values = reviewed_environment(args.environment_json)
    result = preflight(database, args.expected_revision)
    if not args.execute:
        return result
    if not args.legacy_worker_stopped:
        raise Refused('Independent legacy worker shutdown confirmation required')
    if os.path.lexists(stop_file):
        raise Refused('Stop request is already present')
    with worker_lock(database):
        preflight(database, args.expected_revision)
        configure_process(database, derived, temporary, endpoint, values)
        sys.path.insert(0, str(ROOT/'backend'))
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.config import get_settings
        from app.tasks import TaskExecutor
        from app.caption_service import get_caption_provider
        # Health/model identity check before a task can be claimed. No local model.
        provider = get_caption_provider()
        if not provider.get_model_name().startswith('qwen3-vl-http'):
            raise Refused('Qwen3 HTTP provider is not ready')
        engine = create_engine('sqlite://', creator=lambda: connect_existing(database))
        stop = threading.Event()
        handlers = {}
        try:
            for sig in (signal.SIGINT, signal.SIGTERM, *([signal.SIGBREAK] if hasattr(signal, 'SIGBREAK') else [])):
                handlers[sig] = signal.signal(sig, lambda *_: stop.set())
            executor = TaskExecutor(sessionmaker(bind=engine), get_settings(), caption_only=True)
            completed = drain_loop(executor, stop, stop_file, once=args.once)
            return {'worker': 'stopped', 'claimed_tasks_processed': completed, 'drained': True}
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
            engine.dispose()


def main(argv=None):
    parser = Parser(description=__doc__)
    for name in ('database', 'derived', 'temporary', 'stop-file', 'caption-url', 'environment-json', 'expected-revision'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--legacy-worker-stopped', action='store_true')
    parser.add_argument('--once', action='store_true')
    try:
        print(json.dumps(run(parser.parse_args(argv)), sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({'worker': 'refused-or-interrupted', 'clean_drain_confirmed': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
