"""Bounded worker for approved member-upload video preparation.

This worker deliberately owns only the media-safe part of the video chain:
``video_probe`` and ``video_keyframes``.  It never starts the mixed
``TaskExecutor`` and it leaves ``video_embed`` for the separately qualified
inference worker.  A task is eligible only after upload review has assigned it
to a library.  The default mode is a long-running poller; ``--once`` is useful
for a service canary and tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import stat
import subprocess
import tempfile
import time
from datetime import datetime, timezone


TASK_TYPES = ("video_probe", "video_keyframes")
MAX_DURATION_SECONDS = 24 * 60 * 60
MAX_KEYFRAMES = 32
MAX_FRAME_BYTES = 128 * 1024 * 1024
MAX_LOG_BYTES = 64 * 1024
MAX_SOURCE_BYTES = 16 * 1024**3
MAX_RETRIES = 3
SCHEMA_REVISION = "a8d4c2e6f901"
MAX_PAYLOAD_BYTES = 2048
ERROR_CODES = frozenset({
    "source_outside_media_roots", "source_not_regular", "source_size_changed",
    "source_changed", "source_hash_changed", "media_process_timeout",
    "media_process_log_budget", "media_process_failed", "keyframe_output_budget",
    "keyframe_count_budget", "keyframe_bytes_budget", "keyframe_output_invalid",
    "invalid_video_probe", "video_budget", "approved_video_changed",
    "approved_video_not_found", "invalid_task_payload", "asset_id_missing",
    "minimum_free_ram", "windows_job_object_required", "worker_internal_error",
})


class WorkerError(RuntimeError):
    pass


def _direct_existing(path: Path, *, directory: bool) -> Path:
    if not path.is_absolute() or '..' in path.parts or path.is_symlink():
        raise ValueError('direct_existing_path_required')
    resolved = path.resolve(strict=True)
    if resolved != path or (not path.is_dir() if directory else not path.is_file()):
        raise ValueError('direct_existing_path_required')
    return path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _safe_error(exc: BaseException) -> str:
    value = str(exc).strip()
    return value if value in ERROR_CODES else "worker_internal_error"


def _inside(path: Path, roots: tuple[Path, ...]) -> bool:
    try:
        resolved = path.resolve(strict=False)
        return any(resolved.is_relative_to(root.resolve(strict=False)) for root in roots)
    except OSError:
        return False


def verify_source(path: Path, expected_sha256: str, expected_bytes: int,
                  roots: tuple[Path, ...]) -> dict:
    if not _inside(path, roots):
        raise WorkerError("source_outside_media_roots")
    first = path.stat()
    if not path.is_file() or path.is_symlink() or first.st_size <= 0:
        raise WorkerError("source_not_regular")
    if first.st_size > MAX_SOURCE_BYTES or first.st_size != int(expected_bytes):
        raise WorkerError("source_size_changed")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    second = path.stat()
    if ((first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns, first.st_ctime_ns)
            != (second.st_dev, second.st_ino, second.st_size, second.st_mtime_ns, second.st_ctime_ns)):
        raise WorkerError("source_changed")
    if digest.hexdigest().lower() != str(expected_sha256).lower():
        raise WorkerError("source_hash_changed")
    return {"sha256": digest.hexdigest(), "bytes": second.st_size,
            "identity": (second.st_dev, second.st_ino, second.st_size,
                         second.st_mtime_ns, second.st_ctime_ns)}


def run_command(args: list[str], *, timeout: int, log_bytes: int = MAX_LOG_BYTES,
                output_dir: Path | None = None, free_ram_check=None) -> tuple[str, str]:
    """Run ff* without shell, with timeout, bounded output and process cleanup."""
    out_file = tempfile.TemporaryFile()
    err_file = tempfile.TemporaryFile()
    proc = subprocess.Popen(
        args, stdin=subprocess.DEVNULL, stdout=out_file, stderr=err_file,
        start_new_session=(os.name != "nt"),
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
    )
    try:
        started = time.monotonic()
        while proc.poll() is None:
            if time.monotonic() - started > timeout:
                raise WorkerError("media_process_timeout")
            if out_file.tell() > log_bytes or err_file.tell() > log_bytes:
                raise WorkerError("media_process_log_budget")
            if output_dir is not None:
                files = [p for p in output_dir.iterdir() if p.is_file() and not p.is_symlink()]
                if len(files) > MAX_KEYFRAMES or sum(p.stat().st_size for p in files) > MAX_FRAME_BYTES:
                    raise WorkerError("keyframe_output_budget")
            if free_ram_check is not None:
                free_ram_check()
            time.sleep(0.05)
        proc.wait()
        if out_file.tell() > log_bytes or err_file.tell() > log_bytes:
            raise WorkerError("media_process_log_budget")
        if proc.returncode:
            raise WorkerError("media_process_failed")
        out_file.seek(0); err_file.seek(0)
        return out_file.read().decode("utf-8", "replace"), err_file.read().decode("utf-8", "replace")
    except BaseException:
        if proc.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=False)
            else:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except OSError: proc.kill()
            proc.wait()
        raise
    finally:
        out_file.close(); err_file.close()


class ApprovedVideoWorker:
    def __init__(self, database: Path, derived_root: Path, media_roots: tuple[Path, ...],
                 *, ffprobe: str = "ffprobe", ffmpeg: str = "ffmpeg",
                 poll_seconds: float = 2.0, once: bool = False,
                 max_retries: int = MAX_RETRIES):
        self.database = _direct_existing(database, directory=False)
        self.derived_root = _direct_existing(derived_root, directory=True)
        self.media_roots = tuple(_direct_existing(p, directory=True) for p in media_roots)
        if not self.media_roots:
            raise ValueError("media_root_must_be_direct_directory")
        self.ffprobe = ffprobe
        self.ffmpeg = ffmpeg
        self.poll_seconds = max(0.1, float(poll_seconds))
        self.once = once
        self.max_retries = max(1, int(max_retries))
        self.stop = False
        self._lock_handle = None
        self._require_schema()
        self.ffprobe = self._direct_executable(self.ffprobe)
        self.ffmpeg = self._direct_executable(self.ffmpeg)

    @staticmethod
    def _direct_executable(value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            found = shutil.which(value)
            if not found: raise ValueError("media_executable_missing")
            path = Path(found)
        if path.is_symlink() or not path.is_file(): raise ValueError("media_executable_not_direct")
        return str(path.resolve())

    def _require_schema(self):
        db = self._connect()
        try:
            row = db.execute("SELECT version_num FROM alembic_version").fetchall()
            if [r[0] for r in row] != [SCHEMA_REVISION]:
                raise ValueError("schema_revision_mismatch")
        except sqlite3.Error as exc:
            raise ValueError("schema_revision_missing") from exc
        finally: db.close()

    def _lock(self):
        lock = self.derived_root / ".approved-video-worker.lock"
        flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        self._lock_handle = os.fdopen(os.open(lock, flags, 0o600), 'r+b', buffering=0)
        try:
            opened = os.fstat(self._lock_handle.fileno())
            target = lock.lstat()
            if (not stat.S_ISREG(opened.st_mode) or stat.S_ISLNK(target.st_mode)
                    or (opened.st_dev, opened.st_ino) != (target.st_dev, target.st_ino)):
                raise WorkerError("worker_already_running")
            if os.name == 'nt':
                import msvcrt
                self._lock_handle.seek(0)
                msvcrt.locking(self._lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, WorkerError) as exc:
            self._lock_handle.close(); self._lock_handle = None
            raise WorkerError("worker_already_running") from exc

    def _unlock(self):
        if self._lock_handle is not None:
            if os.name == 'nt':
                import msvcrt
                self._lock_handle.seek(0)
                msvcrt.locking(self._lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock_handle, fcntl.LOCK_UN)
            self._lock_handle.close(); self._lock_handle = None

    @staticmethod
    def _ram_check():
        from home_preparation_resources import memory
        if memory()[0] < 8192 * 1024**2:
            raise WorkerError("minimum_free_ram")

    def _resource_guard(self):
        if os.name != "nt":
            raise WorkerError("windows_job_object_required")
        from home_memory_envelope import WindowsJob
        self._ram_check()
        return WindowsJob(2048)

    def _connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def claim(self):
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                """SELECT * FROM tasks WHERE state='pending' AND cancel_requested=0
                   AND type IN ('video_probe','video_keyframes')
                   AND (scheduled_at IS NULL OR scheduled_at <= datetime('now'))
                   ORDER BY priority,id"""
            ).fetchall()
            for row in rows:
                raw = row["payload_json"] or ""
                if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
                    continue
                try: payload = json.loads(raw)
                except (TypeError, ValueError): continue
                if (not isinstance(payload, dict) or set(payload) != {"asset_id"}
                        or type(payload["asset_id"]) is not int or payload["asset_id"] <= 0):
                    continue
                approved = db.execute(
                    """SELECT a.* FROM assets a JOIN access_uploads u ON u.asset_id=a.id
                       JOIN access_asset_libraries al ON al.asset_id=a.id
                       JOIN access_libraries l ON l.id=al.library_id AND l.state='active'
                       WHERE a.id=? AND u.state='assigned' AND a.status='active'
                         AND lower(coalesce(a.mime,'')) LIKE 'video/%'""", (payload["asset_id"],)
                ).fetchone()
                if approved is not None:
                    provenance = db.execute(
                        "SELECT sha256,bytes FROM access_uploads WHERE asset_id=? AND state='assigned'",
                        (payload["asset_id"],),
                    ).fetchone()
                    mapped = db.execute(
                        "SELECT count(*) FROM access_asset_libraries WHERE asset_id=?",
                        (payload["asset_id"],),
                    ).fetchone()[0]
                    if (provenance is None or provenance[0] != approved["hash_sha256"]
                            or int(provenance[1] or -1) != int(approved["file_size"] or -2)
                            or mapped != 1):
                        approved = None
                if approved is None: continue
                changed = db.execute(
                    "UPDATE tasks SET state='running',started_at=?,updated_at=? WHERE id=? AND state='pending' AND cancel_requested=0",
                    (_now(), _now(), row["id"]),
                ).rowcount
                if changed == 1:
                    db.commit(); return dict(row)
            db.commit()
            return None
        finally:
            db.close()

    @staticmethod
    def _payload(task) -> dict:
        try:
            payload = json.loads(task["payload_json"] or "{}")
        except (TypeError, ValueError):
            raise WorkerError("invalid_task_payload")
        if (not isinstance(payload, dict) or set(payload) != {"asset_id"}
                or type(payload.get("asset_id")) is not int or payload["asset_id"] <= 0):
            raise WorkerError("asset_id_missing")
        return payload

    def _asset(self, asset_id: int):
        db = self._connect()
        try:
            row = db.execute(
                """SELECT a.id,a.path,a.hash_sha256,a.file_size,a.mime,a.duration_sec,
                          a.width,a.height,a.fps
                   FROM assets a JOIN access_uploads u ON u.asset_id=a.id
                   JOIN access_asset_libraries al ON al.asset_id=a.id
                   JOIN access_libraries l ON l.id=al.library_id AND l.state='active'
                   WHERE a.id=? AND u.state='assigned' AND a.status='active'
                     AND lower(coalesce(a.mime,'')) LIKE 'video/%'
                     AND u.sha256=a.hash_sha256 AND u.bytes=a.file_size
                     AND (SELECT count(*) FROM access_asset_libraries ax WHERE ax.asset_id=a.id)=1""", (asset_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            db.close()

    def _publish_guard(self, task_id: int, asset_id: int, expected, callback):
        """Hash before the SQLite write lock; keep publication and enqueue atomic."""
        source = Path(expected["path"])
        fingerprint = verify_source(source, expected["hash_sha256"], expected["file_size"], self.media_roots)
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            task = db.execute("SELECT state,cancel_requested FROM tasks WHERE id=?", (task_id,)).fetchone()
            asset = db.execute(
                """SELECT a.* FROM assets a JOIN access_uploads u ON u.asset_id=a.id
                   JOIN access_asset_libraries al ON al.asset_id=a.id
                   JOIN access_libraries l ON l.id=al.library_id AND l.state='active'
                   WHERE a.id=? AND u.state='assigned' AND a.status='active'
                     AND lower(coalesce(a.mime,'')) LIKE 'video/%'
                     AND u.sha256=a.hash_sha256 AND u.bytes=a.file_size
                     AND (SELECT count(*) FROM access_asset_libraries ax WHERE ax.asset_id=a.id)=1""", (asset_id,)
            ).fetchone()
            if (task is None or task["state"] != "running" or task["cancel_requested"]
                    or asset is None or asset["hash_sha256"] != expected["hash_sha256"]
                    or int(asset["file_size"] or -1) != int(expected["file_size"] or -2)
                    or asset["path"] != expected["path"]):
                raise WorkerError("approved_video_changed")
            current = source.stat(follow_symlinks=False)
            if (source.is_symlink() or
                    (current.st_dev, current.st_ino, current.st_size,
                     current.st_mtime_ns, current.st_ctime_ns) != fingerprint["identity"]):
                raise WorkerError("source_changed")
            callback(db, asset)
            changed = db.execute(
                """UPDATE tasks SET state='finished',finished_at=?,updated_at=?,last_error=NULL
                   WHERE id=? AND state='running' AND cancel_requested=0""",
                (_now(), _now(), task_id),
            ).rowcount
            if changed != 1:
                raise WorkerError("approved_video_changed")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _fail(self, task_id: int, retry_count: int, exc: BaseException):
        db = self._connect()
        try:
            count = int(retry_count or 0) + 1
            state = "dead" if count >= self.max_retries else "pending"
            # A short deterministic backoff prevents a corrupt video from
            # consuming every poll while retaining a bounded retry history.
            delay = f"+{min(3600, 15 * (2 ** min(count - 1, 8)))} seconds"
            if state == "pending":
                db.execute("UPDATE tasks SET state=?,retry_count=?,last_error=?,scheduled_at=datetime('now', ?),updated_at=? WHERE id=? AND state='running'",
                           (state, count, _safe_error(exc), delay, _now(), task_id))
            else:
                db.execute("UPDATE tasks SET state=?,retry_count=?,last_error=?,finished_at=?,updated_at=? WHERE id=? AND state='running'",
                           (state, count, _safe_error(exc), _now(), _now(), task_id))
            db.commit()
        finally:
            db.close()

    def _probe(self, asset, asset_id: int, task_id: int):
        verify_source(Path(asset["path"]), asset["hash_sha256"], asset["file_size"], self.media_roots)
        out, _ = run_command([self.ffprobe, "-v", "error", "-protocol_whitelist", "file", "-print_format", "json",
                              "-show_streams", "-show_format", asset["path"]], timeout=30,
                              free_ram_check=self._ram_check)
        try:
            info = json.loads(out)
            streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
            fmt = info.get("format", {})
            stream = streams[0] if streams else None
            duration = float(stream.get("duration") or fmt.get("duration") or 0.0)
            width, height = int(stream["width"]), int(stream["height"])
            fps_text = str(stream.get("r_frame_rate") or "0/1")
            n, d = fps_text.split("/", 1)
            fps = float(n) / float(d)
        except (ValueError, KeyError, TypeError, ZeroDivisionError, IndexError):
            raise WorkerError("invalid_video_probe")
        if not (math.isfinite(duration) and 0 < duration <= MAX_DURATION_SECONDS
                and math.isfinite(fps) and 0 < fps <= 240
                and 0 < width <= 16384 and 0 < height <= 16384):
            raise WorkerError("video_budget")
        # Approval can be revoked while ffprobe is running. Re-read the join
        # before publishing metadata or releasing the next task.
        def publish(db, current):
            db.execute("UPDATE assets SET duration_sec=?,width=?,height=?,fps=? WHERE id=?",
                       (duration, width, height, fps, asset_id))
            exists = None
            for row in db.execute("SELECT type,payload_json,state FROM tasks WHERE type='video_keyframes' AND state NOT IN ('dead','failed')").fetchall():
                try:
                    if json.loads(row["payload_json"] or "{}").get("asset_id") == asset_id: exists = row; break
                except (TypeError, ValueError): pass
            if exists is None:
                db.execute("INSERT INTO tasks(type,payload_json,state,priority,retry_count,cancel_requested,scheduled_at,created_at) VALUES('video_keyframes',?,'pending',70,0,0,datetime('now'),datetime('now'))",
                           (json.dumps({'asset_id': asset_id}, sort_keys=True),))
        self._publish_guard(task_id=task_id, asset_id=asset_id, expected=asset, callback=publish)

    def _keyframes(self, asset, asset_id: int, task_id: int):
        verify_source(Path(asset["path"]), asset["hash_sha256"], asset["file_size"], self.media_roots)
        root = self.derived_root / "video_frames"
        root.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=f".{asset_id}-", dir=root))
        try:
            duration = float(asset.get("duration_sec") or 0.0)
            interval = max(0.5, duration / MAX_KEYFRAMES if duration else 2.0)
            run_command([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                         "-threads", "1", "-protocol_whitelist", "file", "-i", asset["path"],
                         "-map", "0:v:0", "-an", "-sn", "-dn",
                         "-vf", f"fps=1/{interval:.6f},scale=1024:1024:force_original_aspect_ratio=decrease",
                         "-frames:v", str(MAX_KEYFRAMES), str(temp / "frame_%05d.jpg")],
                        timeout=300, output_dir=temp, free_ram_check=self._ram_check)
            frames = sorted(p for p in temp.glob("frame_*.jpg") if p.is_file() and not p.is_symlink())
            if not frames or len(frames) > MAX_KEYFRAMES:
                raise WorkerError("keyframe_output_invalid")
            published = root / str(asset_id)
            old = root / f".{asset_id}.old"
            def publish(db, current):
                if old.exists(): shutil.rmtree(old)
                if published.exists(): os.replace(published, old)
                os.replace(temp, published)
                for task_type, priority in (("video_embed", 90), ("caption", 110)):
                    exists = None
                    for row in db.execute("SELECT payload_json,state FROM tasks WHERE type=? AND state NOT IN ('dead','failed')", (task_type,)).fetchall():
                        try:
                            if json.loads(row["payload_json"] or "{}").get("asset_id") == asset_id: exists = row; break
                        except (TypeError, ValueError): pass
                    if exists is None:
                        db.execute("INSERT INTO tasks(type,payload_json,state,priority,retry_count,cancel_requested,scheduled_at,created_at) VALUES(?,?,'pending',?,0,0,datetime('now'),datetime('now'))",
                                   (task_type, json.dumps({'asset_id': asset_id}, sort_keys=True), priority))
                if old.exists(): shutil.rmtree(old)
            self._publish_guard(task_id=task_id, asset_id=asset_id, expected=asset, callback=publish)
        except Exception:
            shutil.rmtree(temp, ignore_errors=True)
            raise

    def run_once(self) -> bool:
        task = self.claim()
        if task is None:
            return False
        try:
            payload = self._payload(task)
            asset_id = int(payload["asset_id"])
            asset = self._asset(asset_id)
            if asset is None:
                raise WorkerError("approved_video_not_found")
            if task["type"] == "video_probe": self._probe(asset, asset_id, task["id"])
            elif task["type"] == "video_keyframes": self._keyframes(asset, asset_id, task["id"])
            else: raise WorkerError("unsupported_task_type")
        except Exception as exc:
            self._fail(task["id"], task["retry_count"], exc)
        return True

    def run(self):
        self._lock()
        job = None
        try:
            job = self._resource_guard()
            while not self.stop:
                self._ram_check()
                worked = self.run_once()
                if self.once or not worked:
                    if self.once: return
                    time.sleep(self.poll_seconds)
                else:
                    time.sleep(0.05)
        finally:
            if job is not None: job.close()
            self._unlock()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--derived-root", type=Path, required=True)
    parser.add_argument("--media-root", type=Path, action="append", required=True)
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--max-retries", type=int, default=MAX_RETRIES)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    worker = ApprovedVideoWorker(args.database, args.derived_root, tuple(args.media_root),
                                 ffprobe=args.ffprobe, ffmpeg=args.ffmpeg,
                                 poll_seconds=args.poll_seconds, once=args.once,
                                 max_retries=args.max_retries)
    if not args.execute:
        print(json.dumps({"preflight": "pass", "schema_revision": SCHEMA_REVISION,
                          "activated": False}))
        return 0
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: setattr(worker, "stop", True))
    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
