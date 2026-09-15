"""Synthetic regression coverage for the library-scoped face assignment worker.

The fixture deliberately writes tiny NumPy-compatible files with the stdlib.  It
does not import an inference provider, open a socket, or create schema at import
time; the worker is responsible for all validation and mutation fencing.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tests" / "security"))
from app.db import Asset, Base, Caption, FaceDetection, FaceEmbeddingArtifact, Person, PersonEmbeddingArtifact, Task
from app.scoped_face_worker import AssignmentRefused
from test_orm_migrations import config


MODEL = "synthetic-face"
VERSION = "synthetic-face-v1"
ALIGNMENT = "five-point-112"
ACTOR = "00000000-0000-4000-8000-000000000001"
FOREIGN = "00000000-0000-4000-8000-000000000002"


def npy(path: Path, values: list[float], *, dtype: str = "<f4") -> str:
    """Write a minimal, valid NumPy v1.0 little-endian 1-D array."""
    code = {"<f4": (b"\x93NUMPY\x01\x00", "<f4", "<f"), "<f8": (b"\x93NUMPY\x01\x00", "<f8", "<d")}[dtype]
    raw = b"".join(struct.pack(code[2], value) for value in values)
    header = ("{'descr': '%s', 'fortran_order': False, 'shape': (%d,), }" % (code[1], len(values))).encode()
    header += b" " * ((16 - ((10 + len(header) + 1) % 16)) % 16) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(code[0] + struct.pack("<H", len(header)) + header + raw)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ScopedFaceWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="scoped-face-worker-")
        self.addCleanup(self.tmp.cleanup)
        self.root = (Path(self.tmp.name).resolve() / "embeddings")
        self.root.mkdir()
        for target in ("socket.socket.connect", "socket.socket.bind", "subprocess.Popen", "os.system"):
            guard = patch(target, side_effect=AssertionError("External I/O forbidden"))
            guard.start(); self.addCleanup(guard.stop)
        self.engine = create_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as conn:
            cfg = config(); cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            conn.exec_driver_sql("""INSERT INTO access_accounts(id,phone_login,password_hash)
                VALUES (:actor,'+12025550100','synthetic'),(:foreign,'+12025550101','synthetic')""", {"actor": ACTOR, "foreign": FOREIGN})
            conn.exec_driver_sql("INSERT INTO access_operators(account_id) VALUES (:actor)", {"actor": ACTOR})
            conn.exec_driver_sql("""INSERT INTO access_libraries(id,bootstrap_operator)
                VALUES ('library-a',:actor),('library-b',:foreign)""", {"actor": ACTOR, "foreign": FOREIGN})
            conn.exec_driver_sql("""INSERT INTO access_memberships
                (account_id,library_id,status,role,revision,approved_by)
                VALUES (:actor,'library-a','approved','owner',1,:actor),
                       (:foreign,'library-b','approved','owner',1,:foreign)""", {"actor": ACTOR, "foreign": FOREIGN})
            # Pending caption work is an independent queue and must survive.
            conn.exec_driver_sql("""INSERT INTO assets
                (id,path,hash_sha256,status) VALUES (900,'synthetic/caption.jpg','h900','active')""")
            conn.exec_driver_sql("""INSERT INTO captions
                (id,asset_id,text,model,user_edited,superseded) VALUES
                (900,900,'pending caption','synthetic',0,0)""")
            conn.exec_driver_sql("""INSERT INTO tasks
                (id,type,payload_json,state) VALUES (900,'caption','{}','pending')""")
        self._seed_faces()

    def _seed_faces(self):
        with Session(self.engine) as db:
            for asset_id, library in ((1, "library-a"), (2, "library-a"), (3, "library-b"), (4, None), (5, "library-a"), (6, "library-a")):
                db.add(Asset(id=asset_id, path=f"synthetic/{asset_id}.jpg", hash_sha256=f"h{asset_id}", status="active"))
            db.flush()
            for asset_id, library in ((1, "library-a"), (2, "library-a"), (3, "library-b"), (4, None), (5, "library-a"), (6, "library-a")):
                if library:
                    db.execute(text("INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (:id,:lib)"), {"id": asset_id, "lib": library})
            # Person 1 is an owned manual reference; person 2 is intentionally unowned.
            db.add_all([Person(id=1, display_name="owned", face_count=1), Person(id=2, display_name="unowned", face_count=1), Person(id=3, display_name="foreign", face_count=1)])
            db.flush()
            db.execute(text("INSERT INTO access_person_libraries(person_id,library_id,creator_id,revision) VALUES (3,'library-b',:actor,1)"), {"actor": FOREIGN})
            db.execute(text("INSERT INTO access_person_libraries(person_id,library_id,creator_id,revision) VALUES (1,'library-a',:actor,1)"), {"actor": ACTOR})
            faces = [
                FaceDetection(id=11, asset_id=1, person_id=1, label_source="manual", bbox_x=0, bbox_y=0, bbox_w=1, bbox_h=1),
                FaceDetection(id=12, asset_id=2, person_id=None, label_source="manual", bbox_x=0, bbox_y=0, bbox_w=1, bbox_h=1),
                FaceDetection(id=13, asset_id=3, person_id=3, label_source="manual", bbox_x=0, bbox_y=0, bbox_w=1, bbox_h=1),
                FaceDetection(id=14, asset_id=4, person_id=None, label_source=None, bbox_x=0, bbox_y=0, bbox_w=1, bbox_h=1),
                FaceDetection(id=15, asset_id=5, person_id=None, label_source="dnn", bbox_x=0, bbox_y=0, bbox_w=1, bbox_h=1),
                FaceDetection(id=16, asset_id=6, person_id=2, label_source="dnn", bbox_x=0, bbox_y=0, bbox_w=1, bbox_h=1),
            ]
            db.add_all(faces); db.flush()
            for face_id in (11, 12, 13, 14, 15, 16):
                path = self.root / f"{face_id}.npy"
                checksum = npy(path, [1.0, 0.0])
                db.add(FaceEmbeddingArtifact(face_id=face_id, model=MODEL, model_version=VERSION, dim=2,
                    alignment=ALIGNMENT, storage_path=str(path), vector_checksum=checksum, status="active"))
            db.commit()

    def task(self, kind: str, **payload) -> Task:
        data = {"library_id": "library-a", "operator_account_id": ACTOR, "embedding_model": MODEL,
                "embedding_version": VERSION, "embedding_dim": 2, "embedding_alignment": ALIGNMENT,
                "embedding_status": "active", "score_threshold": .82, "margin": .015,
                "min_ref_faces": 2, **payload}
        with Session(self.engine) as db:
            task = Task(type=kind, payload_json=data, state="running")
            db.add(task); db.commit(); db.refresh(task)
            return task

    def invoke_worker(self, kind: str, **payload):
        from app.scoped_face_worker import run_scoped_assignment
        task = self.task(kind, **payload)
        with Session(self.engine) as db:
            live = db.get(Task, task.id)
            return run_scoped_assignment(db, live, embedding_root=self.root, clock=lambda: 2_000_000_000)

    def rows(self, query):
        with self.engine.connect() as conn:
            return conn.execute(text(query)).all()

    def test_manual_positive_and_null_preserved_for_all_operations_and_scope_exclusions(self):
        before = self.rows("SELECT id,person_id,label_source,label_score FROM face_detections ORDER BY id")
        for kind, extra in (("person_cluster", {"min_ref_faces": 1}), ("person_recluster", {"min_ref_faces": 1}), ("person_label_propagate", {"person_ids": [1]})):
            self.invoke_worker(kind, **extra)
            after = self.rows("SELECT id,person_id,label_source,label_score FROM face_detections ORDER BY id")
            self.assertEqual(before[0:4], after[0:4])
            self.assertEqual(after[2], before[2])
        self.assertEqual(self.rows("SELECT person_id FROM face_detections WHERE id=13")[0][0], 3)
        self.assertIsNone(self.rows("SELECT person_id FROM face_detections WHERE id=14")[0][0])
        self.assertEqual(self.rows("SELECT person_id,label_source FROM face_detections WHERE id=15"), [(1, "dnn")])
        self.assertEqual(self.rows("SELECT face_count FROM persons WHERE id=1"), [(2,)])

    def test_propagation_refuses_unowned_or_foreign_targets(self):
        for ids in ([2], [3], [0], [1, 1], [1, 101]):
            with self.assertRaises(AssignmentRefused):
                self.invoke_worker("person_label_propagate", person_ids=ids)
        self.assertEqual(self.rows("SELECT count(*) FROM face_assignment_events")[0][0], 0)

    def test_malformed_checksum_dtype_dimension_and_outside_root_fail_closed(self):
        from app.scoped_face_worker import run_scoped_assignment
        with Session(self.engine) as db:
            db.execute(text("UPDATE face_embedding_artifacts SET vector_checksum='bad' WHERE face_id=11")); db.commit()
        with self.assertRaises(AssignmentRefused): self.invoke_worker("person_cluster")
        with Session(self.engine) as db:
            db.execute(text("UPDATE face_embedding_artifacts SET vector_checksum=NULL WHERE face_id=11")); db.commit()
        with self.assertRaises(AssignmentRefused): self.invoke_worker("person_cluster")
        outside = Path(self.tmp.name) / "outside.npy"; checksum = npy(outside, [1, 0], dtype="<f8")
        with Session(self.engine) as db:
            db.execute(text("UPDATE face_embedding_artifacts SET storage_path=:p,vector_checksum=:c WHERE face_id=11"), {"p": str(outside), "c": checksum}); db.commit()
        with self.assertRaises(AssignmentRefused): self.invoke_worker("person_cluster")

    def test_audit_failure_rolls_back_everything_but_caller_can_commit_error_state(self):
        before = self.rows("SELECT id,person_id,label_source,label_score FROM face_detections ORDER BY id")
        with self.engine.begin() as conn:
            conn.exec_driver_sql("CREATE TRIGGER reject_face_audit BEFORE INSERT ON face_assignment_events BEGIN SELECT RAISE(ABORT,'audit refusal'); END")
        from app.scoped_face_worker import run_scoped_assignment
        task = self.task("person_cluster")
        with Session(self.engine) as db:
            live = db.get(Task, task.id)
            with self.assertRaises(AssignmentRefused): run_scoped_assignment(db, live, embedding_root=self.root, clock=lambda: 2_000_000_000)
            live.state = "error"; live.last_error = "synthetic audit refusal"; db.commit()
        self.assertEqual(before, self.rows("SELECT id,person_id,label_source,label_score FROM face_detections ORDER BY id"))
        with self.engine.connect() as conn:
            self.assertEqual([("error", "synthetic audit refusal")], conn.execute(
                text("SELECT state,last_error FROM tasks WHERE id=:id"), {"id": task.id}).all())
        self.assertEqual(self.rows("SELECT count(*) FROM face_assignment_events")[0][0], 0)

    def test_missing_audit_schema_refuses_without_startup_ddl_and_caption_untouched(self):
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany): statements.append(statement.upper())
        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            with self.engine.begin() as conn: conn.exec_driver_sql("DROP TABLE face_assignment_events")
            with self.assertRaises(AssignmentRefused): self.invoke_worker("person_cluster")
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertFalse(any(s.startswith(("CREATE TABLE", "ALTER TABLE")) for s in statements))
        self.assertEqual(self.rows("SELECT text FROM captions WHERE id=900")[0][0], "pending caption")
        self.assertEqual(self.rows("SELECT state FROM tasks WHERE id=900")[0][0], "pending")

    def test_completed_task_cannot_be_replayed(self):
        from app.scoped_face_worker import run_scoped_assignment
        task = self.task("person_cluster")
        with Session(self.engine) as db:
            live = db.get(Task, task.id)
            run_scoped_assignment(db, live, embedding_root=self.root, clock=lambda: 2_000_000_000)
        with Session(self.engine) as db:
            with self.assertRaises(AssignmentRefused):
                run_scoped_assignment(db, db.get(Task, task.id), embedding_root=self.root,
                                      clock=lambda: 2_000_000_000)

    def test_fresh_propagation_assigns_only_a_same_library_candidate(self):
        self.invoke_worker("person_label_propagate", person_ids=[1], min_ref_faces=1)
        self.assertEqual(self.rows("SELECT person_id,label_source FROM face_detections WHERE id=15"), [(1, "dnn")])
        self.assertEqual(self.rows("SELECT count(*) FROM face_assignment_events WHERE new_person_id=1")[0][0], 1)

    def test_shared_person_is_not_an_explicitly_owned_propagation_target(self):
        with Session(self.engine) as db:
            db.add(FaceDetection(id=17, asset_id=3, person_id=1, label_source="manual",
                                 bbox_x=0, bbox_y=0, bbox_w=1, bbox_h=1))
            db.flush()
            path = self.root / "17.npy"; checksum = npy(path, [1.0, 0.0])
            db.add(FaceEmbeddingArtifact(face_id=17, model=MODEL, model_version=VERSION, dim=2,
                alignment=ALIGNMENT, storage_path=str(path), vector_checksum=checksum, status="active"))
            db.commit()
        with self.assertRaises(AssignmentRefused):
            self.invoke_worker("person_label_propagate", person_ids=[1], min_ref_faces=1)
        self.assertEqual(self.rows("SELECT count(*) FROM face_assignment_events")[0][0], 0)

    def test_recluster_recomputes_counts_beyond_batch_and_invalidates_person_artifacts(self):
        retained = {}
        with Session(self.engine) as db:
            db.add(Person(id=4, face_count=999)); db.flush()
            db.execute(text("INSERT INTO access_person_libraries VALUES (4,'library-a',:actor,1)"), {'actor': ACTOR})
            db.execute(text('UPDATE persons SET face_count=888 WHERE id=1'))
            db.execute(text("UPDATE face_detections SET person_id=4 WHERE id=15"))
            db.add(FaceDetection(id=17, asset_id=6, person_id=4, label_source="dnn",
                                 bbox_x=0, bbox_y=0, bbox_w=1, bbox_h=1))
            for pid in (1, 4):
                path = self.root / f'person-{pid}.npy'
                checksum = npy(path, [0., 1.]); retained[path] = path.read_bytes()
                db.execute(text('UPDATE persons SET embedding_path=:path WHERE id=:pid'), {'path': str(path), 'pid': pid})
                db.add(PersonEmbeddingArtifact(person_id=pid, model=MODEL, model_version=VERSION, dim=2,
                    source_face_count=999, storage_path=str(path), vector_checksum=checksum, status='active'))
            db.commit()
        self.invoke_worker("person_recluster", min_ref_faces=1, max_faces=1)
        self.assertEqual(self.rows('SELECT id,face_count,embedding_path FROM persons WHERE id IN (1,4) ORDER BY id'), [(1, 2, None), (4, 1, None)])
        self.assertEqual(self.rows('SELECT person_id,status FROM person_embedding_artifacts ORDER BY person_id'), [(1, 'stale'), (4, 'stale')])
        self.assertEqual(self.rows("SELECT person_id FROM face_detections WHERE id=17"), [(4,)])
        for path, data in retained.items():
            self.assertEqual(path.read_bytes(), data)

    def test_late_batch_audit_failure_rolls_back_person_ownership_counts_and_events(self):
        tables = ('persons', 'face_detections', 'access_person_libraries', 'person_embedding_artifacts',
                  'face_assignment_events', 'access_audit')
        before = {table: self.rows('SELECT * FROM ' + table) for table in tables}
        with self.engine.begin() as db:
            db.exec_driver_sql("CREATE TRIGGER late_audit_failure BEFORE INSERT ON access_audit BEGIN SELECT RAISE(ABORT,'late audit'); END")
        task = self.task('person_cluster')  # No qualifying centroid: exercises new owned person rollback.
        from app.scoped_face_worker import run_scoped_assignment
        with Session(self.engine) as db:
            live = db.get(Task, task.id)
            with self.assertRaises(AssignmentRefused):
                run_scoped_assignment(db, live, embedding_root=self.root)
            live.state = 'failed'; db.commit()
        self.assertEqual(before, {table: self.rows('SELECT * FROM ' + table) for table in tables})

    def test_owner_expiry_during_batch_rolls_back(self):
        with self.engine.begin() as db:
            db.exec_driver_sql("UPDATE access_memberships SET expires_at=2000000010 WHERE library_id='library-a'")
        from app.scoped_face_worker import run_scoped_assignment
        task = self.task('person_cluster', min_ref_faces=1)
        times = iter([2_000_000_000, 2_000_000_020])
        with Session(self.engine) as db:
            with self.assertRaises(AssignmentRefused):
                run_scoped_assignment(db, db.get(Task, task.id), embedding_root=self.root, clock=lambda: next(times))
            db.commit()
        self.assertEqual(self.rows('SELECT person_id FROM face_detections WHERE id=15'), [(None,)])
        self.assertEqual(self.rows('SELECT * FROM access_audit'), [])

    def test_dtype_and_unknown_legacy_provenance_refused(self):
        path = self.root / '15.npy'
        data = path.read_bytes().replace(b"'<f4'", b"'<i4'")
        path.write_bytes(data)
        with self.engine.begin() as db:
            db.exec_driver_sql('UPDATE face_embedding_artifacts SET vector_checksum=? WHERE face_id=15',
                               (hashlib.sha256(data).hexdigest(),))
        with self.assertRaises(AssignmentRefused):
            self.invoke_worker('person_cluster', min_ref_faces=1)
        with self.assertRaises(AssignmentRefused):
            self.invoke_worker('person_cluster', embedding_model='unknown-legacy', embedding_status='legacy')

    def test_other_vector_versions_and_shadow_artifacts_do_not_compete(self):
        for column, value in (('model_version', 'other-version'), ('status', 'shadow')):
            with self.subTest(column=column), self.engine.begin() as db:
                db.exec_driver_sql("UPDATE face_embedding_artifacts SET model_version=?,status='active' WHERE face_id=11", (VERSION,))
                db.exec_driver_sql('UPDATE face_embedding_artifacts SET ' + column + '=? WHERE face_id=11', (value,))
            result = self.invoke_worker('person_label_propagate', person_ids=[1], min_ref_faces=1)
            self.assertEqual(result['assigned'], 0)
            self.assertEqual(self.rows('SELECT person_id FROM face_detections WHERE id=15'), [(None,)])

    def test_unapproved_owner_or_invalid_payload_cannot_assign(self):
        for payload in ({'library_id': 'library-b'}, {'operator_account_id': FOREIGN},
                        {'max_faces': 501}, {'embedding_dim': 0}, {'score_threshold': float('nan')},
                        {'margin': -1}, {'embedding_status': 'shadow'}, {'unexpected': True}):
            with self.subTest(payload=payload), self.assertRaises(AssignmentRefused):
                self.invoke_worker('person_cluster', **payload)
        with self.engine.begin() as db:
            db.exec_driver_sql("UPDATE access_memberships SET status='revoked' WHERE library_id='library-a'")
        with self.assertRaises(AssignmentRefused):
            self.invoke_worker('person_cluster')
        self.assertEqual(self.rows('SELECT person_id FROM face_detections WHERE id=15'), [(None,)])
        self.assertEqual(self.rows('SELECT * FROM face_assignment_events'), [])

    def test_correct_checksum_does_not_make_shape_or_provenance_unsafe(self):
        bad = self.root / "bad-shape.npy"; checksum = npy(bad, [1.0, 0.0, 0.0])
        with Session(self.engine) as db:
            db.execute(text("UPDATE face_embedding_artifacts SET storage_path=:p,vector_checksum=:c WHERE face_id=15"),
                       {"p": str(bad), "c": checksum})
            db.commit()
        with self.assertRaises(AssignmentRefused):
            self.invoke_worker("person_cluster", min_ref_faces=1)
        with Session(self.engine) as db:
            db.execute(text("UPDATE face_embedding_artifacts SET storage_path=:p,vector_checksum=:c WHERE face_id=15"),
                       {"p": str(self.root / "15.npy"), "c": hashlib.sha256((self.root / "15.npy").read_bytes()).hexdigest()})
            db.execute(text("UPDATE face_embedding_artifacts SET storage_path=:p,vector_checksum=:c,status='shadow' WHERE face_id=11"),
                       {"p": str(self.root / "11.npy"), "c": hashlib.sha256((self.root / "11.npy").read_bytes()).hexdigest()})
            db.commit()
        self.invoke_worker("person_cluster", min_ref_faces=1)
        self.assertEqual(self.rows("SELECT person_id,label_source FROM face_detections WHERE id=11"), [(1, "manual")])


if __name__ == "__main__":
    unittest.main()
