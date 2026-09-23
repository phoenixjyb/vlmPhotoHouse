import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import approved_face_queue as queue
import run_approved_face_pipeline as worker


def fixture(tmp_path):
    originals = tmp_path / 'originals'; originals.mkdir()
    derived = tmp_path / 'derived'; derived.mkdir()
    source = originals / 'image.jpg'
    Image.new('RGB', (96, 64), 'white').save(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    database = tmp_path / 'metadata.sqlite'
    with sqlite3.connect(database) as db:
        db.executescript('''
          CREATE TABLE alembic_version(version_num TEXT);
          INSERT INTO alembic_version VALUES ('a8d4c2e6f901');
          CREATE TABLE tasks(id INTEGER PRIMARY KEY,type TEXT,payload_json TEXT,state TEXT,
            priority INTEGER DEFAULT 100,retry_count INTEGER DEFAULT 0,cancel_requested INTEGER DEFAULT 0,
            scheduled_at TEXT,started_at TEXT,finished_at TEXT,last_error TEXT);
          CREATE TABLE assets(id INTEGER PRIMARY KEY,path TEXT,hash_sha256 TEXT,file_size INTEGER,mime TEXT,status TEXT);
          CREATE TABLE access_uploads(asset_id INTEGER,state TEXT,sha256 TEXT,bytes INTEGER);
          CREATE TABLE access_asset_libraries(asset_id INTEGER,library_id TEXT);
          CREATE TABLE access_libraries(id TEXT,state TEXT);
          CREATE TABLE face_detections(id INTEGER PRIMARY KEY,asset_id INTEGER,bbox_x REAL,bbox_y REAL,
            bbox_w REAL,bbox_h REAL,person_id INTEGER,embedding_path TEXT,landmarks_json TEXT,
            landmark_model TEXT,label_source TEXT,label_score REAL);
          CREATE TABLE face_embedding_artifacts(id INTEGER PRIMARY KEY,face_id INTEGER,model TEXT,
            model_version TEXT,dim INTEGER,alignment TEXT,storage_path TEXT,vector_checksum TEXT,status TEXT,
            UNIQUE(face_id,model_version));
        ''')
        db.execute("INSERT INTO assets VALUES(1,?,?,?,?,?)", (str(source), digest, source.stat().st_size, 'image/jpeg', 'active'))
        db.execute("INSERT INTO access_uploads VALUES(1,'assigned',?,?)", (digest, source.stat().st_size))
        db.execute("INSERT INTO access_libraries VALUES('family','active')")
        db.execute("INSERT INTO access_asset_libraries VALUES(1,'family')")
        db.execute("INSERT INTO tasks(id,type,payload_json,state,scheduled_at) VALUES(1,'face','{\"asset_id\":1}','pending',datetime('now'))")
    detector = tmp_path / 'detector.onnx'; detector.write_bytes(b'detector')
    embedder = tmp_path / 'embedder.onnx'; embedder.write_bytes(b'embedder')
    config = {'database': database, 'originals': originals, 'derived': derived,
              'root': tmp_path, 'detector': detector, 'detector_id': worker.identity(detector),
              'embedder': embedder, 'embedder_id': worker.identity(embedder),
              'stop': tmp_path / 'stop', 'gpu_uuid': 'GPU-test'}
    return config, source


def claim_one(config):
    with sqlite3.connect(config['database']) as db:
        candidate = queue.select_candidate(db)
        assert candidate and queue.claim(db, candidate)
    return candidate


def fake_child(operation, stage, config, image=None):
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    if operation == 'detect':
        Image.new('RGB', (256, 256), 'blue').save(stage / 'face-00.jpg')
        return {'operation': 'detect', 'provider': 'CUDAExecutionProvider',
                'effective_device': 'cuda:0', 'model_root': str(config['root']),
                'input_sha256': digest, 'outputs': ['face-00.jpg'],
                'faces': [{'crop': 'face-00.jpg', 'bbox': [2, 3, 20, 22], 'landmarks': None}]}
    vector = np.ones(512, dtype='float32')
    vector /= np.linalg.norm(vector)
    np.save(stage / 'embedding.npy', vector)
    return {'operation': 'embed', 'provider': 'CUDAExecutionProvider',
            'effective_device': 'cuda', 'model_path': str(config['embedder']),
            'input_sha256': digest, 'outputs': ['embedding.npy'], 'dimension': 512}


def test_detection_and_embedding_publish_only_shadow_with_approved_scope(tmp_path, monkeypatch):
    config, _ = fixture(tmp_path)
    monkeypatch.setattr(worker, '_child', fake_child)
    assert worker._process(claim_one(config), config)
    with sqlite3.connect(config['database']) as db:
        assert db.execute("SELECT state FROM tasks WHERE id=1").fetchone() == ('finished',)
        assert db.execute("SELECT person_id,label_source FROM face_detections").fetchone() == (None, None)
        assert db.execute("SELECT state,payload_json FROM tasks WHERE type='face_embed'").fetchone() == (
            'pending', '{"face_id": 1}')
    assert (config['derived'] / 'faces' / '256' / '1.jpg').is_file()
    candidate = claim_one(config)
    assert candidate['kind'] == 'face_embed'
    assert worker._process(candidate, config)
    with sqlite3.connect(config['database']) as db:
        assert db.execute("SELECT status,model_version FROM face_embedding_artifacts").fetchone() == (
            'shadow', worker.VERSION)
        assert db.execute("SELECT count(*) FROM face_detections WHERE person_id IS NOT NULL").fetchone()[0] == 0
    assert (config['derived'] / 'face_embeddings' / worker.VERSION / '1.npy').is_file()


def test_cancel_after_inference_rolls_back_and_keeps_artifacts_private(tmp_path, monkeypatch):
    config, _ = fixture(tmp_path)
    candidate = claim_one(config)
    def cancel_child(operation, stage, config, image=None):
        result = fake_child(operation, stage, config, image)
        with sqlite3.connect(config['database']) as db:
            db.execute("UPDATE tasks SET cancel_requested=1 WHERE id=?", (candidate['task_id'],))
        return result
    monkeypatch.setattr(worker, '_child', cancel_child)
    with pytest.raises(worker.Refused, match='approval_or_claim_changed'):
        worker._process(candidate, config)
    with sqlite3.connect(config['database']) as db:
        assert db.execute("SELECT count(*) FROM face_detections").fetchone()[0] == 0
    assert not list(config['derived'].rglob('*.jpg'))


def test_publish_error_removes_uncommitted_files_and_journal(tmp_path, monkeypatch):
    config, _ = fixture(tmp_path)
    candidate = claim_one(config)
    monkeypatch.setattr(worker, '_child', fake_child)
    original = worker._publish_detection
    def fail_after_files(db, config, candidate, detections, published):
        original(db, config, candidate, detections, published)
        raise RuntimeError('synthetic_commit_failure')
    monkeypatch.setattr(worker, '_publish_detection', fail_after_files)
    with pytest.raises(RuntimeError, match='synthetic_commit_failure'):
        worker._process(candidate, config)
    with sqlite3.connect(config['database']) as db:
        assert db.execute("SELECT count(*) FROM face_detections").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM tasks WHERE type='face_embed'").fetchone()[0] == 0
    assert not list(config['derived'].rglob('*.jpg'))
    assert not list(config['derived'].glob('*.journal.json'))


def test_crash_recovery_removes_only_unreferenced_owned_output(tmp_path):
    config, _ = fixture(tmp_path)
    candidate = claim_one(config)
    orphan = config['derived'] / 'faces' / '256' / '99.jpg'
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b'orphan')
    journal = worker._write_journal(config, candidate, [orphan])
    with sqlite3.connect(config['database']) as db:
        worker._recover_journals(config, db)
        assert queue.recover_owned(db) == 1
        assert db.execute("SELECT state,retry_count FROM tasks WHERE id=1").fetchone() == ('pending', 1)
    assert not orphan.exists() and not journal.exists()


def test_recovery_refuses_referenced_output_and_preserves_file(tmp_path):
    config, _ = fixture(tmp_path)
    candidate = claim_one(config)
    existing = config['derived'] / 'faces' / '256' / '7.jpg'
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b'referenced')
    worker._write_journal(config, candidate, [existing])
    with sqlite3.connect(config['database']) as db:
        db.execute('INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h) VALUES(7,1,0,0,1,1)')
        db.commit()
        with pytest.raises(worker.Refused, match='journal_output_referenced'):
            worker._recover_journals(config, db)
    assert existing.read_bytes() == b'referenced'


def test_preexisting_journal_is_never_removed_by_task_attempt(tmp_path, monkeypatch):
    config, _ = fixture(tmp_path)
    candidate = claim_one(config)
    journal = worker._journal_path(config, candidate['task_id'])
    journal.write_bytes(b'foreign-or-previous-journal')
    monkeypatch.setattr(worker, '_child', fake_child)
    with pytest.raises(worker.Refused, match='unrecovered_journal'):
        worker._process(candidate, config)
    assert journal.read_bytes() == b'foreign-or-previous-journal'
