"""Child-process fixture and tests for real TaskExecutor face dispatch."""
from __future__ import annotations
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ["PHOTOHOUSE_NO_DOTENV"] = "1"
os.environ["VLM_SKIP_LOCAL_ENV_FILES"] = "1"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tests" / "security"))

from sqlalchemy import event, inspect, text
from sqlalchemy.orm import Session
from app.db import Task
import test_scoped_face_worker as scoped_fixture_source

ACTOR = scoped_fixture_source.ACTOR

class ScopedTaskExecutorFixture:
    def __init__(self):
        self.base = scoped_fixture_source.ScopedFaceWorkerTests("runTest")
        self.base.setUp()
        self.engine, self.root = self.base.engine, self.base.root
    def close(self):
        self.base.doCleanups()
    def task_payload(self, **payload):
        data = {"library_id":"library-a", "operator_account_id":ACTOR,
                "embedding_model":"synthetic-face", "embedding_version":"synthetic-face-v1",
                "embedding_dim":2, "embedding_alignment":"five-point-112",
                "embedding_status":"active", "score_threshold":.82, "margin":.015,
                "min_ref_faces":1}
        data.update(payload)
        return data
    def pending_task(self, kind, **payload):
        with Session(self.engine) as db:
            task = Task(type=kind, payload_json=self.task_payload(**payload), state="pending", priority=-100)
            db.add(task); db.commit(); return int(task.id)
    def rows(self, query):
        return self.base.rows(query)
    @staticmethod
    def settings():
        return SimpleNamespace(max_task_retries=1, retry_backoff_base_seconds=0.0,
                               retry_backoff_cap_seconds=0.0, retry_backoff_jitter=0.0,
                               worker_poll_interval=.01)

class ScopedWorkerHandlerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ScopedTaskExecutorFixture(); self.addCleanup(self.fixture.close)
        os.environ.update({"DERIVED_PATH":str(self.fixture.root), "VLM_DATA_ROOT":str(self.fixture.root), "DISABLE_ENV_GUARD":"1"})
        import app.tasks as tasks
        self.tasks = tasks; self.tasks.DERIVED_DIR = self.fixture.root
        self.guards = [patch.object(self.tasks, name, side_effect=AssertionError("model/index init forbidden"))
                       for name in ("EmbeddingService", "InMemoryVectorIndex", "FaissVectorIndex")]
        for guard in self.guards: guard.start(); self.addCleanup(guard.stop)
    def executor(self):
        executor = self.tasks.TaskExecutor(session_factory=lambda: Session(self.fixture.engine),
                                           settings=self.fixture.settings(), face_assignment_only=True)
        return executor
    def task_state(self, task_id):
        with self.fixture.engine.connect() as conn:
            return conn.execute(text("SELECT state,last_error FROM tasks WHERE id=:id"), {"id":task_id}).one()
    def run_success(self, kind, **payload):
        before = self.fixture.rows("SELECT id,person_id,label_source,label_score FROM face_detections ORDER BY id")
        task_id = self.fixture.pending_task(kind, **payload)
        self.assertTrue(self.executor().run_once()); self.assertEqual("finished", self.task_state(task_id)[0])
        after = self.fixture.rows("SELECT id,person_id,label_source,label_score FROM face_detections ORDER BY id")
        self.assertEqual(before[0:4], after[0:4]); self.assertIsNone(after[3][1])
        self.assertEqual((1, "dnn"), self.fixture.rows("SELECT person_id,label_source FROM face_detections WHERE id=15")[0])
        self.assertGreater(self.fixture.rows("SELECT count(*) FROM face_assignment_events")[0][0], 0)
        self.assertEqual("pending caption", self.fixture.rows("SELECT text FROM captions WHERE id=900")[0][0])
        self.assertFalse(self.executor().run_once())
        self.assertEqual('pending', self.fixture.rows('SELECT state FROM tasks WHERE id=900')[0][0])
    def test_run_once_cluster_actual_handler_preserves_manual_null(self): self.run_success("person_cluster")
    def test_run_once_recluster_actual_handler_preserves_manual_null(self): self.run_success("person_recluster")
    def test_run_once_propagation_actual_handler_matches_scoped_candidate(self): self.run_success("person_label_propagate", person_ids=[1])
    def test_missing_scope_fails_task_without_mutating_faces(self):
        before = self.fixture.rows("SELECT id,person_id,label_source,label_score FROM face_detections ORDER BY id")
        task_id = self.fixture.pending_task("person_cluster")
        with Session(self.fixture.engine) as db:
            db.execute(text("UPDATE tasks SET payload_json=:payload WHERE id=:id"), {"id":task_id, "payload":'{"operator_account_id":"'+ACTOR+'","embedding_model":"synthetic-face","embedding_version":"synthetic-face-v1","embedding_dim":2,"embedding_alignment":"five-point-112","embedding_status":"active","min_ref_faces":1}'}); db.commit()
        self.assertTrue(self.executor().run_once()); state, error = self.task_state(task_id)
        self.assertEqual("failed", state); self.assertIn("scoped", error.lower())
        self.assertEqual(before, self.fixture.rows("SELECT id,person_id,label_source,label_score FROM face_detections ORDER BY id"))
    def test_audit_failure_rolls_back_handler_mutation(self):
        before = self.fixture.rows("SELECT id,person_id,label_source,label_score FROM face_detections ORDER BY id")
        with self.fixture.engine.begin() as conn: conn.exec_driver_sql("CREATE TRIGGER reject_face_audit BEFORE INSERT ON face_assignment_events BEGIN SELECT RAISE(ABORT,'audit refusal'); END")
        task_id = self.fixture.pending_task("person_cluster"); self.assertTrue(self.executor().run_once()); state, error = self.task_state(task_id)
        self.assertEqual("failed", state); self.assertIn("rolled back", error.lower()); self.assertEqual(before, self.fixture.rows("SELECT id,person_id,label_source,label_score FROM face_detections ORDER BY id"))
        self.assertEqual(0, self.fixture.rows("SELECT count(*) FROM face_assignment_events")[0][0])
    def test_missing_audit_table_direct_and_dispatch_refuse_without_ddl(self):
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany): statements.append(statement.upper())
        event.listen(self.fixture.engine, "before_cursor_execute", capture)
        try:
            with self.fixture.engine.begin() as conn: conn.exec_driver_sql("DROP TABLE face_assignment_events")
            import app.face_assignment_audit as audit
            with Session(self.fixture.engine) as db:
                with self.assertRaisesRegex(ValueError, "audit schema"): audit._ensure_audit_table(db)
            task_id = self.fixture.pending_task("person_cluster"); self.assertTrue(self.executor().run_once())
        finally: event.remove(self.fixture.engine, "before_cursor_execute", capture)
        self.assertEqual("failed", self.task_state(task_id)[0]); self.assertFalse(any(s.startswith(("CREATE TABLE", "ALTER TABLE")) for s in statements))
        self.assertEqual("pending caption", self.fixture.rows("SELECT text FROM captions WHERE id=900")[0][0])
    def test_legacy_dependency_initialization_refuses_protected_fixture_without_ddl(self):
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany): statements.append(statement.upper())
        import app.dependencies as dependencies
        old = dependencies.engine, dependencies.SessionLocal, dependencies._DB_READY; event.listen(self.fixture.engine, "before_cursor_execute", capture)
        try:
            dependencies.engine, dependencies.SessionLocal, dependencies._DB_READY = self.fixture.engine, None, False
            with patch.object(dependencies, "_rebind_if_needed", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "Protected database"): dependencies.ensure_db()
        finally:
            event.remove(self.fixture.engine, "before_cursor_execute", capture); dependencies.engine, dependencies.SessionLocal, dependencies._DB_READY = old
        self.assertFalse(any(s.startswith(("CREATE TABLE", "ALTER TABLE")) for s in statements)); self.assertTrue(inspect(self.fixture.engine).has_table("access_libraries"))

if __name__ == "__main__": unittest.main(verbosity=1)
