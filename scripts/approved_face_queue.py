"""SQLite authorization and task-state helpers for approved face processing.

No media is opened here. ``select_candidate`` is read-only. ``claim`` owns a
short ``BEGIN IMMEDIATE`` transaction and commits/rolls back it itself.
``verify_claim`` is called inside the caller's existing ``BEGIN IMMEDIATE``
transaction and never commits. Failure and recovery helpers own and commit
their short transactions.

The schema has no worker-owner column. The exact sanitized marker
``approved_face_v38`` in ``tasks.last_error`` records ownership while a task is
running; it is replaced by a sanitized failure code on failure and cleared on
recovery/requeue.
"""
from __future__ import annotations

import json
import sqlite3

REVISION = "a8d4c2e6f901"
OWNER = "approved_face_v38"
MAX_RETRIES = 3
SUPPORTED_MIME = {"image/jpeg", "image/png"}
FAILURE_CODES = {"approval_scope", "unsupported_media", "source_changed", "worker_error"}


class QueueRefused(ValueError):
    pass


REQUIRED = {
    "alembic_version": {"version_num"},
    "tasks": {"id", "type", "payload_json", "state", "priority", "retry_count",
              "cancel_requested", "scheduled_at", "started_at", "finished_at", "last_error"},
    "assets": {"id", "path", "hash_sha256", "file_size", "mime", "status"},
    "access_uploads": {"asset_id", "state", "sha256", "bytes"},
    "access_asset_libraries": {"asset_id", "library_id"},
    "access_libraries": {"id", "state"},
    "face_detections": {"id", "asset_id"},
    "face_embedding_artifacts": {"id", "face_id", "model", "model_version", "dim",
                                  "alignment", "storage_path", "vector_checksum", "status"},
}


def validate_schema(db: sqlite3.Connection) -> None:
    versions = db.execute("SELECT version_num FROM alembic_version").fetchall()
    if len(versions) != 1 or versions[0][0] != REVISION:
        raise QueueRefused("unsupported_schema")
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not REQUIRED.keys() <= tables:
        raise QueueRefused("required_table_missing")
    for table, needed in REQUIRED.items():
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if not needed <= columns:
            raise QueueRefused("required_column_missing")


def _approval(db: sqlite3.Connection, asset_id: int):
    rows = db.execute("""SELECT a.id,a.path,a.hash_sha256,a.file_size,a.mime,a.status,
        u.state,u.sha256,u.bytes,
        (SELECT count(*) FROM access_asset_libraries m WHERE m.asset_id=a.id),
        m.library_id,l.state
        FROM assets a JOIN access_uploads u ON u.asset_id=a.id
        JOIN access_asset_libraries m ON m.asset_id=a.id
        JOIN access_libraries l ON l.id=m.library_id
        WHERE a.id=?""", (asset_id,)).fetchall()
    if len(rows) != 1:
        return None
    r = rows[0]
    if (r[5] != "active" or r[6] != "assigned" or r[11] != "active"
            or r[2] != r[7] or type(r[3]) is not int or r[3] != r[8]
            or r[9] != 1 or r[4] not in SUPPORTED_MIME):
        return None
    return {"asset_id": r[0], "path": r[1], "sha256": r[2], "bytes": r[3], "mime": r[4], "library_id": r[10]}


def _payload(raw, kind):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError):
        return None
    key = "asset_id" if kind == "face" else "face_id"
    if (type(value) is not dict or set(value) != {key}
            or type(value.get(key)) is not int or value[key] <= 0):
        return None
    return value


def _due_rows(db):
    return db.execute("""SELECT id,type,payload_json,retry_count,priority FROM tasks
        WHERE type IN ('face','face_embed') AND state='pending' AND cancel_requested=0
          AND (scheduled_at IS NULL OR scheduled_at<=CURRENT_TIMESTAMP)
        ORDER BY priority,id""").fetchall()


def select_candidate(db: sqlite3.Connection) -> dict | None:
    """Return the first due, exactly shaped, currently approved face task."""
    validate_schema(db)
    for task_id, kind, raw, retries, priority in _due_rows(db):
        payload = _payload(raw, kind)
        if payload is None:
            continue
        face_id = None
        if kind == "face":
            asset_id = payload["asset_id"]
        else:
            row = db.execute("SELECT asset_id FROM face_detections WHERE id=?", (payload["face_id"],)).fetchone()
            if not row:
                continue
            asset_id, face_id = row[0], payload["face_id"]
        approval = _approval(db, asset_id)
        if approval is None:
            continue
        return {"task_id": task_id, "kind": kind, "asset_id": asset_id,
                "face_id": face_id, "retries": retries, "priority": priority,
                "payload": payload, **approval}
    return None


def _same_scope(db, candidate):
    approval = _approval(db, candidate["asset_id"])
    if not approval:
        return False
    if any(approval.get(k) != candidate.get(k) for k in ("asset_id", "path", "sha256", "bytes", "mime", "library_id")):
        return False
    if candidate["kind"] == "face_embed":
        row = db.execute("SELECT asset_id FROM face_detections WHERE id=?", (candidate["face_id"],)).fetchone()
        if not row or row[0] != candidate["asset_id"]:
            return False
    return True


def claim(db: sqlite3.Connection, candidate: dict) -> bool:
    """Claim candidate; begins and commits its own immediate transaction."""
    if db.in_transaction:
        raise QueueRefused("claim_requires_idle_connection")
    try:
        db.execute("BEGIN IMMEDIATE")
        if not _same_scope(db, candidate):
            db.rollback(); return False
        row = db.execute("SELECT type,payload_json,retry_count FROM tasks WHERE id=? AND state='pending' AND cancel_requested=0 AND (scheduled_at IS NULL OR scheduled_at<=CURRENT_TIMESTAMP)", (candidate["task_id"],)).fetchone()
        if not row or row[0] != candidate["kind"] or row[2] != candidate["retries"]:
            db.rollback(); return False
        if _payload(row[1], row[0]) != candidate["payload"]:
            db.rollback(); return False
        changed = db.execute("""UPDATE tasks SET state='running',started_at=CURRENT_TIMESTAMP,
            finished_at=NULL,last_error=? WHERE id=? AND state='pending' AND cancel_requested=0""",
            (OWNER, candidate["task_id"])).rowcount
        if changed != 1:
            db.rollback(); return False
        db.commit(); return True
    except Exception:
        db.rollback()
        raise


def verify_claim(db: sqlite3.Connection, candidate: dict) -> bool:
    """Recheck claim ownership and all approval/source metadata in caller's write txn."""
    if not db.in_transaction:
        raise QueueRefused("verify_requires_transaction")
    row = db.execute("SELECT type,payload_json,state,cancel_requested,last_error,retry_count FROM tasks WHERE id=?",
                     (candidate["task_id"],)).fetchone()
    if (not row or row[0] != candidate["kind"] or row[2] != "running" or row[3] != 0
            or row[4] != OWNER or row[5] != candidate["retries"]
            or _payload(row[1], row[0]) != candidate["payload"]):
        return False
    return _same_scope(db, candidate)


def record_failure(db: sqlite3.Connection, candidate: dict, code: str) -> bool:
    """Record bounded failure only for a task still running under this owner."""
    error = code if code in FAILURE_CODES else "worker_error"
    if db.in_transaction:
        raise QueueRefused("failure_requires_idle_connection")
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT retry_count FROM tasks WHERE id=? AND state='running' AND last_error=?",
                         (candidate["task_id"], OWNER)).fetchone()
        if not row:
            db.rollback(); return False
        retries = min(int(row[0]) + 1, MAX_RETRIES)
        state = ("dead" if retries >= MAX_RETRIES else
                 "failed" if error in {"approval_scope", "unsupported_media", "source_changed"}
                 else "pending")
        changed = db.execute("""UPDATE tasks SET state=?,retry_count=?,last_error=?,
            started_at=NULL,finished_at=CASE WHEN ?='pending' THEN NULL ELSE CURRENT_TIMESTAMP END,
            scheduled_at=CASE WHEN ?='pending' THEN datetime('now','+60 seconds') ELSE scheduled_at END
            WHERE id=? AND state='running' AND last_error=?""",
            (state, retries, error, state, state, candidate["task_id"], OWNER)).rowcount
        db.commit(); return changed == 1
    except Exception:
        db.rollback(); raise


def recover_owned(db: sqlite3.Connection) -> int:
    """Requeue owned abandoned running tasks, exhausting only their bounded retries."""
    if db.in_transaction:
        raise QueueRefused("recovery_requires_idle_connection")
    try:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute("SELECT id,retry_count FROM tasks WHERE state='running' AND last_error=?", (OWNER,)).fetchall()
        count = 0
        for task_id, prior in rows:
            retries = min(int(prior) + 1, MAX_RETRIES)
            state = "dead" if retries >= MAX_RETRIES else "pending"
            count += db.execute("""UPDATE tasks SET state=?,retry_count=?,started_at=NULL,
                finished_at=CASE WHEN ?='dead' THEN CURRENT_TIMESTAMP ELSE NULL END,
                last_error=CASE WHEN ?='dead' THEN 'worker_error' ELSE NULL END
                WHERE id=? AND state='running' AND last_error=?""",
                (state, retries, state, state, task_id, OWNER)).rowcount
        db.commit(); return count
    except Exception:
        db.rollback(); raise
