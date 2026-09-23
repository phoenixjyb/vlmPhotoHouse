"""Standalone lifecycle tests; no legacy API, media, model or live database."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('caption_worker_launcher', ROOT/'scripts/run_caption_worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class CaptionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.db = self.root/'catalog.sqlite'
        with closing(sqlite3.connect(self.db)) as db:
            db.executescript("CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES ('c7f4a9e2b610'); CREATE TABLE tasks(type TEXT,state TEXT);")

    def test_preflight_read_only_without_application_imports(self):
        before = self.db.read_bytes()
        with patch.dict(sys.modules, {'app.tasks': None, 'app.main': None}):
            self.assertEqual(worker.preflight(self.db, 'c7f4a9e2b610')['preflight'], 'pass')
        self.assertEqual(before, self.db.read_bytes())

    def test_missing_database_not_created(self):
        missing = self.root/'missing.sqlite'
        with self.assertRaises((OSError, worker.Refused)):
            worker.preflight(missing, 'c7f4a9e2b610')
        self.assertFalse(missing.exists())

    def test_execution_connection_enforces_foreign_keys_and_existing_file(self):
        with closing(worker.connect_existing(self.db)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone(), (1,))
        missing = self.root/'missing.sqlite'
        with self.assertRaises(sqlite3.OperationalError): worker.connect_existing(missing)
        self.assertFalse(missing.exists())

    def test_default_run_does_not_configure_process_or_create_lock(self):
        path = self.root/'reviewed.json'; path.write_text('{}')
        args = worker.argparse.Namespace(database=str(self.db), derived=str(self.root),
            temporary=str(self.root), stop_file=str(self.root/'stop'), caption_url='http://127.0.0.1:1',
            environment_json=str(path), expected_revision='c7f4a9e2b610', execute=False)
        with patch.object(worker, 'configure_process', side_effect=AssertionError('No runtime')):
            self.assertEqual(worker.run(args)['preflight'], 'pass')
        self.assertFalse(Path(str(self.db)+'.caption-worker.lock').exists())

    def test_revision_mismatch_refuses(self):
        with self.assertRaises(worker.Refused):
            worker.preflight(self.db, 'd2b7e4f6a901')

    def test_each_supported_revision_requires_exact_read_only_selection(self):
        revisions = ('d2b7e4f6a901', 'c7f4a9e2b610', 'd8e5b2f7a904', 'f2a6d8b4c915', 'a8d4c2e6f901')
        self.assertEqual(worker.REVISIONS, revisions)
        for actual in revisions:
            with closing(sqlite3.connect(self.db)) as db:
                db.execute('UPDATE alembic_version SET version_num=?', (actual,))
                db.commit()
            before = self.db.read_bytes()
            for selected in revisions:
                with self.subTest(actual=actual, selected=selected):
                    if actual == selected:
                        result = worker.preflight(self.db, selected)
                        self.assertEqual(result['revision'], actual)
                        self.assertFalse(result['activated'])
                    else:
                        with self.assertRaises(worker.Refused):
                            worker.preflight(self.db, selected)
                    self.assertEqual(before, self.db.read_bytes())

    def test_migrated_schema_does_not_bypass_running_caption_gate(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE alembic_version SET version_num='f2a6d8b4c915'")
            db.execute("INSERT INTO tasks VALUES ('caption','running')")
            db.commit()
        before = self.db.read_bytes()
        with self.assertRaises(worker.Refused):
            worker.preflight(self.db, 'f2a6d8b4c915')
        self.assertEqual(before, self.db.read_bytes())

    def test_unknown_revision_refuses(self):
        with self.assertRaises(worker.Refused):
            worker.preflight(self.db, 'unknown')

    def test_running_caption_refuses_without_repair(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO tasks VALUES ('caption','running')"); db.commit()
        before = self.db.read_bytes()
        with self.assertRaises(worker.Refused):
            worker.preflight(self.db, 'c7f4a9e2b610')
        self.assertEqual(before, self.db.read_bytes())

    def test_other_running_task_does_not_claim_caption_ownership(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO tasks VALUES ('video_embed','running')"); db.commit()
        worker.preflight(self.db, 'c7f4a9e2b610')

    def test_url_is_explicit_loopback_without_credentials(self):
        self.assertEqual(worker.caption_url('http://127.0.0.1:8102/'), 'http://127.0.0.1:8102')
        for url in ('http://example.com:80', 'http://127.0.0.1', 'http://user:secret@127.0.0.1:80',
                    'http://127.0.0.1:80/path', 'http://127.0.0.1:80?x=1'):
            with self.subTest(url=url), self.assertRaises(worker.Refused): worker.caption_url(url)

    def test_reviewed_settings_refuse_unknown_duplicate_and_nonfinite(self):
        path = self.root/'env.json'
        for raw in ('{"CAPTION_PROVIDER":"stub"}', '{"CAPTION_WORD_LIMIT":"0","CAPTION_WORD_LIMIT":"1"}',
                    '{"CAPTION_HTTP_TIMEOUT_SEC":"nan"}', '{"CAPTION_HTTP_RETRIES":"0"}',
                    '{"CAPTION_AUTO_TAG_ENABLE":"yes"}',
                    '{"CAPTION_WORD_LIMIT":0}'):
            path.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(worker.Refused): worker.reviewed_environment(path)
        path.write_text('{"CAPTION_WORD_LIMIT":"0"}')
        self.assertEqual(worker.reviewed_environment(path), {'CAPTION_WORD_LIMIT':'0'})
        path.write_text('{"CAPTION_AUTO_TAG_ENABLE":"true"}')
        self.assertEqual(worker.reviewed_environment(path), {'CAPTION_AUTO_TAG_ENABLE':'true'})

    def test_lock_excludes_second_worker_and_releases_on_exception(self):
        with self.assertRaisesRegex(RuntimeError, 'fixture'):
            with worker.worker_lock(self.db):
                with self.assertRaises(worker.Refused):
                    with worker.worker_lock(self.db): pass
                raise RuntimeError('fixture')
        with worker.worker_lock(self.db): pass
        self.assertTrue(Path(str(self.db)+'.caption-worker.lock').exists())

    def test_stop_before_start_claims_nothing(self):
        executor = Mock()
        stop = threading.Event(); stop.set()
        self.assertEqual(worker.drain_loop(executor, stop, self.root/'stop'), 0)
        executor.run_once.assert_not_called()

    def test_stop_file_claims_nothing(self):
        stopfile = self.root/'stop'; stopfile.touch()
        executor = Mock()
        self.assertEqual(worker.drain_loop(executor, threading.Event(), stopfile), 0)
        executor.run_once.assert_not_called()

    def test_stop_arriving_at_lock_acquisition_prevents_configuration(self):
        from contextlib import contextmanager
        path = self.root/'reviewed.json'; path.write_text('{}')
        stopfile = self.root/'stop'
        args = worker.argparse.Namespace(database=str(self.db), derived=str(self.root),
            temporary=str(self.root), stop_file=str(stopfile), caption_url='http://127.0.0.1:1',
            environment_json=str(path), expected_revision='c7f4a9e2b610', execute=True,
            legacy_worker_stopped=True, once=False)
        @contextmanager
        def arriving_stop(database):
            stopfile.touch()
            yield
        with patch.object(worker, 'worker_lock', side_effect=arriving_stop), \
             patch.object(worker, 'configure_process') as configure:
            with self.assertRaises(worker.Refused): worker.run(args)
        configure.assert_not_called()
        self.assertTrue(stopfile.exists())

    def test_stop_drains_inflight_before_return_and_no_next_claim(self):
        entered, finish, stop = threading.Event(), threading.Event(), threading.Event()
        def run_once():
            entered.set(); self.assertTrue(finish.wait(5)); return True
        executor = Mock(run_once=Mock(side_effect=run_once))
        result = []
        thread = threading.Thread(target=lambda: result.append(worker.drain_loop(executor, stop, self.root/'stop')))
        thread.start()
        try:
            self.assertTrue(entered.wait(5)); stop.set()
            self.assertTrue(thread.is_alive())
        finally:
            finish.set(); thread.join(5)
        self.assertFalse(thread.is_alive()); self.assertEqual(result, [1])
        executor.run_once.assert_called_once()

    def test_once_and_idle_do_not_spin(self):
        executor = Mock(run_once=Mock(return_value=False))
        self.assertEqual(worker.drain_loop(executor, threading.Event(), self.root/'stop', once=True), 0)
        executor.run_once.assert_called_once()

    def test_unhandled_database_error_does_not_report_drained(self):
        executor = Mock(run_once=Mock(side_effect=sqlite3.OperationalError('fixture')))
        with self.assertRaises(sqlite3.OperationalError):
            worker.drain_loop(executor, threading.Event(), self.root/'stop')

    @unittest.skipUnless(all(importlib.util.find_spec(name) for name in
        ('numpy', 'imagehash', 'exifread', 'prometheus_client')),
        'Requires separate legacy worker test dependencies; protected runtime stays CPU-minimal')
    def test_actual_runner_queue_handler_and_drain_in_fresh_process(self):
        for mode in ('drain', 'edited', 'retry', 'idle', 'unready', 'unconfirmed', 'tags'):
            with self.subTest(mode=mode):
                result = subprocess.run([sys.executable, '-I', str(ROOT/'tests/security/caption_worker_fixture.py'),
                    str(ROOT), str(self.root/mode), mode], capture_output=True, text=True, timeout=40)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertIn('"fixture": "pass"', result.stdout)
