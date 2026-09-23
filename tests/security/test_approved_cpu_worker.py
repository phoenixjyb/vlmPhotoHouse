import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_approved_cpu_worker as worker


class ApprovedCpuWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.originals = self.root / 'originals'; self.originals.mkdir()
        self.derived = self.root / 'derived'; self.derived.mkdir()
        self.dbpath = self.root / 'catalog.sqlite'
        self.stop = self.root / 'stop.flag'
        self.source = self.originals / 'synthetic.png'
        Image.new('RGB', (48, 32), (24, 100, 180)).save(self.source)
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.db = sqlite3.connect(self.dbpath)
        self.db.executescript('''
          CREATE TABLE alembic_version(version_num TEXT NOT NULL);
          INSERT INTO alembic_version VALUES ('a8d4c2e6f901');
          CREATE TABLE assets(id INTEGER PRIMARY KEY,path TEXT,file_size INTEGER,hash_sha256 TEXT,
            mime TEXT,status TEXT,perceptual_hash TEXT);
          CREATE TABLE access_uploads(asset_id INTEGER,state TEXT,sha256 TEXT,bytes INTEGER);
          CREATE TABLE access_asset_libraries(asset_id INTEGER,library_id TEXT);
          CREATE TABLE access_libraries(id TEXT,state TEXT);
          CREATE TABLE tasks(id INTEGER PRIMARY KEY,type TEXT,state TEXT,payload_json TEXT,
            retry_count INTEGER DEFAULT 0,cancel_requested INTEGER DEFAULT 0,scheduled_at TEXT,
            started_at TEXT,finished_at TEXT,last_error TEXT,priority INTEGER DEFAULT 80);
        ''')
        self.db.execute("INSERT INTO assets VALUES (1,?,?,?,?,?,NULL)",
                        (str(self.source), self.source.stat().st_size, self.digest, 'image/png', 'active'))
        self.db.execute("INSERT INTO access_uploads VALUES (1,'assigned',?,?)",
                        (self.digest, self.source.stat().st_size))
        self.db.execute("INSERT INTO access_libraries VALUES ('family','active')")
        self.db.execute("INSERT INTO access_asset_libraries VALUES (1,'family')")
        self.db.commit()

    def tearDown(self):
        self.db.close(); self.tmp.cleanup()

    def task(self, kind, state='pending', payload=None):
        self.db.execute('INSERT INTO tasks(type,state,payload_json,scheduled_at) VALUES (?,?,?,CURRENT_TIMESTAMP)',
                        (kind, state, json.dumps(payload or {'asset_id': 1}, sort_keys=True)))
        self.db.commit()
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    def args(self, execute=False, once=True):
        return type('Args', (), {'database': str(self.dbpath), 'originals_root': str(self.originals),
            'derived_root': str(self.derived), 'stop_file': str(self.stop), 'execute': execute, 'once': once})()

    def run_cpu_worker(self, args):
        # The isolated CI/mac fixture may have less than the production 8 GiB
        # floor; production keeps the default. Child RSS sampling remains active.
        with patch.object(worker, 'MIN_FREE_RAM', 0):
            return worker.run(args)

    def test_default_preflight_is_read_only_and_counts_only_approved_mappable_rows(self):
        self.task('thumb')
        self.db.execute("UPDATE access_uploads SET state='incoming'"); self.db.commit()
        before = self.db.execute('SELECT state FROM tasks').fetchone()
        result = worker.run(self.args())
        self.assertEqual(result['approved_claimable'], 0)
        self.assertFalse(result['activated'])
        self.assertEqual(self.db.execute('SELECT state FROM tasks').fetchone(), before)

    def test_claim_rejects_unapproved_and_bad_payload(self):
        self.task('thumb')
        self.db.execute("UPDATE access_uploads SET state='incoming'"); self.db.commit()
        self.assertIsNone(worker.claim_one(self.dbpath))
        self.db.execute("UPDATE access_uploads SET state='assigned'")
        self.db.execute('UPDATE tasks SET payload_json=?', ('{"asset_id":2}',)); self.db.commit()
        self.assertIsNone(worker.claim_one(self.dbpath))
        self.assertEqual(self.db.execute('SELECT state FROM tasks').fetchone()[0], 'pending')

    def test_thumb_runs_bounded_child_and_publishes_expected_variants(self):
        self.task('thumb')
        result = self.run_cpu_worker(self.args(execute=True))
        self.assertEqual(result['completed'], 1)
        for size in ('256', '1024'):
            target = self.derived / 'thumbnails' / size / '1.jpg'
            self.assertTrue(target.is_file())
            with Image.open(target) as image:
                self.assertEqual(image.format, 'JPEG')
                self.assertLessEqual(max(image.size), int(size))
        self.assertEqual(self.db.execute('SELECT state FROM tasks').fetchone()[0], 'finished')

    def test_phash_commits_only_after_verified_source(self):
        self.task('phash')
        result = self.run_cpu_worker(self.args(execute=True))
        self.assertEqual(result['completed'], 1)
        value = self.db.execute('SELECT perceptual_hash FROM assets WHERE id=1').fetchone()[0]
        self.assertEqual(len(value), 16)
        self.assertEqual(self.db.execute('SELECT state FROM tasks').fetchone()[0], 'finished')

    def test_source_hash_mismatch_is_visible_and_never_finished(self):
        self.task('phash')
        original = self.source.read_bytes()
        self.source.write_bytes(bytes([original[0] ^ 0xff]) + original[1:])
        result = self.run_cpu_worker(self.args(execute=True))
        self.assertEqual(result['completed'], 0)
        row = self.db.execute('SELECT state,retry_count,last_error FROM tasks').fetchone()
        self.assertEqual(row[0], 'pending')
        self.assertEqual(row[1], 1)
        self.assertEqual(row[2], 'input_or_output_validation')

    def test_inactive_library_is_not_claimed(self):
        self.task('thumb')
        self.db.execute("UPDATE access_libraries SET state='closed'"); self.db.commit()
        self.assertIsNone(worker.claim_one(self.dbpath))

    def test_changed_upload_receipt_or_multiple_libraries_are_not_claimed(self):
        self.task('thumb')
        self.db.execute("UPDATE access_uploads SET sha256='wrong'"); self.db.commit()
        self.assertIsNone(worker.claim_one(self.dbpath))
        self.db.execute("UPDATE access_uploads SET sha256=?", (self.digest,))
        self.db.execute("INSERT INTO access_libraries VALUES ('other','active')")
        self.db.execute("INSERT INTO access_asset_libraries VALUES (1,'other')")
        self.db.commit()
        self.assertIsNone(worker.claim_one(self.dbpath))

    def test_current_live_schema_revision_is_required(self):
        self.assertEqual(worker.REVISIONS, {'a8d4c2e6f901'})
        self.assertEqual(worker.preflight(self.dbpath, self.originals, self.derived, self.stop)['preflight'], 'pass')

    def test_execute_polls_idle_queue_until_stop_file(self):
        calls = []
        def no_job(_database):
            calls.append(1)
            if len(calls) == 2:
                self.stop.touch()
            return None
        with patch.object(worker, 'claim_one', side_effect=no_job), patch.object(worker.time, 'sleep') as pause:
            result = self.run_cpu_worker(self.args(execute=True, once=False))
        self.assertEqual(len(calls), 2)
        self.assertEqual(pause.call_count, 1)
        self.assertEqual(result['attempted'], 0)
        self.assertTrue(result['stopped_by_operator'])

    def test_once_exits_on_idle_queue(self):
        with patch.object(worker, 'claim_one', return_value=None), patch.object(worker.time, 'sleep') as pause:
            result = worker.run(self.args(execute=True))
        self.assertEqual(result['attempted'], 0)
        pause.assert_not_called()

    def test_resource_guard_enforces_free_ram_floor_and_child_rss_cap(self):
        with patch.object(worker.sys, 'platform', 'linux'), \
             patch.object(worker.shutil, 'disk_usage', return_value=SimpleNamespace(free=1024**3)), \
             patch.object(worker.Path, 'read_text', side_effect=['MemAvailable: 7000000 kB', 'VmRSS: 10 kB']):
            with self.assertRaisesRegex(RuntimeError, 'memory_budget'):
                worker._guard_resources(self.derived, self.stop, SimpleNamespace(pid=123), float('inf'))

        with patch.object(worker.sys, 'platform', 'linux'), \
             patch.object(worker.shutil, 'disk_usage', return_value=SimpleNamespace(free=1024**3)), \
             patch.object(worker.Path, 'read_text', side_effect=['MemAvailable: 9000000 kB', 'VmRSS: 2000000 kB']):
            with self.assertRaisesRegex(RuntimeError, 'memory_budget'):
                worker._guard_resources(self.derived, self.stop, SimpleNamespace(pid=123), float('inf'))


if __name__ == '__main__':
    unittest.main()
