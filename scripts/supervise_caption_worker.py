#!/usr/bin/env python3
"""One-process caption supervisor. Default: pinned, read-only preflight.

No HTTP/API dependency, service control, child restart, schema repair or migration.
Run with a qualified worker interpreter and -I -B in a dedicated process.
"""
import argparse
from contextlib import closing, contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from types import ModuleType
import uuid


FILES = frozenset([
    *('backend/app/'+name+'.py' for name in ('__init__', 'config', 'db', 'tasks',
        'vector_index', 'image_utils', 'face_assignment_audit', 'metrics',
        'gps_utils', 'caption_policy', 'caption_service', 'tagging')),
    'config/detailed-caption-prompt.txt', 'scripts/run_caption_worker.py',
    'docs/security/CAPTION_WORKER.md',
])
FIELDS = frozenset(('format_version', 'worker_root', 'worker_commit',
    'manifest_sha256', 'database', 'expected_revision', 'derived', 'temporary',
    'stop_file', 'caption_url', 'environment_json', 'environment_sha256',
    'receipt_directory'))
OPTIONAL_FIELDS = frozenset(('defer_non_caption_pending',))


class Refused(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('Invalid arguments')


def direct(value, *, directory=False, new=False):
    if type(value) is not str or not value or '\x00' in value:
        raise Refused('Explicit path required')
    path = Path(value)
    if (not path.is_absolute() or '..' in path.parts
            or path.anchor.startswith(('//', '\\\\'))
            or path.parent.resolve(strict=True) != path.parent):
        raise Refused('Direct local path required')
    if new and not os.path.lexists(path):
        return path
    if (path.resolve(strict=True) != path
            or not (path.is_dir() if directory else path.is_file())
            or (not directory and path.stat().st_nlink != 1)):
        raise Refused('Unexpected path type or alias')
    return path


def read_bytes(path, limit):
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    if len(raw) > limit:
        raise Refused('Input too large')
    return raw


def digest(raw, expected):
    if (type(expected) is not str or not re.fullmatch('[0-9a-f]{64}', expected)
            or hashlib.sha256(raw).hexdigest() != expected):
        raise Refused('Hash mismatch')


def json_object(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise Refused('Duplicate key')
            out[key] = value
        return out
    obj = json.loads(raw, object_pairs_hook=unique,
                     parse_constant=lambda _: (_ for _ in ()).throw(Refused('Nonfinite value')))
    if type(obj) is not dict:
        raise Refused('Object required')
    return obj


def verified_worker(config):
    root = direct(config['worker_root'], directory=True)
    raw = read_bytes(direct(str(root/'manifest.json')), 65536)
    digest(raw, config['manifest_sha256'])
    manifest = json_object(raw)
    expected = {'format_version': 1, 'source_commit': config['worker_commit'],
        'artifact_kind': 'caption_worker_source_only', 'activated': False,
        'dependencies_included': False, 'private_configuration_included': False,
        'http_listener_included': False}
    if (set(manifest) != set(expected)|{'files'}
            or any(type(manifest[k]) is not type(v) or manifest[k] != v for k, v in expected.items())
            or type(manifest['files']) is not dict or set(manifest['files']) != FILES):
        raise Refused('Unexpected worker manifest')
    # No unmanifested Python, bytecode, .env or reparse paths in the release.
    actual = set()
    for path in root.rglob('*'):
        direct(str(path), directory=path.is_dir())
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != FILES|{'manifest.json'}:
        raise Refused('Unexpected worker files')
    sources = {}
    for name in sorted(FILES):
        raw = read_bytes(direct(str(root/name)), 512000)
        digest(raw, manifest['files'][name])
        sources[name] = raw
    if sum(map(len, sources.values())) > 2000000:
        raise Refused('Worker source budget exceeded')
    module = ModuleType('verified_caption_runner')
    module.__file__ = str(root/'scripts/run_caption_worker.py')
    exec(compile(sources['scripts/run_caption_worker.py'], module.__file__, 'exec'), module.__dict__)
    return module


def prepare(config_path, config_sha256):
    path = direct(config_path)
    raw = read_bytes(path, 65536)
    digest(raw, config_sha256)
    config = json_object(raw)
    if (set(config) not in (FIELDS, FIELDS | OPTIONAL_FIELDS)
            or (config.get('defer_non_caption_pending', False) is not False
                and config.get('defer_non_caption_pending') is not True)
            or type(config['format_version']) is not int
            or config['format_version'] != 1
            or any(type(config[k]) is not str for k in FIELDS-{'format_version'})
            or not re.fullmatch('[0-9a-f]{40}', config['worker_commit'])):
        raise Refused('Unexpected configuration')
    if any(name == 'app' or name.startswith('app.') for name in sys.modules):
        raise Refused('Dedicated process required')
    root = direct(config['worker_root'], directory=True)
    database = direct(config['database'])
    environment = direct(config['environment_json'])
    directories = [direct(config[k], directory=True) for k in
                   ('derived', 'temporary', 'receipt_directory')]
    # Receipts and stop requests must never be written into source/media/temp.
    receipts = directories[-1]
    for a in (root, *directories[:-1]):
        if receipts == a or receipts in a.parents or a in receipts.parents:
            raise Refused('Receipt storage overlaps runtime storage')
    stop = direct(config['stop_file'], new=True)
    if (os.path.lexists(stop) or stop in (database, path, environment,
            Path(str(database)+'.caption-worker.lock'))
            or any(stop == a or a in stop.parents for a in (root, *directories[:-1]))):
        raise Refused('Stop request present or unsafe')
    if any(p == root or root in p.parents for p in (path, database, environment)):
        raise Refused('Runtime inputs must be outside source')
    digest(read_bytes(environment, 65536), config['environment_sha256'])
    worker = verified_worker(config)
    args = argparse.Namespace(database=str(database), derived=config['derived'],
        temporary=config['temporary'], stop_file=str(stop), caption_url=config['caption_url'],
        environment_json=str(environment), expected_revision=config['expected_revision'],
        execute=False, legacy_worker_stopped=False, once=False)
    worker.run(args)  # read-only: exact revision, policy, paths, no running caption
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True, timeout=3)) as db:
        db.execute('PRAGMA query_only=ON')
        if db.execute("SELECT 1 FROM tasks WHERE state='running' AND type!='caption' LIMIT 1").fetchone():
            raise Refused('Other task families require an independent owner')
        other_pending = db.execute("SELECT count(*) FROM tasks WHERE state='pending' AND type!='caption'").fetchone()[0]
        if other_pending and not config.get('defer_non_caption_pending', False):
            raise Refused('Other task families require an independent owner')
        config['_deferred_other_pending_count'] = other_pending
    return config, worker, args


def receipt(directory, run_id, phase, values):
    record = {'format_version': 1, 'run_id': run_id, 'phase': phase,
              'utc': datetime.now(timezone.utc).isoformat(), **values}
    raw = (json.dumps(record, sort_keys=True)+'\n').encode('utf-8')
    if len(raw) > 2048:
        raise Refused('Receipt too large')
    path = direct(str(directory/(run_id+'.'+phase+'.json')), new=True)
    flags = os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os, 'O_BINARY', 0)|getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path, flags, 0o600), 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


@contextmanager
def private_output():
    """Discard raw model/media diagnostics; never accumulate pipe output in RAM."""
    with open(os.devnull, 'w', encoding='utf-8') as sink:
        saved = []
        try:
            for fd in (1, 2):
                saved.append((fd, os.dup(fd)))
                os.dup2(sink.fileno(), fd)
            with redirect_stdout(sink), redirect_stderr(sink):
                yield
        finally:
            for fd, original in saved:
                os.dup2(original, fd); os.close(original)


def supervise(args):
    sys.dont_write_bytecode = True
    config, worker, worker_args = prepare(args.config, args.config_sha256)
    if not args.execute:
        result = {'supervisor': 'preflight-pass', 'activated': False,
                  'revision': config['expected_revision']}
        if config.get('defer_non_caption_pending', False):
            result['deferred_other_pending_count'] = config['_deferred_other_pending_count']
        return result
    if not args.writers_fenced:
        raise Refused('Independent writer fencing confirmation required')
    # This assertion is authorization context, not detection of legacy writers.
    # Verify immutable inputs again immediately before handing off in this process.
    config, worker, worker_args = prepare(args.config, args.config_sha256)
    worker_args.execute = True
    worker_args.legacy_worker_stopped = True
    worker_args.once = args.once
    directory = Path(config['receipt_directory'])
    run_id = uuid.uuid4().hex
    receipt(directory, run_id, 'started', {'source_commit': config['worker_commit'],
        'revision': config['expected_revision'], 'pid': os.getpid(),
        'clean_drain_confirmed': False,
        'deferred_other_pending_count': config['_deferred_other_pending_count']})
    try:
        with private_output():
            result = worker.run(worker_args)
        if (type(result) is not dict or result.get('drained') is not True
                or result.get('worker') != 'stopped'
                or type(result.get('claimed_tasks_processed')) is not int
                or result['claimed_tasks_processed'] < 0):
            raise Refused('Unconfirmed worker outcome')
        outcome = {'supervisor': 'stopped', 'clean_drain_confirmed': True,
                   'claimed_tasks_processed': result['claimed_tasks_processed']}
    except (Exception, KeyboardInterrupt, SystemExit):
        outcome = {'supervisor': 'refused-or-interrupted', 'clean_drain_confirmed': False}
    # A missing/incomplete result receipt never establishes a clean drain.
    receipt(directory, run_id, 'result', outcome)
    return outcome


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--config-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--writers-fenced', action='store_true')
    parser.add_argument('--once', action='store_true')
    try:
        result = supervise(parser.parse_args(argv))
        print(json.dumps(result, sort_keys=True))
        return 2 if result.get('clean_drain_confirmed') is False else 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({'supervisor': 'refused-or-interrupted',
                          'clean_drain_confirmed': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
