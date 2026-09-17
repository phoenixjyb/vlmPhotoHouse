"""Offline supervisor validation; no host services, GPU or private input."""
from contextlib import closing, nullcontext
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import build_caption_worker_package as package
import supervise_caption_worker as supervisor


class CaptionSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root/'source'
        data = package.package_bytes('a'*40, {name: (ROOT/name).read_bytes() for name in package.FILES})
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive.extractall(self.source)
        self.db = self.root/'catalog.sqlite'
        with closing(sqlite3.connect(self.db)) as db:
            db.executescript("CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES ('f2a6d8b4c915'); CREATE TABLE tasks(type TEXT,state TEXT);")
        for name in ('derived', 'temporary', 'receipts'):
            (self.root/name).mkdir()
        self.environment = self.root/'environment.json'
        self.environment.write_text('{"CAPTION_HTTP_MAX_IMAGE_EDGE":"1536"}')
        self.path = self.root/'supervisor.json'
        self.config = dict(format_version=1, worker_root=str(self.source), worker_commit='a'*40,
            manifest_sha256=hashlib.sha256((self.source/'manifest.json').read_bytes()).hexdigest(),
            database=str(self.db), expected_revision='f2a6d8b4c915', derived=str(self.root/'derived'),
            temporary=str(self.root/'temporary'), stop_file=str(self.root/'stop'),
            caption_url='http://127.0.0.1:1', environment_json=str(self.environment),
            environment_sha256=hashlib.sha256(self.environment.read_bytes()).hexdigest(),
            receipt_directory=str(self.root/'receipts'))
        self.save()
        # Simulate the dedicated process; unrelated suites may have imported app.
        self.modules = patch.dict(sys.modules)
        self.modules.start(); self.addCleanup(self.modules.stop)
        for name in list(sys.modules):
            if name == 'app' or name.startswith('app.'):
                del sys.modules[name]

    def save(self):
        self.path.write_text(json.dumps(self.config))
        self.sha = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def args(self, **overrides):
        return supervisor.argparse.Namespace(config=str(self.path), config_sha256=self.sha,
            **dict({'execute': False, 'writers_fenced': False, 'once': False}, **overrides))

    def test_preflight_no_external_io_writes_or_application_imports(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('socket.socket.connect', side_effect=AssertionError('No network')), \
             patch('subprocess.Popen', side_effect=AssertionError('No process')), \
             patch.object(supervisor, 'receipt', side_effect=AssertionError('No receipts')):
            result = supervisor.supervise(self.args())
        self.assertEqual(result, {'supervisor': 'preflight-pass', 'activated': False, 'revision': 'f2a6d8b4c915'})
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(any(n == 'app' or n.startswith('app.') for n in sys.modules))

    def test_explicit_revision_and_running_work_refuse_without_repair(self):
        for kind, state in (('caption', 'running'), ('face', 'pending'), ('embed', 'running')):
            with closing(sqlite3.connect(self.db)) as db:
                db.execute('DELETE FROM tasks')
                db.execute('INSERT INTO tasks VALUES (?,?)', (kind, state)); db.commit()
            before = self.db.read_bytes()
            with self.assertRaises(ValueError): supervisor.supervise(self.args())
            self.assertEqual(before, self.db.read_bytes())
        self.config['expected_revision'] = 'd2b7e4f6a901'; self.save()
        with self.assertRaises(ValueError): supervisor.supervise(self.args())

    def test_finished_other_work_does_not_block(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO tasks VALUES ('face','finished')"); db.commit()
        self.assertFalse(supervisor.supervise(self.args())['activated'])

    def test_config_and_policy_hash_pins(self):
        self.path.write_text(self.path.read_text()+' ')
        with self.assertRaises(ValueError): supervisor.supervise(self.args())
        self.save()
        self.environment.write_text('{}')
        with self.assertRaises(ValueError): supervisor.supervise(self.args())

    def test_manifest_and_source_hash_pins(self):
        manifest = self.source/'manifest.json'
        original = manifest.read_bytes()
        manifest.write_bytes(original+b' ')
        with self.assertRaises(ValueError): supervisor.supervise(self.args())
        manifest.write_bytes(original)
        (self.source/'scripts/run_caption_worker.py').write_text('raise AssertionError("must not execute")')
        with self.assertRaises(ValueError): supervisor.supervise(self.args())

    def test_unmanifested_source_and_bytecode_refused(self):
        for name in ('.env', 'backend/app/extra.py', 'backend/app/extra.pyc'):
            path = self.source/name; path.write_text('unreviewed')
            with self.assertRaises(ValueError): supervisor.supervise(self.args())
            path.unlink()

    def test_retained_stop_refuses_even_preflight(self):
        stop = self.root/'stop'; stop.touch()
        with self.assertRaises(ValueError): supervisor.supervise(self.args())
        self.assertTrue(stop.exists())
        self.assertEqual(list((self.root/'receipts').iterdir()), [])

    def test_alias_and_overlap_refused(self):
        alias = self.root/'alias'; alias.symlink_to(self.environment)
        self.config['environment_json'] = str(alias); self.save()
        with self.assertRaises(ValueError): supervisor.supervise(self.args())
        self.config['environment_json'] = str(self.environment)
        self.config['receipt_directory'] = str(self.root/'derived'); self.save()
        with self.assertRaises(ValueError): supervisor.supervise(self.args())

    def test_schema_and_config_errors_are_sanitized(self):
        for raw in ('{"secret":"never-echo-this"}', '{"format_version":1,"format_version":1}', 'invalid-private-value'):
            self.path.write_text(raw)
            sha = hashlib.sha256(self.path.read_bytes()).hexdigest()
            out = io.StringIO()
            with patch('sys.stderr', out):
                code = supervisor.main(['--config', str(self.path), '--config-sha256', sha])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(out.getvalue()), {'supervisor': 'refused-or-interrupted', 'clean_drain_confirmed': False})

    def test_execute_requires_independent_fencing_assertion(self):
        with self.assertRaises(ValueError): supervisor.supervise(self.args(execute=True))
        self.assertEqual(list((self.root/'receipts').iterdir()), [])

    def test_output_discard_covers_python_and_native_writes(self):
        code = ('import sys,os; sys.path.insert(0,sys.argv[1]); '
                'from supervise_caption_worker import private_output\n'
                'with private_output():\n print("private"); os.write(1,b"native"); os.write(2,b"error")\n'
                'print("safe")')
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(ROOT/'scripts')],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'safe\n'); self.assertEqual(result.stderr, '')

    def test_single_run_sanitized_receipts_and_no_restart(self):
        config, worker, args = supervisor.prepare(str(self.path), self.sha)
        result = {'worker': 'stopped', 'drained': True, 'claimed_tasks_processed': 1}
        with patch.object(supervisor, 'prepare', return_value=(config, worker, args)) as prepare, \
             patch.object(worker, 'run', return_value=result) as run, \
             patch.object(supervisor, 'private_output', return_value=nullcontext()):
            outcome = supervisor.supervise(self.args(execute=True, writers_fenced=True))
        self.assertTrue(outcome['clean_drain_confirmed'])
        self.assertEqual(prepare.call_count, 2); run.assert_called_once()
        self.assertTrue(args.execute and args.legacy_worker_stopped)
        files = list((self.root/'receipts').iterdir()); self.assertEqual(len(files), 2)
        for path in files:
            self.assertLess(path.stat().st_size, 2048)
            self.assertNotIn(str(self.root), path.read_text())

    def test_error_result_never_claims_drain_or_restarts(self):
        config, worker, args = supervisor.prepare(str(self.path), self.sha)
        with patch.object(supervisor, 'prepare', return_value=(config, worker, args)), \
             patch.object(worker, 'run', side_effect=RuntimeError('private-value')) as run, \
             patch.object(supervisor, 'private_output', return_value=nullcontext()):
            outcome = supervisor.supervise(self.args(execute=True, writers_fenced=True))
        self.assertFalse(outcome['clean_drain_confirmed']); run.assert_called_once()
        for path in (self.root/'receipts').iterdir(): self.assertNotIn('private-value', path.read_text())

    def test_receipt_failure_before_start_never_runs_worker(self):
        config, worker, args = supervisor.prepare(str(self.path), self.sha)
        with patch.object(supervisor, 'prepare', return_value=(config, worker, args)), \
             patch.object(supervisor, 'receipt', side_effect=OSError('fixture')), \
             patch.object(worker, 'run') as run:
            with self.assertRaises(OSError): supervisor.supervise(self.args(execute=True, writers_fenced=True))
        run.assert_not_called()

    @unittest.skipUnless(all(importlib.util.find_spec(name) for name in
        ('numpy', 'imagehash', 'exifread', 'prometheus_client')),
        'Separate legacy test dependencies required')
    def test_actual_packaged_runner_under_supervisor(self):
        for mode in ('drain', 'edited', 'retry', 'idle', 'unready', 'unconfirmed', 'tags'):
            with self.subTest(mode=mode):
                result = subprocess.run([sys.executable, '-I', '-B',
                    str(ROOT/'tests/security/caption_worker_fixture.py'), str(self.source),
                    str(self.root/mode), mode, str(ROOT), str(ROOT/'scripts/supervise_caption_worker.py')],
                    capture_output=True, text=True, timeout=40)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertIn('"fixture": "pass"', result.stdout)


if __name__ == '__main__':
    unittest.main()
