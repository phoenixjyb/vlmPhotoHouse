"""Security contract for offline, owner-authorized face-job enqueueing.

The command is intentionally exercised through ``provision_access.py``.  The
database is a migrated synthetic copy of ``test_scoped_face_worker`` and the
payload is the worker's existing, library-scoped payload; no inference files,
media, caption rows, or network services are involved.
"""
from contextlib import closing, redirect_stderr, redirect_stdout
import io
import getpass
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import warnings
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "security"))
import provision_access as cli
import test_scoped_face_worker as scoped
from app.access.credentials import hash_password


PASSWORD = "Synthetic family passphrase!"


class FaceJobControlTests(unittest.TestCase):
    def setUp(self):
        self.fixture = scoped.ScopedFaceWorkerTests("run")
        self.fixture.setUp()
        self.addCleanup(self._cleanup_fixture)
        self.tmp = tempfile.TemporaryDirectory(prefix="face-job-control-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self.db, self.backup = root / "database.sqlite", root / "backup.sqlite"
        self.request, self.plan = root / "request.json", root / "face-plan.json"
        with closing(sqlite3.connect(self.db)) as dst, self.fixture.engine.connect() as src:
            src.connection.driver_connection.backup(dst)
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE access_accounts SET password_hash=? WHERE id=?",
                        (hash_password(PASSWORD), scoped.ACTOR))
            db.commit()
        self.pristine = self.db.read_bytes()
        self.payload = {
            "library_id": "library-a", "operator_account_id": scoped.ACTOR,
            "embedding_model": scoped.MODEL, "embedding_version": scoped.VERSION,
            "embedding_dim": 2, "embedding_alignment": scoped.ALIGNMENT,
            "embedding_status": "active", "score_threshold": .82, "margin": .015,
            "max_faces": 100, "min_ref_faces": 1, "person_ids": [1],
        }

    def _cleanup_fixture(self):
        self.fixture.tearDown()
        self.fixture.doCleanups()

    def call(self, command, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main([command, "--database", str(self.db), *map(str, args)],
                            clock=lambda: 2_000_000_000)
        return code, (json.loads(out.getvalue()) if out.getvalue() else None), err.getvalue()

    def make_plan(self, *, kind="person_label_propagate", quiescence="face-workers-stopped"):
        if self.plan.exists():
            self.plan.unlink()
        self.request.write_text(json.dumps({"kind": kind, "payload": self.payload,
                                             "quiescence_reference": quiescence}))
        return self.call("plan-face-job", "--request", self.request, "--out", self.plan)

    def review(self):
        with closing(sqlite3.connect(self.db)) as source, closing(sqlite3.connect(self.backup)) as backup:
            source.backup(backup)
        digest = self.call("validate", "--plan", self.plan)[1]["plan_digest"]
        result = self.call("review", "--plan", self.plan, "--backup", self.backup,
                         "--reviewed-plan-digest", digest,
                         "--authority-reference", "synthetic-face-authority",
                         "--restore-reference", "synthetic-face-restore")
        self.reviewed = result[1]
        self.plan_digest = digest
        return result

    def apply(self, *, stopped=True, password=PASSWORD, warning=False, prompt_mock=False):
        reviewed = self.reviewed
        digest = json.loads(self.plan.read_text())["plan"]["plan_id"]
        args = ["--plan", self.plan, "--backup", self.backup,
                "--reviewed-plan-digest", self.plan_digest,
                "--authority-reference", "synthetic-face-authority",
                "--restore-reference", "synthetic-face-restore",
                "--review-digest", reviewed["review_digest"]]
        if stopped:
            args.append("--all-writers-stopped")
        if warning:
            def echo_fallback(_):
                warnings.warn("echo fallback", getpass.GetPassWarning)
                return PASSWORD
            password_patch = patch("app.access.provisioning_apply.getpass.getpass", side_effect=echo_fallback)
        else:
            password_patch = (patch("app.access.provisioning_apply.getpass.getpass", side_effect=password)
                              if isinstance(password, BaseException)
                              else patch("app.access.provisioning_apply.getpass.getpass", return_value=password))
        with password_patch as prompt:
            result = self.call("apply", *args)
        if prompt_mock:
            self.prompt_calls = prompt.call_count
        return result

    def rows(self, sql):
        with closing(sqlite3.connect(self.db)) as db:
            return db.execute(sql).fetchall()

    def test_happy_path_requires_existing_owner_password_and_only_enqueues(self):
        before = self.rows("SELECT id,person_id,label_source FROM face_detections ORDER BY id")
        self.assertEqual(self.make_plan()[0], 0)
        result = self.review()[1]
        self.assertEqual(result["reviewed_effects"]["media_writes"], False)
        code, applied, _ = self.apply()
        self.assertEqual(code, 0); self.assertTrue(applied["applied"])
        self.assertEqual(self.rows("SELECT id,person_id,label_source FROM face_detections ORDER BY id"), before)
        self.assertEqual(self.rows("SELECT text FROM captions WHERE id=900"), [("pending caption",)])
        self.assertEqual(self.rows("SELECT type,state FROM tasks WHERE id=900"), [("caption", "pending")])
        self.assertEqual(self.rows("SELECT type,state FROM tasks WHERE type='person_label_propagate'"),
                         [("person_label_propagate", "pending")])
        receipt = self.rows("SELECT receipt FROM access_provisioning_receipts")[0][0]
        receipt = json.loads(receipt)
        self.assertEqual(receipt["task_id"], self.rows(
            "SELECT id FROM tasks WHERE type='person_label_propagate'")[0][0])
        self.assertEqual(self.call("receipt", "--plan-id", receipt["plan_id"],
                                   "--reviewed-plan-digest", receipt["plan_digest"])[1]["receipt_found"], True)

    def test_private_password_failures_and_missing_stop_flag_have_no_effect(self):
        self.make_plan(); self.review()
        before = self.db.read_bytes()
        self.assertEqual(self.apply(stopped=True, password=PASSWORD + " wrong")[0], 2)
        self.assertEqual(self.db.read_bytes(), before)
        self.make_plan(); self.review()
        self.assertEqual(self.apply(stopped=True, warning=True)[0], 2)
        self.make_plan(quiescence="another-stopped-reference")
        self.review()
        self.assertEqual(self.apply(stopped=False, prompt_mock=True)[0], 2)
        self.assertEqual(self.prompt_calls, 0)

    def test_stale_scope_membership_faces_hash_and_foreign_or_unowned_scope_refuse(self):
        for mutate in (
            "UPDATE access_memberships SET revision=revision+1 WHERE library_id='library-a'",
            "UPDATE face_detections SET label_source='manual' WHERE id=15",
            "UPDATE assets SET hash_sha256='changed' WHERE id=5",
        ):
            with self.subTest(mutate=mutate):
                self.db.write_bytes(self.pristine)
                self.make_plan(); self.rows("SELECT 1")
                with closing(sqlite3.connect(self.db)) as db: db.execute(mutate); db.commit()
                self.assertEqual(self.call("validate", "--plan", self.plan)[0], 2)
        self.db.write_bytes(self.pristine)
        self.make_plan(); self.review()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE face_embedding_artifacts SET vector_checksum=? WHERE face_id=11", ("0" * 64,)); db.commit()
        self.assertEqual(self.apply()[0], 2)
        self.db.write_bytes(self.pristine)
        self.make_plan(); self.review()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE access_accounts SET password_hash=? WHERE id=?", ("synthetic", scoped.ACTOR)); db.commit()
        self.assertEqual(self.apply()[0], 2)
        self.payload["library_id"] = "library-b"
        self.assertEqual(self.make_plan()[0], 2)
        self.payload["library_id"], self.payload["person_ids"] = "library-a", [2]
        self.assertEqual(self.make_plan()[0], 2)

    def test_audit_failure_rolls_back_task_and_receipt_without_touching_caption(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("CREATE TRIGGER reject_face_enqueue_audit BEFORE INSERT ON access_audit "
                       "BEGIN SELECT RAISE(ABORT,'synthetic audit refusal'); END")
            db.commit()
        # Include the trigger in both the sealed plan snapshot and its backup;
        # the failure therefore occurs during the write transaction, not review.
        self.make_plan(); self.review()
        before = self.rows("SELECT id,person_id,label_source FROM face_detections ORDER BY id")
        self.assertEqual(self.apply()[0], 2)
        self.assertEqual(self.rows("SELECT type FROM tasks WHERE type='person_label_propagate'"), [])
        self.assertEqual(self.rows("SELECT count(*) FROM access_provisioning_receipts"), [(0,)])
        self.assertEqual(self.rows("SELECT id,person_id,label_source FROM face_detections ORDER BY id"), before)
        self.assertEqual(self.rows("SELECT text FROM captions WHERE id=900"), [("pending caption",)])

    def test_enqueue_path_has_no_network_process_or_shell_side_effects(self):
        with patch("socket.socket.connect") as connect, patch("subprocess.Popen") as popen, patch("os.system") as system:
            self.assertEqual(self.make_plan()[0], 0)
            self.review()
            self.assertEqual(self.apply()[0], 0)
        connect.assert_not_called(); popen.assert_not_called(); system.assert_not_called()

    def test_each_supported_assignment_kind_is_plannable(self):
        self.payload.pop("person_ids")
        for kind in ("person_cluster", "person_recluster"):
            with self.subTest(kind=kind):
                self.assertEqual(self.make_plan(kind=kind)[0], 0)
                self.assertEqual(self.call("validate", "--plan", self.plan)[0], 0)

    def test_backup_mismatch_rollback_and_replay_are_fail_closed(self):
        self.make_plan(); self.review()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE assets SET hash_sha256='unreviewed' WHERE id=900"); db.commit()
        self.assertEqual(self.apply()[0], 2)
        self.assertEqual(self.rows("SELECT count(*) FROM access_provisioning_receipts"), [(0,)])
        self.make_plan(); self.review(); self.assertEqual(self.apply()[0], 0)
        self.assertEqual(self.apply()[0], 2)


if __name__ == "__main__":
    unittest.main()
