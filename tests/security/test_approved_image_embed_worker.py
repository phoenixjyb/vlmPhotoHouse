import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_approved_image_embed_worker as worker


class ApprovedImageEmbedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.originals = self.root / 'originals'; self.originals.mkdir()
        self.derived = self.root / 'derived'; self.derived.mkdir()
        self.dbpath = self.root / 'catalog.sqlite'
        self.source = self.originals / 'synthetic.png'
        Image.new('RGB', (48, 32), (20, 80, 140)).save(self.source)
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.db = sqlite3.connect(self.dbpath)
        self.db.executescript('''
          CREATE TABLE alembic_version(version_num TEXT NOT NULL);
          INSERT INTO alembic_version VALUES ('a8d4c2e6f901');
          CREATE TABLE assets(id INTEGER PRIMARY KEY,path TEXT,file_size INTEGER,hash_sha256 TEXT,
            mime TEXT,status TEXT);
          CREATE TABLE access_uploads(asset_id INTEGER,state TEXT,sha256 TEXT,bytes INTEGER);
          CREATE TABLE access_asset_libraries(asset_id INTEGER,library_id TEXT);
          CREATE TABLE access_libraries(id TEXT,state TEXT);
          CREATE TABLE tasks(id INTEGER PRIMARY KEY,type TEXT,state TEXT,payload_json TEXT,
            retry_count INTEGER DEFAULT 0,cancel_requested INTEGER DEFAULT 0,scheduled_at TEXT,
            started_at TEXT,finished_at TEXT,last_error TEXT,priority INTEGER DEFAULT 80);
          CREATE TABLE embeddings(asset_id INTEGER,modality TEXT,model TEXT,dim INTEGER,
            storage_path TEXT,vector_checksum TEXT,device TEXT,model_version TEXT);
        ''')
        size = self.source.stat().st_size
        self.db.execute('INSERT INTO assets VALUES (1,?,?,?,?,?)',
                        (str(self.source), size, self.digest, 'image/png', 'active'))
        self.db.execute("INSERT INTO access_uploads VALUES (1,'assigned',?,?)", (self.digest, size))
        self.db.execute("INSERT INTO access_libraries VALUES ('family','active')")
        self.db.execute("INSERT INTO access_asset_libraries VALUES (1,'family')")
        self.db.commit()
        self.stop = self.root / 'stop.flag'
        self.checkpoint = self.root / 'local.ckpt'
        self.checkpoint.write_bytes(b'synthetic checkpoint identity')
        self.checksum = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()

    def tearDown(self):
        self.db.close(); self.tmp.cleanup()

    def task(self, kind='embed', payload=None):
        self.db.execute('INSERT INTO tasks(type,state,payload_json,scheduled_at) VALUES (?,?,?,CURRENT_TIMESTAMP)',
                        (kind, 'pending', json.dumps(payload or {'asset_id': 1, 'modality': 'image'})))
        self.db.commit()
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    def candidate(self, task_id):
        with worker.closing(worker._sqlite(self.dbpath)) as db:
            return worker.matching_candidates(db)[0]

    def args(self):
        return type('Args', (), {'database': str(self.dbpath), 'originals_root': str(self.originals),
            'derived_root': str(self.derived), 'checkpoint': str(self.checkpoint),
            'checkpoint_sha256': self.checksum, 'image_model': 'clip-vit-b32',
            'model_version': 'synthetic-v1', 'device': 'cpu', 'stop_file': str(self.stop),
            'expected_gpu_uuid': None,
            'execute': True, 'once': True})()

    def test_preflight_is_read_only_and_requires_exact_approved_image_payload(self):
        self.task('thumb')
        self.task('embed', {'asset_id': 1, 'modality': 'legacy'})
        self.task('embed', {'asset_id': 1, 'modality': 'image'})
        before = self.db.execute('SELECT id,state FROM tasks ORDER BY id').fetchall()
        with patch.object(worker, '_probe_provider', return_value={
                'effective_provider': 'open_clip', 'effective_device': 'cpu',
                'selected_physical_device': 'cpu', 'selected_gpu_uuid': None}):
            args = self.args(); args.execute = False
            result = worker.run(args)
        self.assertEqual(result['approved_claimable'], 1)
        self.assertEqual(result['skipped_due_embed'], 1)
        self.assertFalse(result['activated'])
        self.assertEqual(before, self.db.execute('SELECT id,state FROM tasks ORDER BY id').fetchall())

    def test_incoming_upload_and_bad_payload_are_refused_before_claim(self):
        task_id = self.task()
        self.db.execute("UPDATE access_uploads SET state='incoming'"); self.db.commit()
        self.assertIsNone(worker._claim_one(self.dbpath))
        self.assertEqual(self.db.execute('SELECT state FROM tasks WHERE id=?', (task_id,)).fetchone()[0], 'pending')
        self.db.execute("UPDATE access_uploads SET state='assigned'")
        self.db.execute('UPDATE tasks SET payload_json=? WHERE id=?', ('{"asset_id":1}', task_id)); self.db.commit()
        self.assertIsNone(worker._claim_one(self.dbpath))
        self.assertEqual(self.db.execute('SELECT state FROM tasks WHERE id=?', (task_id,)).fetchone()[0], 'pending')

    def test_claim_ignores_unrelated_job_types(self):
        self.task('thumb')
        self.assertIsNone(worker._claim_one(self.dbpath))
        self.assertEqual(self.db.execute('SELECT state FROM tasks').fetchone()[0], 'pending')

    def test_synthetic_approved_image_commits_vector_and_task_atomically(self):
        task_id = self.task()
        candidate = worker._claim_one(self.dbpath)
        self.assertEqual(candidate['task_id'], task_id)
        args = self.args()

        def fake_decode(source, stage, derived, deadline, stop_file):
            target = stage / '1024.jpg'
            Image.new('RGB', (32, 32), (100, 20, 30)).save(target)
            return target

        def fake_embed(image, stage, args, checkpoint, deadline):
            vector = np.array([0.25, 0.5, 0.75], dtype=np.float32)
            target = stage / 'vector.npy'
            with target.open('wb') as stream:
                np.save(stream, vector, allow_pickle=False)
            meta = {'provider': 'open_clip', 'effective_device': 'cpu', 'dimension': 3,
                    'model_version': args.model_version}
            return vector, meta, hashlib.sha256(target.read_bytes()).hexdigest()

        with patch.object(worker, '_run_bounded_decoder', side_effect=fake_decode), \
             patch.object(worker, '_run_embed_child', side_effect=fake_embed):
            completed = worker._process_task(candidate, self.dbpath, self.originals,
                self.derived, args, self.checkpoint, worker.identity(self.checkpoint), self.stop)
        self.assertTrue(completed)
        row = self.db.execute('SELECT state FROM tasks WHERE id=?', (task_id,)).fetchone()
        self.assertEqual(row[0], 'finished')
        embedding = self.db.execute('SELECT asset_id,modality,dim,device FROM embeddings').fetchone()
        self.assertEqual(embedding, (1, 'image', 3, 'cpu'))
        stored = self.derived / 'embeddings' / '1.npy'
        self.assertTrue(stored.is_file())
        np.testing.assert_array_equal(np.load(stored, allow_pickle=False), [0.25, 0.5, 0.75])

    def test_changed_source_hash_never_finishes_and_failure_is_sanitized(self):
        task_id = self.task()
        candidate = worker._claim_one(self.dbpath)
        self.source.write_bytes(b'changed synthetic content')
        args = self.args()
        with self.assertRaises(ValueError):
            worker._process_task(candidate, self.dbpath, self.originals, self.derived,
                                 args, self.checkpoint, worker.identity(self.checkpoint), self.stop)
        worker.record_failure(self.dbpath, task_id, candidate['retry_count'], ValueError('source_fingerprint_mismatch'))
        state, retries, error = self.db.execute('SELECT state,retry_count,last_error FROM tasks WHERE id=?',
                                                (task_id,)).fetchone()
        self.assertEqual((state, retries, error), ('failed', 1, 'source_fingerprint_mismatch'))

    def test_shared_gpu_lock_name_is_fixed_and_exclusive(self):
        expected = Path(str(self.dbpath) + '.approved-gpu-worker.lock')
        with worker.kernel_lock(self.dbpath):
            self.assertTrue(expected.is_file())
            with self.assertRaises(worker.Refused):
                with worker.kernel_lock(self.dbpath):
                    pass

    def test_worker_polls_until_operator_stop_without_claiming_other_jobs(self):
        self.task('thumb')
        args = self.args(); args.once = False
        class StopAfterWait:
            def is_set(self): return False
            def wait(self, _seconds): self_outer.stop.touch()
        self_outer = self
        with patch.object(worker, '_probe_provider', return_value={
                'effective_provider': 'open_clip', 'effective_device': 'cpu',
                'selected_physical_device': 'cpu', 'selected_gpu_uuid': None}), \
             patch.object(worker, '_claim_one', return_value=None), \
             patch.object(worker.threading, 'Event', StopAfterWait):
            result = worker.run(args)
        self.assertEqual(result['attempted'], 0)
        self.assertTrue(result['stopped_by_operator'])
        self.assertEqual(self.db.execute('SELECT state FROM tasks').fetchone()[0], 'pending')

    def test_cuda_preflight_requires_verifiable_physical_gpu_and_free_memory(self):
        uuid0 = 'GPU-00000000-0000-0000-0000-000000000000'
        uuid1 = 'GPU-11111111-1111-1111-1111-111111111111'
        def fake_popen(stdout):
            return SimpleNamespace(stdout=io.BytesIO(stdout), wait=lambda timeout: 0,
                                   returncode=0, kill=lambda: None)
        with patch.object(worker.shutil, 'which', return_value='nvidia-smi'), \
             patch.object(worker.subprocess, 'Popen', side_effect=lambda *a, **k: fake_popen(f'{uuid1}, 2500\n'.encode())):
            self.assertEqual(worker.gpu_free_memory('cuda:1', uuid1), 2500 * 1024**2)
        with patch.object(worker.shutil, 'which', return_value='nvidia-smi'), \
             patch.object(worker.subprocess, 'Popen', side_effect=lambda *a, **k: fake_popen(f'{uuid1}, 1500\n'.encode())), \
             self.assertRaisesRegex(RuntimeError, 'gpu_memory_floor'):
            worker.gpu_free_memory('cuda:1', uuid1)
        with patch.object(worker.shutil, 'which', return_value='nvidia-smi'), \
             patch.object(worker.subprocess, 'Popen', side_effect=lambda *a, **k: fake_popen(f'{uuid1}, 2500\n'.encode())), \
             self.assertRaisesRegex(RuntimeError, 'gpu_device_unverifiable'):
            worker.gpu_free_memory('cuda:1', uuid0)
        with patch.object(worker.shutil, 'which', return_value=None), \
             self.assertRaisesRegex(RuntimeError, 'gpu_device_unverifiable'):
            worker.gpu_free_memory('cuda:0', uuid0)

    def test_cuda_configuration_requires_explicit_expected_uuid(self):
        args = self.args(); args.device = 'cuda:0'
        with self.assertRaisesRegex(worker.Refused, 'Explicit expected GPU UUID required'):
            worker.preflight(self.dbpath, self.originals, self.derived, self.checkpoint,
                self.checksum, args.image_model, args.model_version, args.device,
                args.expected_gpu_uuid)

    def test_physical_second_gpu_is_logical_zero_inside_isolated_child(self):
        args = self.args(); args.device = 'cuda:1'
        args.expected_gpu_uuid = 'GPU-11111111-1111-1111-1111-111111111111'
        receipt = {'provider': 'open_clip', 'effective_provider': 'open_clip',
                   'effective_device': 'cuda:0', 'dimension': 512}

        def child(argv, *, env, **_kwargs):
            self.assertEqual(argv[argv.index('--device') + 1], 'cuda:0')
            self.assertEqual(env['CUDA_VISIBLE_DEVICES'], '1')
            Path(argv[argv.index('--receipt') + 1]).write_text(json.dumps(receipt))

        with patch.object(worker, 'gpu_free_memory', return_value=4 * 1024**3), \
             patch.object(worker, 'run_supervised', side_effect=child):
            observed = worker._probe_provider(args, self.checkpoint, deadline=float('inf'))
        self.assertEqual(observed['selected_physical_device'], 'cuda:1')
        self.assertEqual(observed['effective_device'], 'cuda:0')

        image = self.derived / 'sample.jpg'
        Image.new('RGB', (8, 8)).save(image)
        stage = self.derived / 'stage'; stage.mkdir()
        def embed_child(argv, *, env, **_kwargs):
            self.assertEqual(argv[argv.index('--device') + 1], 'cuda:0')
            self.assertEqual(env['CUDA_VISIBLE_DEVICES'], '1')
            with (stage / 'vector.npy').open('wb') as stream:
                np.save(stream, np.ones(512, dtype=np.float32), allow_pickle=False)
            (stage / 'result.json').write_text(json.dumps({
                **receipt, 'model_version': args.model_version}))

        with patch.object(worker, 'gpu_free_memory', return_value=4 * 1024**3), \
             patch.object(worker, 'run_supervised', side_effect=embed_child):
            vector, metadata, _ = worker._run_embed_child(
                image, stage, args, self.checkpoint, float('inf'))
        self.assertEqual(vector.shape, (512,))
        self.assertEqual(metadata['effective_device'], 'cuda:0')

    def test_windows_supervised_child_gets_hard_job_memory_cap_and_cleanup(self):
        job = Mock()
        module = SimpleNamespace(WindowsJob=Mock(return_value=job))
        proc = SimpleNamespace(poll=Mock(return_value=0), returncode=0, stdout=None)
        proc.stdout = None
        popen = Mock(return_value=proc)
        with patch.dict(sys.modules, {'home_memory_envelope': module}), \
             patch.object(worker.sys, 'platform', 'win32'), \
             patch.object(worker, 'observe_memory', return_value=(16 * 1024**3, 0)), \
             patch.object(worker.subprocess, 'Popen', popen), \
             patch.object(worker.subprocess, 'CREATE_NO_WINDOW', 0, create=True), \
             patch.object(worker.subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0, create=True):
            worker.run_supervised(['synthetic-child'], env={}, derived=self.derived,
                                  deadline=float('inf'))
        module.WindowsJob.assert_called_once_with(worker.MAX_CHILD_RSS // 1024**2)
        job.close.assert_called_once()
        self.assertEqual(popen.call_args.kwargs['creationflags'], 0)
