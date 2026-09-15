#!/usr/bin/env python3
"""Run one sealed, already-authenticated face assignment task.

The default operation is a read-only argument/database preflight.  This is a
deliberately separate process: it does not discover configuration, listen on
HTTP, load models, or select another queue item.
"""
import argparse
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'd8e5b2f7a904'
KINDS = ('person_cluster', 'person_recluster', 'person_label_propagate')


class Refused(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused("Invalid face-worker arguments")


def direct_path(value, *, directory=False, new=False):
    path = Path(value)
    if (not path.is_absolute() or path == Path(path.anchor) or ".." in path.parts or path.anchor.startswith(("//", "\\\\"))
            or len(str(value)) > 4096 or any(ord(c) < 32 for c in str(value))
            or path.parent.resolve(strict=True) != path.parent):
        raise Refused("Explicit direct local path required")
    if new and not os.path.lexists(path):
        return path
    if path.resolve(strict=True) != path or not (path.is_dir() if directory else path.is_file()):
        raise Refused("Unexpected path type")
    return path


def identity(path):
    st = path.lstat()
    return st.st_dev, st.st_ino


@contextmanager
def kernel_lock(database):
    path = direct_path(str(database) + ".face-worker.lock", new=True)
    flags = (os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(os.open(path, flags, 0o600), "r+b", buffering=0) as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != identity(path):
            raise Refused('Lock target changed')
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise Refused("Another face worker owns this database") from None
            try:
                yield
            finally:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise Refused("Another face worker owns this database") from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def preflight(database, root, task_id, plan_id, digest, stop_file):
    direct_path(database); direct_path(root, directory=True); direct_path(stop_file, new=True)
    if not re.fullmatch(r"[1-9][0-9]{0,18}", task_id) or int(task_id) > 2**63 - 1:
        raise Refused("Explicit task required")
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or str(uuid.UUID(plan_id)) != plan_id:
        raise Refused("Explicit sealed plan required")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('BEGIN')
        if db.execute('SELECT version_num FROM alembic_version').fetchall() != [(REVISION,)]:
            raise Refused('Migrated database required')
        task = db.execute('SELECT type,state,cancel_requested,scheduled_at FROM tasks WHERE id=?', (int(task_id),)).fetchone()
        if not task or task[0] not in KINDS or task[1:] != ('pending', 0, None):
            raise Refused("Exact pending assignment task required")
        if not db.execute('SELECT 1 FROM access_provisioning_receipts WHERE plan_id=? AND plan_digest=?',
                          (plan_id, digest)).fetchone():
            raise Refused('Exact receipt required')
    return {"preflight": "pass", "task_id": int(task_id), "activated": False,
            'cohort_revalidation_required': True}


def run(args, *, clock=time.time):
    database = direct_path(args.database)
    root = direct_path(args.embedding_root, directory=True)
    stop_file = direct_path(args.stop_file, new=True)
    before = identity(database)
    root_before = identity(root)
    result = preflight(database, root, args.task_id, args.plan_id, args.reviewed_plan_digest, stop_file)
    if not args.execute:
        return result
    if not args.legacy_worker_stopped or os.path.lexists(stop_file):
        raise Refused("Independent worker shutdown or stop request required")
    with kernel_lock(database):
        if (os.path.lexists(stop_file) or identity(database) != before
                or identity(root) != root_before):
            raise Refused("Face-worker target changed")
        sys.path.insert(0, str(ROOT / "backend"))
        if any(name in sys.modules for name in ('app.tasks','app.config','app.dependencies','app.main',
                                                'torch','transformers','onnxruntime','insightface')):
            raise Refused('Fresh isolated CPU worker process required')
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session
        from app.db import Task
        from app.access.face_jobs import verify_queued
        from app.access.provisioning import _PlanState
        from app.scoped_face_worker import run_scoped_assignment

        def connect():
            db = sqlite3.connect(database.as_uri() + '?mode=rw', uri=True, timeout=3)
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            return db
        engine = create_engine('sqlite://', creator=connect)
        try:
            with Session(engine, expire_on_commit=False) as session:
                # Establish the SQLAlchemy connection first: its initial dialect
                # setup may roll back. All validation and effects follow below.
                connection = session.connection()
                raw = connection.connection.driver_connection
                state = _PlanState(raw, clock=clock)
                connection.exec_driver_sql('BEGIN IMMEDIATE')
                if (identity(database) != before or identity(root) != root_before
                        or os.path.lexists(stop_file)):
                    raise Refused('Worker target or stop request changed')
                if raw.execute('SELECT version_num FROM alembic_version').fetchall() != [(REVISION,)]:
                    raise Refused('Migrated database required')
                envelope = verify_queued(state, plan_id=args.plan_id, digest=args.reviewed_plan_digest,
                              task_id=int(args.task_id), database_identity=before)
                claim_result = session.execute(text("UPDATE tasks SET state='running',started_at=CURRENT_TIMESTAMP WHERE id=:id AND state='pending'"), {"id": int(args.task_id)})
                if claim_result.rowcount != 1:
                    raise Refused("Exact pending task required")
                task = session.get(Task, int(args.task_id))
                assignment = run_scoped_assignment(session, task, embedding_root=root, clock=clock, commit=False)
                completed = session.execute(text("UPDATE tasks SET state='finished',finished_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=:id AND state='running'"), {"id": int(args.task_id)})
                if (completed.rowcount != 1 or identity(database) != before or identity(root) != root_before
                        or not envelope['plan']['created_at'] <= int(clock()) < envelope['plan']['expires_at']):
                    raise Refused('Worker completion review changed')
                session.commit()
            return {"worker": "stopped", "task_id": int(args.task_id), "completed": True,
                    'assigned': assignment['assigned']}
        finally:
            engine.dispose()


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--embedding-root", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--reviewed-plan-digest", required=True)
    parser.add_argument("--stop-file", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--legacy-worker-stopped", action="store_true")
    try:
        print(json.dumps(run(parser.parse_args(argv)), sort_keys=True)); return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"worker": "refused-or-interrupted", "inspect_receipt_and_batch_audit": True}), file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
