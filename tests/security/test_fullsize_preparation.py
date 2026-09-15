"""Copy-only, disk-backed preparation against disposable SQLite fixtures."""
from contextlib import closing, redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_access_database as small
import rehearse_fullsize_database as full


class FullsizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = sqlite3.connect(':memory:')
        small.upgrade_memory(cls.template)

    @classmethod
    def tearDownClass(cls):
        cls.template.close()

    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.source = self.root / 'source.sqlite'
        self.backup = self.root / 'snapshot.sqlite'
        self.candidate = self.root / 'candidate.sqlite'
        self.restored = self.root / 'restored.sqlite'
        with closing(sqlite3.connect(self.source)) as db:
            self.template.backup(db)
            db.execute("CREATE TABLE synthetic_payload(id INTEGER PRIMARY KEY, value BLOB)")
            db.execute("INSERT INTO synthetic_payload VALUES(1,x'00ff')")
            db.commit()
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def budget(self):
        return full.Budget(256 * 1024**2, 120)

    def snapshot(self):
        return full.snapshot(self.source, self.backup, self.budget())

    def test_wal_snapshot_contains_committed_rows_and_does_not_change_source(self):
        with closing(sqlite3.connect(self.source)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute("INSERT INTO synthetic_payload VALUES(2,x'1122')"); writer.commit()
            result = self.snapshot()
            self.assertEqual(writer.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            self.assertEqual(writer.execute('SELECT count(*) FROM synthetic_payload').fetchone()[0], 2)
        with closing(sqlite3.connect(self.backup)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM synthetic_payload').fetchone()[0], 2)
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'delete')
        self.assertFalse(result['suitable_for_cutover'])

    def test_live_writer_can_commit_after_snapshot_pin(self):
        with closing(sqlite3.connect(self.source)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            with full.read_source(self.source, self.budget()) as pinned:
                writer.execute("INSERT INTO synthetic_payload VALUES(2,x'11')"); writer.commit()
                self.assertEqual(pinned.execute('SELECT count(*) FROM synthetic_payload').fetchone()[0], 1)
            self.assertEqual(writer.execute('SELECT count(*) FROM synthetic_payload').fetchone()[0], 2)

    def test_rehearsal_quarantines_and_restores_without_source_edits(self):
        result = self.snapshot(); before = self.backup.read_bytes()
        with patch.dict(os.environ, {'DATABASE_URL': 'sqlite:////never-select-this.sqlite'}):
            proof = full.rehearse(self.backup, self.candidate, self.restored,
                                  result['snapshot_digest'], self.budget())
        self.assertTrue(proof['disk_restore_verified']); self.assertFalse(proof['suitable_for_cutover'])
        self.assertEqual(before, self.backup.read_bytes())
        with closing(sqlite3.connect(self.candidate)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM synthetic_payload').fetchone()[0], 1)

    def test_stale_review_refused_before_output(self):
        result = self.snapshot()
        with closing(sqlite3.connect(self.backup)) as db:
            db.execute("UPDATE synthetic_payload SET value=x'01'"); db.commit()
        with self.assertRaises(full.small.Refused):
            full.rehearse(self.backup, self.candidate, self.restored, result['snapshot_digest'], self.budget())
        self.assertFalse(self.candidate.exists())

    def test_pre_access_revision_migrates_and_preserves_original_columns(self):
        from sqlalchemy import create_engine
        from alembic import command
        old = self.root / 'old.sqlite'
        engine = create_engine('sqlite:///' + str(old))
        try:
            with engine.connect() as connection:
                config = small.migration_config(); config.attributes['connection'] = connection
                command.upgrade(config, 'd2b7e4f6a901')
            with closing(sqlite3.connect(old)) as db:
                db.execute("INSERT INTO assets(id,path,hash_sha256,status) VALUES(1,'synthetic.jpg','synthetic-hash','active')")
                db.commit()
            result = full.snapshot(old, self.backup, self.budget())
            proof = full.rehearse(self.backup, self.candidate, self.restored, result['snapshot_digest'], self.budget())
            self.assertEqual(proof['source_revision'], 'd2b7e4f6a901')
            self.assertEqual(proof['revision'], 'c7f4a9e2b610')
        finally: engine.dispose()

    def test_existing_owner_and_library_are_closed_without_changing_original(self):
        from app.access.bootstrap import bootstrap_owner
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            bootstrap_owner(db, phone='+12025550123', password='Synthetic test password only!', library_id='synthetic')
        result = self.snapshot()
        full.rehearse(self.backup, self.candidate, self.restored, result['snapshot_digest'], self.budget())
        with closing(sqlite3.connect(self.candidate)) as db:
            self.assertEqual(db.execute('SELECT state FROM access_accounts').fetchall(), [('disabled',)])
            self.assertEqual(db.execute('SELECT state FROM access_libraries').fetchall(), [('closed',)])
        with closing(sqlite3.connect(self.source)) as db:
            self.assertEqual(db.execute('SELECT state FROM access_accounts').fetchall(), [('active',)])

    def test_migration_corruption_is_detected_and_partial_copy_retained(self):
        result = self.snapshot()
        actual = full.upgrade_copy
        def corrupted(db, budget):
            actual(db, budget)
            db.execute('DELETE FROM synthetic_payload'); db.commit()
        with patch.object(full, 'upgrade_copy', side_effect=corrupted):
            with self.assertRaises(small.Refused):
                full.rehearse(self.backup, self.candidate, self.restored, result['snapshot_digest'], self.budget())
        self.assertTrue(self.candidate.exists()); self.assertFalse(self.restored.exists())

    def test_existing_output_and_source_as_output_are_preserved(self):
        before = self.source.read_bytes()
        with self.assertRaises(FileExistsError):
            full.snapshot(self.source, self.source, self.budget())
        self.assertEqual(before, self.source.read_bytes())

    def test_offline_rehearsal_refuses_wal(self):
        result = self.snapshot()
        with closing(sqlite3.connect(self.backup)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            with self.assertRaises(small.Refused):
                full.rehearse(self.backup, self.candidate, self.restored, result['snapshot_digest'], self.budget())

    def test_timeout_and_size_limits(self):
        budget = self.budget(); budget.deadline = 0
        with self.assertRaises(small.Refused): full.snapshot(self.source, self.backup, budget)
        budget = self.budget(); budget.max_bytes = 1
        with self.assertRaises(small.Refused): full.snapshot(self.source, self.backup, budget)
        self.assertFalse(self.backup.exists())

    def test_low_disk_space_refuses_before_output(self):
        usage = type('Usage', (), {'free': 1})()
        with patch.object(full.shutil, 'disk_usage', return_value=usage):
            with self.assertRaises(small.Refused): self.snapshot()
        self.assertFalse(self.backup.exists())

    def test_symlink_target_refused(self):
        try: self.backup.symlink_to(self.source)
        except OSError: self.skipTest('Symlink privilege unavailable')
        with self.assertRaises((small.Refused, FileExistsError)): self.snapshot()

    def test_over_64_mib_is_disk_backed(self):
        with closing(sqlite3.connect(self.source)) as db:
            for item in range(2, 68):
                db.execute('INSERT INTO synthetic_payload VALUES(?,zeroblob(1048576))', (item,))
            db.commit()
        self.assertGreater(self.source.stat().st_size, small.MAX_DATABASE_BYTES)
        result = self.snapshot()
        proof = full.rehearse(self.backup, self.candidate, self.restored, result['snapshot_digest'], self.budget())
        self.assertTrue(proof['disk_restore_verified'])

    def test_cli_sanitizes_failures(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = full.main(['snapshot', '--database', str(self.root/'private-missing.sqlite'),
                '--out', str(self.backup), '--max-bytes', '104857600', '--timeout-seconds', '30'])
        self.assertEqual(status, 2)
        self.assertNotIn(str(self.root), out.getvalue()+err.getvalue())


if __name__ == '__main__': unittest.main()
