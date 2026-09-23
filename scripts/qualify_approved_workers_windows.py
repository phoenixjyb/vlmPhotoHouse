#!/usr/bin/env python3
"""Synthetic native canary for approved-upload CPU and video preparation lanes.

Creates a disposable database, image, and generated video under the OS temp
directory. Never opens the production database or family originals. This is a
qualification check, not a scheduled or live processing launcher.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


SCHEMA = '''
CREATE TABLE alembic_version(version_num TEXT NOT NULL);
INSERT INTO alembic_version VALUES ('a8d4c2e6f901');
CREATE TABLE assets(id INTEGER PRIMARY KEY,path TEXT,hash_sha256 TEXT,file_size INTEGER,
  mime TEXT,status TEXT,perceptual_hash TEXT,duration_sec REAL,width INTEGER,height INTEGER,fps REAL);
CREATE TABLE access_uploads(asset_id INTEGER,state TEXT,sha256 TEXT,bytes INTEGER);
CREATE TABLE access_asset_libraries(asset_id INTEGER,library_id TEXT);
CREATE TABLE access_libraries(id TEXT,state TEXT);
CREATE TABLE tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,type TEXT,payload_json TEXT,state TEXT,
  priority INTEGER,retry_count INTEGER,cancel_requested INTEGER,scheduled_at TEXT,
  started_at TEXT,finished_at TEXT,updated_at TEXT,last_error TEXT,created_at TEXT);
INSERT INTO access_libraries VALUES ('family','active');
'''


def _insert_asset(db, path: Path, asset_id: int, mime: str) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    size = path.stat().st_size
    db.execute('INSERT INTO assets(id,path,hash_sha256,file_size,mime,status) VALUES(?,?,?,?,?,?)',
               (asset_id, str(path), digest, size, mime, 'active'))
    db.execute("INSERT INTO access_uploads VALUES(?,'assigned',?,?)", (asset_id, digest, size))
    db.execute("INSERT INTO access_asset_libraries VALUES(?,'family')", (asset_id,))


def _task(db, kind: str, asset_id: int, priority: int) -> None:
    db.execute("""INSERT INTO tasks(type,payload_json,state,priority,retry_count,
      cancel_requested,scheduled_at,created_at) VALUES(?,?,'pending',?,0,0,
      datetime('now'),datetime('now'))""",
      (kind, json.dumps({'asset_id': asset_id}, sort_keys=True), priority))


def _worker_once(script: str, arguments: list[str], timeout: int) -> None:
    result = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'scripts' / script),
                             *arguments, '--execute', '--once'],
                            timeout=timeout, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode != 0:
        raise RuntimeError(f'{script}:exit_{result.returncode}')


def _require_finished(database: Path, kind: str) -> None:
    with closing(sqlite3.connect(database)) as db:
        row = db.execute('SELECT state,last_error FROM tasks WHERE type=?', (kind,)).fetchone()
    if row is None or row[0] != 'finished':
        error = (row[1] if row is not None else None) or 'no_error_code'
        if not isinstance(error, str) or not error.replace('_', '').isalnum() or len(error) > 64:
            error = 'unrecognized_error_code'
        raise RuntimeError(f'{kind}:state_{row[0] if row else "missing"}:{error}')


def run(ffmpeg: Path, ffprobe: Path) -> dict:
    if sys.platform != 'win32':
        raise RuntimeError('Windows native qualification required')
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise RuntimeError('Explicit native ffmpeg and ffprobe required')
    with tempfile.TemporaryDirectory(prefix='photohouse-approved-v37-canary-') as name:
        base = Path(name).resolve(strict=True)
        originals = base / 'originals'; originals.mkdir()
        derived = base / 'derived'; derived.mkdir()
        database = base / 'metadata.sqlite'
        image = originals / 'synthetic.png'
        Image.new('RGB', (96, 64), (30, 120, 170)).save(image)
        movie = originals / 'synthetic.mp4'
        try:
            subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                            '-f', 'lavfi', '-i', 'testsrc2=size=128x72:rate=5', '-t', '2',
                            '-c:v', 'mpeg4', '-q:v', '5', str(movie)],
                           check=True, timeout=30, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError('synthetic_video_generation_failed') from exc
        with closing(sqlite3.connect(database)) as db:
            db.executescript(SCHEMA)
            _insert_asset(db, image, 1, 'image/png')
            _insert_asset(db, movie, 2, 'video/mp4')
            _task(db, 'thumb', 1, 60)
            _task(db, 'phash', 1, 80)
            _task(db, 'video_probe', 2, 40)
            db.commit()
        cpu_args = ['--database', str(database), '--originals-root', str(originals),
            '--derived-root', str(derived), '--stop-file', str(base / 'cpu.stop')]
        for kind in ('thumb', 'phash'):
            _worker_once('run_approved_cpu_worker.py', cpu_args, 120)
            _require_finished(database, kind)
        video_args = ['--database', str(database), '--derived-root', str(derived),
            '--media-root', str(originals), '--ffprobe', str(ffprobe), '--ffmpeg', str(ffmpeg)]
        for kind in ('video_probe', 'video_keyframes'):
            _worker_once('run_approved_video_worker.py', video_args, 400)
            _require_finished(database, kind)
        with closing(sqlite3.connect(database)) as db:
            statuses = dict(db.execute("SELECT type,state FROM tasks WHERE type IN ('thumb','phash','video_probe','video_keyframes')"))
            perceptual_hash = db.execute('SELECT perceptual_hash FROM assets WHERE id=1').fetchone()[0]
            chained = set(db.execute("SELECT type FROM tasks WHERE type IN ('caption','video_embed')"))
        if (statuses != {kind: 'finished' for kind in ('thumb','phash','video_probe','video_keyframes')}
                or not perceptual_hash or chained != {('caption',), ('video_embed',)}
                or not (derived / 'thumbnails' / '256' / '1.jpg').is_file()
                or not any((derived / 'video_frames' / '2').glob('frame_*.jpg'))):
            raise RuntimeError('Synthetic derivative or queue verification failed')
        return {'native_canary': 'pass', 'schema_revision': 'a8d4c2e6f901',
                'completed': sorted(statuses), 'chained': sorted(kind for kind, in chained),
                'production_database_opened': False, 'family_media_opened': False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', type=Path, required=True)
    parser.add_argument('--ffprobe', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args.ffmpeg, args.ffprobe), sort_keys=True))
        return 0
    except RuntimeError as exc:
        print(json.dumps({'native_canary': 'failed', 'stage': str(exc)}), file=sys.stderr)
        return 2
    except Exception:
        print(json.dumps({'native_canary': 'failed', 'stage': 'unexpected_exception'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
