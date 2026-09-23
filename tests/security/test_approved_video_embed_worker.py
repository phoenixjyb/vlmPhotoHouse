import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_approved_video_embed_worker as worker


class ApprovedVideoEmbedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.originals = self.root / 'originals'; self.originals.mkdir()
        self.derived = self.root / 'derived'; self.derived.mkdir()
        self.frame_dir = self.derived / 'video_frames' / '1'; self.frame_dir.mkdir(parents=True)
        self.dbpath = self.root / 'catalog.sqlite'
        self.source = self.originals / 'member.mp4'; self.source.write_bytes(b'synthetic video source')
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self._frame(1, (0, 40, 100)); self._frame(2, (80, 30, 10))
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
        ''')
        size = self.source.stat().st_size
        self.db.execute('INSERT INTO assets VALUES (1,?,?,?,?,?)',
                        (str(self.source), size, self.digest, 'video/mp4', 'active'))
        self.db.execute("INSERT INTO access_uploads VALUES (1,'assigned',?,?)", (self.digest, size))
        self.db.execute("INSERT INTO access_libraries VALUES ('family','active')")
        self.db.execute("INSERT INTO access_asset_libraries VALUES (1,'family')")
        self.db.commit()
        self.checkpoint = self.root / 'clip.ckpt'; self.checkpoint.write_bytes(b'fake local checkpoint')
        self.checksum = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()
        self.stop = self.root / 'stop.flag'

    def _frame(self, index, color):
        Image.new('RGB', (48, 32), color).save(self.frame_dir / f'frame_{index:05d}.jpg')

    def tearDown(self):
        self.db.close(); self.tmp.cleanup()

    def task(self, kind='video_embed', payload=None):
        self.db.execute('INSERT INTO tasks(type,state,payload_json,scheduled_at) VALUES (?,?,?,CURRENT_TIMESTAMP)',
                        (kind, 'pending', json.dumps(payload or {'asset_id': 1})))
        self.db.commit()
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    def args(self):
        return type('Args', (), {'database': str(self.dbpath), 'originals_root': str(self.originals),
            'derived_root': str(self.derived), 'checkpoint': str(self.checkpoint),
            'checkpoint_sha256': self.checksum, 'image_model': 'clip-vit-b32',
            'model_version': 'synthetic-v1', 'device': 'cpu', 'expected_gpu_uuid': None,
            'stop_file': str(self.stop), 'execute': True, 'once': True})()

    def test_default_preflight_counts_only_approved_videos_with_bounded_frames(self):
        self.task('video_embed', {'asset_id': 99})
        self.task('video_embed', {'asset_id': 1})
        before = self.db.execute('SELECT id,state FROM tasks ORDER BY id').fetchall()
        with patch.object(worker.image_worker, '_probe_provider', return_value={
                'effective_provider': 'open_clip', 'effective_device': 'cpu',
                'selected_physical_device': 'cpu', 'selected_gpu_uuid': None}):
            args = self.args(); args.execute = False
            result = worker.run(args)
        self.assertEqual(result['approved_claimable'], 1)
        self.assertEqual(result['skipped_due_video_embed'], 1)
        self.assertFalse(result['activated'])
        self.assertEqual(before, self.db.execute('SELECT id,state FROM tasks ORDER BY id').fetchall())

    def test_legacy_unapproved_and_unrelated_tasks_are_skipped_unchanged(self):
        legacy = self.task('video_embed', {'asset_id': 99})
        thumb = self.task('embed', {'asset_id': 1, 'modality': 'image'})
        self.assertIsNone(worker._claim_one(self.dbpath, self.derived))
        self.assertEqual(self.db.execute('SELECT state FROM tasks WHERE id IN (?,?) ORDER BY id',
                                         (legacy, thumb)).fetchall(), [('pending',), ('pending',)])
        self.db.execute("UPDATE access_uploads SET state='incoming'"); self.db.commit()
        self.task('video_embed', {'asset_id': 1})
        self.assertIsNone(worker._claim_one(self.dbpath, self.derived))

    def test_synthetic_video_embedding_finishes_and_publishes_normalized_vector(self):
        task_id = self.task()
        candidate = worker._claim_one(self.dbpath, self.derived)
        self.assertEqual(candidate['task_id'], task_id)
        args = self.args()
        vector = np.array([0.6, 0.8], dtype=np.float32)

        def fake_inference(frames, stage, args, checkpoint, deadline):
            with (stage / 'vector.npy').open('wb') as stream:
                np.save(stream, vector, allow_pickle=False)
            return vector, hashlib.sha256((stage / 'vector.npy').read_bytes()).hexdigest()

        with patch.object(worker, '_run_inference', side_effect=fake_inference):
            self.assertTrue(worker._process(candidate, self.dbpath, self.originals,
                self.derived, args, self.checkpoint, worker.image_worker.identity(self.checkpoint), self.stop))
        self.assertEqual(self.db.execute('SELECT state FROM tasks WHERE id=?', (task_id,)).fetchone()[0], 'finished')
        artifact = self.derived / 'video_embeddings' / '1.npy'
        self.assertTrue(artifact.is_file())
        np.testing.assert_allclose(np.load(artifact, allow_pickle=False), vector)
        self.assertAlmostEqual(float(np.linalg.norm(np.load(artifact, allow_pickle=False))), 1.0, places=5)

    def test_source_hash_mismatch_is_failed_and_error_is_sanitized(self):
        task_id = self.task(); candidate = worker._claim_one(self.dbpath, self.derived)
        self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            worker._process(candidate, self.dbpath, self.originals, self.derived,
                self.args(), self.checkpoint, worker.image_worker.identity(self.checkpoint), self.stop)
        worker._record_failure(self.dbpath, candidate, ValueError('source_fingerprint_mismatch'))
        state, error = self.db.execute('SELECT state,last_error FROM tasks WHERE id=?', (task_id,)).fetchone()
        self.assertEqual((state, error), ('failed', 'source_fingerprint_mismatch'))
        self.assertNotIn(str(self.source), error)

    def test_corrupt_bounded_keyframe_fails_visibly(self):
        task_id = self.task(); candidate = worker._claim_one(self.dbpath, self.derived)
        (self.frame_dir / 'frame_00001.jpg').write_bytes(b'not a jpeg')
        with self.assertRaises(ValueError):
            worker._process(candidate, self.dbpath, self.originals, self.derived,
                self.args(), self.checkpoint, worker.image_worker.identity(self.checkpoint), self.stop)
        worker._record_failure(self.dbpath, candidate, ValueError('keyframe_output_invalid'))
        state, error = self.db.execute('SELECT state,last_error FROM tasks WHERE id=?', (task_id,)).fetchone()
        self.assertEqual((state, error), ('failed', 'keyframe_output_invalid'))

    def test_shared_gpu_lock_contract_matches_image_worker(self):
        expected = Path(str(self.dbpath) + '.approved-gpu-worker.lock')
        with worker.image_worker.kernel_lock(self.dbpath):
            self.assertTrue(expected.is_file())


if __name__ == '__main__':
    unittest.main()
