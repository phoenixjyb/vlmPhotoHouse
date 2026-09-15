"""End-to-end security coverage for the exact-task face worker launcher."""
from contextlib import closing, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "tests" / "security"))
import provision_access as provisioning_cli
import run_face_worker as launcher
import test_scoped_face_worker as scoped
from app.access.credentials import hash_password

PASSWORD = "Synthetic family passphrase!"
NOW = int(time.time())


class FaceWorkerLauncherTests(unittest.TestCase):
    def setUp(self):
        self.real_popen = subprocess.Popen
        self.fixture = scoped.ScopedFaceWorkerTests("run"); self.fixture.setUp(); self.addCleanup(self._cleanup_fixture)
        self.tmp = tempfile.TemporaryDirectory(prefix="face-launcher-"); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self.db, self.backup = root / "database.sqlite", root / "backup.sqlite"
        self.request, self.plan, self.stop = root / "request.json", root / "face-plan.json", root / "stop"
        with closing(sqlite3.connect(self.db)) as dst, self.fixture.engine.connect() as src:
            src.connection.driver_connection.backup(dst)
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE access_accounts SET password_hash=? WHERE id=?", (hash_password(PASSWORD), scoped.ACTOR)); db.commit()
        self.pristine = self.db.read_bytes()
        self.payload = {"library_id":"library-a", "operator_account_id":scoped.ACTOR,
            "embedding_model":scoped.MODEL, "embedding_version":scoped.VERSION, "embedding_dim":2,
            "embedding_alignment":scoped.ALIGNMENT, "embedding_status":"active", "score_threshold":.82,
            "margin":.015, "max_faces":100, "min_ref_faces":1, "person_ids":[1]}

    def _cleanup_fixture(self):
        self.fixture.tearDown(); self.fixture.doCleanups()

    def _call(self, command, *args):
        return provisioning_cli.main([command, "--database", str(self.db), *map(str, args)], clock=lambda: NOW)

    def _enqueue(self):
        self.request.write_text(json.dumps({"kind":"person_label_propagate", "payload":self.payload,
                                            "quiescence_reference":"face-workers-stopped"}))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self._call("plan-face-job", "--request", self.request, "--out", self.plan), 0)
        with closing(sqlite3.connect(self.db)) as source, closing(sqlite3.connect(self.backup)) as backup: source.backup(backup)
        out = io.StringIO()
        with redirect_stdout(out): self._call("validate", "--plan", self.plan)
        digest = json.loads(out.getvalue())["plan_digest"]
        out = io.StringIO()
        with redirect_stdout(out): self._call("review", "--plan", self.plan, "--backup", self.backup,
            "--reviewed-plan-digest", digest, "--authority-reference", "face-authority", "--restore-reference", "face-restore")
        review = json.loads(out.getvalue())
        with redirect_stdout(io.StringIO()), patch("app.access.provisioning_apply.getpass.getpass", return_value=PASSWORD):
            self.assertEqual(self._call("apply", "--plan", self.plan, "--backup", self.backup,
                "--reviewed-plan-digest", digest, "--authority-reference", "face-authority",
                "--restore-reference", "face-restore", "--review-digest", review["review_digest"],
                "--all-writers-stopped"), 0)
        with closing(sqlite3.connect(self.db)) as db:
            return json.loads(db.execute("SELECT receipt FROM access_provisioning_receipts").fetchone()[0])

    def _args(self, receipt, *, digest=None):
        return SimpleNamespace(database=self.db, embedding_root=self.fixture.root, task_id=str(receipt["task_id"]),
            plan_id=receipt["plan_id"], reviewed_plan_digest=digest or receipt["plan_digest"], stop_file=self.stop,
            execute=True, legacy_worker_stopped=True)

    def _child(self, receipt, *, stop_file=None, clock=NOW, scripts=ROOT/'scripts'):
        args = vars(self._args(receipt))
        if stop_file is not None:
            args['stop_file'] = stop_file
        values = {k:str(v) if isinstance(v, Path) else v for k,v in args.items()}
        code = """
import json, sys
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
with ExitStack() as guards:
    for target in ('socket.socket.connect','socket.socket.bind','subprocess.Popen','os.system'):
        guards.enter_context(patch(target,side_effect=AssertionError('External I/O forbidden')))
    import run_face_worker
    result = run_face_worker.run(SimpleNamespace(**json.loads(sys.argv[2])),clock=lambda:int(sys.argv[3]))
    print(json.dumps(result))
"""
        # The fixture fences subprocess creation. Only this test harness may
        # launch the isolated child, which reinstates all external-I/O fences.
        with patch('subprocess.Popen', self.real_popen):
            return subprocess.run([sys.executable,'-c',code,str(scripts),
                json.dumps(values),str(clock)],text=True,capture_output=True,check=False,timeout=30)

    def _rows(self, sql, args=()):
        with closing(sqlite3.connect(self.db)) as db: return db.execute(sql, args).fetchall()

    def test_success_assigns_only_bound_task_and_preserves_caption_queue(self):
        receipt = self._enqueue(); before_caption = self._rows("SELECT text FROM captions WHERE id=900")
        result = self._child(receipt)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["completed"])
        self.assertEqual(self._rows("SELECT person_id,label_source FROM face_detections WHERE id=15"), [(1, "dnn")])
        self.assertEqual(self._rows("SELECT state FROM tasks WHERE id=?", (receipt["task_id"],)), [("finished",)])
        self.assertEqual(self._rows("SELECT text FROM captions WHERE id=900"), before_caption)
        self.assertEqual(self._rows("SELECT type,state FROM tasks WHERE id=900"), [("caption", "pending")])
        self.assertEqual(self._rows("SELECT count(*) FROM access_audit WHERE action=?", ("face.batch." + str(receipt["task_id"]),)), [(1,)])

    def test_default_preflight_is_read_only_and_requires_durable_receipt(self):
        before = self.db.read_bytes()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO tasks(id,type,payload_json,state,cancel_requested,scheduled_at) VALUES (901,'person_cluster','{}','pending',0,NULL)")
            db.execute("INSERT INTO access_provisioning_receipts(plan_id,plan_digest,receipt) VALUES (?,?,?)",
                       ("00000000-0000-4000-8000-000000000007", "a" * 64, "{}")); db.commit()
        before = self.db.read_bytes()
        result = launcher.preflight(self.db, self.fixture.root, "901",
                                    "00000000-0000-4000-8000-000000000007", "a" * 64, self.stop)
        self.assertTrue(result["cohort_revalidation_required"])
        self.assertEqual(self.db.read_bytes(), before)

    def test_corrupt_vector_rolls_back_face_changes_and_caption_unchanged(self):
        receipt = self._enqueue(); before = self._rows("SELECT person_id,label_source FROM face_detections ORDER BY id")
        path = self.fixture.root / "15.npy"; path.write_bytes(path.read_bytes() + b"corrupt")
        result = self._child(receipt); self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._rows("SELECT person_id,label_source FROM face_detections ORDER BY id"), before)
        self.assertEqual(self._rows("SELECT text FROM captions WHERE id=900"), [("pending caption",)])
        self.assertEqual(self._rows("SELECT count(*) FROM access_audit WHERE action LIKE 'face.batch.%'"), [(0,)])

    def test_receipt_payload_owner_and_expiry_changes_refuse(self):
        for change in ("receipt", "payload", "owner", "expiry"):
            with self.subTest(change=change):
                self.db.write_bytes(self.pristine)
                if self.plan.exists(): self.plan.unlink()
                receipt = self._enqueue()
                with closing(sqlite3.connect(self.db)) as db:
                    if change == "receipt":
                        value = json.loads(db.execute("SELECT receipt FROM access_provisioning_receipts").fetchone()[0]); value["task_id"] += 1
                        db.execute("UPDATE access_provisioning_receipts SET receipt=?", (json.dumps(value),))
                    elif change == "payload": db.execute("UPDATE tasks SET payload_json='{}' WHERE id=?", (receipt["task_id"],))
                    elif change == "owner": db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (scoped.ACTOR,))
                    db.commit()
                result = self._child(receipt, clock=NOW+901 if change=='expiry' else NOW)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self._rows("SELECT state FROM tasks WHERE id=?", (receipt['task_id'],)), [('pending',)])

    def test_stopfile_and_kernel_lock_refuse_without_claiming(self):
        receipt = self._enqueue(); self.stop.touch()
        self.assertNotEqual(self._child(receipt).returncode, 0)
        self.stop.unlink()
        with launcher.kernel_lock(self.db):
            self.assertNotEqual(self._child(receipt).returncode, 0)
        self.assertEqual(self._rows("SELECT state FROM tasks WHERE id=?", (receipt["task_id"],)), [("pending",)])

    def test_completion_failure_rolls_back_already_assigned_face_and_batch_audit(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("""CREATE TRIGGER reject_completed_face_task BEFORE UPDATE OF state ON tasks
                WHEN NEW.type='person_label_propagate' AND NEW.state='finished'
                  AND EXISTS(SELECT 1 FROM face_detections WHERE id=15 AND label_source='dnn')
                BEGIN SELECT RAISE(ABORT,'synthetic completion failure after assignment'); END""")
            db.commit()
        receipt = self._enqueue()
        before = self._rows('SELECT person_id,label_source FROM face_detections ORDER BY id')
        result = self._child(receipt)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self._rows('SELECT person_id,label_source FROM face_detections ORDER BY id'), before)
        self.assertEqual(self._rows("SELECT count(*) FROM access_audit WHERE action LIKE 'face.batch.%'"), [(0,)])
        self.assertEqual(self._rows('SELECT state,started_at FROM tasks WHERE id=?', (receipt['task_id'],)), [('pending', None)])

    def test_source_package_executes_without_legacy_imports(self):
        import build_face_worker_package as package
        receipt = self._enqueue()
        output = self.db.parent/'source-package'
        data = package.package_bytes('a'*40, {name:(ROOT/name).read_bytes() for name in package.FILES})
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive.extractall(output)  # Locally constructed exact allowlist, not external input.
        result = self._child(receipt, scripts=output/'scripts')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['assigned'], 1)


if __name__ == "__main__": unittest.main()
