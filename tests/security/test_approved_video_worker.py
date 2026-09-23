import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "approved_video_worker", ROOT / "scripts" / "run_approved_video_worker.py"
)
worker_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker_module)
ApprovedVideoWorker = worker_module.ApprovedVideoWorker


class ApprovedVideoWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="photohouse-approved-video-")
        self.root = Path(self.tmp.name).resolve()
        self.db_path = self.root / "metadata.sqlite"
        self.media = self.root / "originals"
        self.media.mkdir()
        self.derived = self.root / "derived"
        self.derived.mkdir()
        db = sqlite3.connect(self.db_path)
        db.executescript(
            """
            CREATE TABLE assets(
              id INTEGER PRIMARY KEY,path TEXT,hash_sha256 TEXT,file_size INTEGER,
              mime TEXT,status TEXT,duration_sec REAL,width INTEGER,height INTEGER,fps REAL);
            CREATE TABLE access_uploads(asset_id INTEGER,state TEXT,sha256 TEXT,bytes INTEGER);
            CREATE TABLE access_asset_libraries(asset_id INTEGER,library_id TEXT);
            CREATE TABLE access_libraries(id TEXT,state TEXT);
            CREATE TABLE tasks(
              id INTEGER PRIMARY KEY AUTOINCREMENT,type TEXT,payload_json TEXT,state TEXT,
              priority INTEGER,retry_count INTEGER,cancel_requested INTEGER,scheduled_at TEXT,
              started_at TEXT,finished_at TEXT,updated_at TEXT,last_error TEXT,created_at TEXT);
            CREATE TABLE alembic_version(version_num TEXT NOT NULL);
            INSERT INTO alembic_version VALUES('a8d4c2e6f901');
            """
        )
        self.source = self.media / "member.mp4"
        self.source.write_bytes(b"synthetic video bytes")
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        db.execute("INSERT INTO assets VALUES(1,?,?,?,?,?,?,?,?,?)",
                   (str(self.source), digest, self.source.stat().st_size, "video/mp4", "active", None, None, None, None))
        db.execute("INSERT INTO access_uploads VALUES(1,'assigned',?,?)",
                   (digest, self.source.stat().st_size))
        db.execute("INSERT INTO access_asset_libraries VALUES(1,'family')")
        db.execute("INSERT INTO access_libraries VALUES('family','active')")
        db.execute("INSERT INTO tasks(type,payload_json,state,priority,retry_count,cancel_requested,scheduled_at,created_at) VALUES('video_probe',?,'pending',40,0,0,datetime('now'),datetime('now'))",
                   (json.dumps({"asset_id": 1}),))
        # An unrelated legacy task must remain untouched by this worker.
        db.execute("INSERT INTO tasks(type,payload_json,state,priority,retry_count,cancel_requested,scheduled_at,created_at) VALUES('video_probe',?,'pending',1,0,0,datetime('now'),datetime('now'))",
                   (json.dumps({"asset_id": 99}),))
        db.commit(); db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def worker(self):
        probe = self.root / "ffprobe.exe"
        ffmpeg = self.root / "ffmpeg.exe"
        probe.touch(); ffmpeg.touch()
        return ApprovedVideoWorker(self.db_path, self.derived, (self.media,),
                                    ffprobe=str(probe), ffmpeg=str(ffmpeg),
                                    once=True, poll_seconds=.01)

    def test_probe_claims_only_approved_mapped_member_upload_and_enqueues_frames(self):
        def fake_run(args, **kwargs):
            return (json.dumps({"streams": [{"codec_type": "video", "width": 640,
                                               "height": 480, "duration": "4", "r_frame_rate": "30/1"}],
                                "format": {"duration": "4"}}), "")
        with patch.object(worker_module, "run_command", side_effect=fake_run):
            self.assertTrue(self.worker().run_once())
        db = sqlite3.connect(self.db_path)
        task = db.execute("SELECT state FROM tasks WHERE id=1").fetchone()[0]
        chained = db.execute("SELECT type,state FROM tasks WHERE type='video_keyframes'").fetchone()
        untouched = db.execute("SELECT state FROM tasks WHERE id=2").fetchone()[0]
        metadata = db.execute("SELECT duration_sec,width,height,fps FROM assets WHERE id=1").fetchone()
        db.close()
        self.assertEqual(task, "finished")
        self.assertEqual(chained, ("video_keyframes", "pending"))
        self.assertEqual(untouched, "pending")
        self.assertEqual(metadata, (4.0, 640, 480, 30.0))

    def test_keyframes_are_published_atomically_and_enqueue_caption_and_embed(self):
        db = sqlite3.connect(self.db_path)
        db.execute("UPDATE assets SET duration_sec=4 WHERE id=1")
        db.execute("UPDATE tasks SET type='video_keyframes' WHERE id=1")
        db.commit(); db.close()

        def fake_run(args, *, output_dir=None, **kwargs):
            output_dir.joinpath("frame_00001.jpg").write_bytes(b"frame")
            return "", ""
        with patch.object(worker_module, "run_command", side_effect=fake_run):
            self.assertTrue(self.worker().run_once())
        published = self.derived / "video_frames" / "1" / "frame_00001.jpg"
        self.assertEqual(published.read_bytes(), b"frame")
        db = sqlite3.connect(self.db_path)
        self.assertEqual(db.execute("SELECT state FROM tasks WHERE id=1").fetchone()[0], "finished")
        self.assertEqual(set(db.execute("SELECT type FROM tasks WHERE id>2").fetchall()),
                         {("video_embed",), ("caption",)})
        db.close()

    def test_changed_source_is_retried_then_dead_without_leaking_path(self):
        self.source.write_bytes(b"changed")
        w = self.worker()
        for _ in range(3):
            w.run_once()
            db = sqlite3.connect(self.db_path)
            db.execute("UPDATE tasks SET scheduled_at=datetime('now') WHERE id=1")
            db.commit(); db.close()
        db = sqlite3.connect(self.db_path)
        state, error = db.execute("SELECT state,last_error FROM tasks WHERE id=1").fetchone()
        db.close()
        self.assertEqual(state, "dead")
        self.assertNotIn(str(self.source), error or "")
        self.assertEqual(error, "source_size_changed")

    def test_inactive_library_is_not_eligible(self):
        db = sqlite3.connect(self.db_path)
        db.execute("UPDATE access_libraries SET state='archived'")
        db.commit(); db.close()
        self.assertFalse(self.worker().run_once())
        db = sqlite3.connect(self.db_path)
        self.assertEqual(db.execute("SELECT state FROM tasks WHERE id=1").fetchone()[0], "pending")
        db.close()

    def test_mismatched_upload_provenance_is_not_eligible(self):
        db = sqlite3.connect(self.db_path)
        db.execute("UPDATE access_uploads SET bytes=bytes+1")
        db.commit(); db.close()
        self.assertFalse(self.worker().run_once())
        db = sqlite3.connect(self.db_path)
        self.assertEqual(db.execute("SELECT state FROM tasks WHERE id=1").fetchone()[0], "pending")
        db.close()

    def test_approval_revoked_during_probe_cannot_publish_or_finish(self):
        def revoke_during_probe(_args, **_kwargs):
            db = sqlite3.connect(self.db_path)
            db.execute("UPDATE access_uploads SET state='incoming' WHERE asset_id=1")
            db.commit(); db.close()
            return (json.dumps({"streams": [{"codec_type": "video", "width": 640,
                                               "height": 480, "duration": "4", "r_frame_rate": "30/1"}],
                                "format": {"duration": "4"}}), "")
        with patch.object(worker_module, "run_command", side_effect=revoke_during_probe):
            self.assertTrue(self.worker().run_once())
        db = sqlite3.connect(self.db_path)
        self.assertEqual(db.execute("SELECT state FROM tasks WHERE id=1").fetchone()[0], "pending")
        self.assertIsNone(db.execute("SELECT duration_sec FROM assets WHERE id=1").fetchone()[0])
        self.assertEqual(db.execute("SELECT count(*) FROM tasks WHERE type='video_keyframes'").fetchone()[0], 0)
        db.close()

    def test_final_hash_runs_before_sqlite_write_lock(self):
        db = sqlite3.connect(self.db_path)
        db.execute("UPDATE tasks SET state='running' WHERE id=1")
        db.commit(); db.close()
        candidate = self.worker()
        asset = candidate._asset(1)
        original = worker_module.verify_source
        def hash_while_write_is_available(*args, **kwargs):
            separate = sqlite3.connect(self.db_path, timeout=.1)
            separate.execute('BEGIN IMMEDIATE')
            separate.rollback(); separate.close()
            return original(*args, **kwargs)
        with patch.object(worker_module, 'verify_source', side_effect=hash_while_write_is_available):
            candidate._publish_guard(1, 1, asset, lambda _db, _asset: None)
        db = sqlite3.connect(self.db_path)
        self.assertEqual(db.execute('SELECT state FROM tasks WHERE id=1').fetchone()[0], 'finished')
        db.close()

    def test_source_changed_after_final_hash_cannot_publish(self):
        db = sqlite3.connect(self.db_path)
        db.execute("UPDATE tasks SET state='running' WHERE id=1")
        db.commit(); db.close()
        candidate = self.worker()
        asset = candidate._asset(1)
        original = worker_module.verify_source
        def change_after_hash(*args, **kwargs):
            result = original(*args, **kwargs)
            self.source.write_bytes(b'changed after hash')
            return result
        with patch.object(worker_module, 'verify_source', side_effect=change_after_hash):
            with self.assertRaisesRegex(worker_module.WorkerError, 'source_changed'):
                candidate._publish_guard(1, 1, asset, lambda _db, _asset: None)
        db = sqlite3.connect(self.db_path)
        self.assertEqual(db.execute('SELECT state FROM tasks WHERE id=1').fetchone()[0], 'running')
        db.close()

    def test_read_only_default_does_not_claim(self):
        with patch.object(worker_module, "ApprovedVideoWorker", return_value=type(
                'Fake', (), {'run': lambda self: (_ for _ in ()).throw(AssertionError('executed'))})()):
            with patch.object(worker_module, "_direct_existing", side_effect=lambda value, **_: value):
                self.assertEqual(worker_module.main([
                    '--database', str(self.db_path), '--derived-root', str(self.derived),
                    '--media-root', str(self.media), '--ffprobe', '/bin/true',
                    '--ffmpeg', '/bin/true']), 0)


if __name__ == "__main__":
    unittest.main()
