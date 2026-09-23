import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import run_approved_face_worker as worker


def db_fixture(tmp_path):
    path = tmp_path / "metadata.sqlite"
    db = sqlite3.connect(path)
    db.executescript(
        """
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
        """
    )
    db.commit(); db.close()
    return path


def test_schema_and_eligibility_only_supported_upload_faces(tmp_path):
    path = db_fixture(tmp_path)
    db = worker.connect(path, readonly=False)
    worker.schema(db)
    source = tmp_path / "approved.jpg"; Image.new("RGB", (2, 2)).save(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    db.execute("INSERT INTO assets VALUES(1,?,?,?,?,?)", (str(source), digest, source.stat().st_size, "image/jpeg", "active"))
    db.execute("INSERT INTO access_uploads VALUES(1,'assigned',?,?)", (digest, source.stat().st_size))
    db.execute("INSERT INTO access_asset_libraries VALUES(1,'family')")
    db.execute("INSERT INTO access_libraries VALUES('family','active')")
    db.execute("INSERT INTO tasks(id,type,payload_json,state,scheduled_at) VALUES(1,'face','{\"asset_id\":1}','pending',datetime('now'))")
    db.execute("INSERT INTO tasks(id,type,payload_json,state,scheduled_at) VALUES(2,'caption','{}','pending',datetime('now'))")
    db.commit()
    assert worker.eligible(db)[0] == 1
    db.close()


def test_approval_scope_and_hash_are_rechecked(tmp_path):
    path = db_fixture(tmp_path)
    originals = tmp_path / "originals"; originals.mkdir()
    source = originals / "photo.jpg"; Image.new("RGB", (4, 4), "white").save(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    db = worker.connect(path, readonly=False)
    db.execute("INSERT INTO assets VALUES(1,?,?,?,?,?)", (str(source), digest, source.stat().st_size, "image/jpeg", "active"))
    db.execute("INSERT INTO access_uploads VALUES(1,'assigned',?,?)", (digest, source.stat().st_size))
    db.execute("INSERT INTO access_asset_libraries VALUES(1,'family')")
    db.execute("INSERT INTO access_libraries VALUES('family','active')")
    db.commit()
    assert worker.allowed_asset(db, 1, originals) == source
    source.write_bytes(b"changed")
    with pytest.raises(worker.Refused, match="source_changed|source_hash_mismatch"):
        worker.allowed_asset(db, 1, originals)
    db.close()


def test_face_scope_requires_receipt_and_one_active_library(tmp_path):
    path = db_fixture(tmp_path)
    originals = tmp_path / 'originals'; originals.mkdir()
    source = originals / 'photo.jpg'; Image.new('RGB', (4, 4)).save(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    size = source.stat().st_size
    db = worker.connect(path, readonly=False)
    db.execute('INSERT INTO assets VALUES(1,?,?,?,?,?)',
               (str(source), digest, size, 'image/jpeg', 'active'))
    db.execute("INSERT INTO access_uploads VALUES(1,'assigned',?,?)", (digest, size))
    db.execute("INSERT INTO access_libraries VALUES('family','active')")
    db.execute("INSERT INTO access_asset_libraries VALUES(1,'family')")
    db.commit()
    assert worker.allowed_asset(db, 1, originals) == source
    db.execute("UPDATE access_uploads SET sha256='wrong'"); db.commit()
    with pytest.raises(worker.Refused, match='approval_scope'):
        worker.allowed_asset(db, 1, originals)
    db.execute('UPDATE access_uploads SET sha256=?', (digest,))
    db.execute("INSERT INTO access_libraries VALUES('archived','inactive')")
    db.execute("INSERT INTO access_asset_libraries VALUES(1,'archived')"); db.commit()
    with pytest.raises(worker.Refused, match='approval_scope'):
        worker.allowed_asset(db, 1, originals)
    db.execute("DELETE FROM access_asset_libraries WHERE library_id='archived'")
    db.execute('UPDATE assets SET status=NULL'); db.commit()
    with pytest.raises(worker.Refused, match='approval_scope'):
        worker.allowed_asset(db, 1, originals)
    db.close()


def test_claim_and_failure_are_bounded_and_sanitized(tmp_path):
    path = db_fixture(tmp_path)
    db = worker.connect(path, readonly=False)
    db.execute("INSERT INTO tasks(id,type,payload_json,state,scheduled_at) VALUES(7,'face_embed','{}','pending',datetime('now'))")
    db.commit()
    assert worker.claim(db, 7)
    worker.fail(db, 7, 0, RuntimeError("secret path /Users/private\ntrace"))
    row = db.execute("SELECT state,retry_count,last_error FROM tasks WHERE id=7").fetchone()
    assert row == ("failed", 1, "worker_error")
    db.close()


def test_cpu_gpu_lock_is_noop_and_model_version_is_bounded(tmp_path):
    path = db_fixture(tmp_path)
    with worker.gpu_lock(path, "cpu"):
        pass
    assert worker.MODEL_VERSION_RE.fullmatch("lvface-b-glint360k-aligned-d512-v1")
    assert not worker.MODEL_VERSION_RE.fullmatch("../unsafe")


def test_face_embed_scope_excludes_unapproved_asset(tmp_path):
    path = db_fixture(tmp_path)
    db = worker.connect(path, readonly=False)
    db.execute("INSERT INTO tasks(id,type,payload_json,state,scheduled_at) VALUES(8,'face_embed','{\"face_id\":9}','pending',datetime('now'))")
    db.execute("INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h) VALUES(9,4,0,0,1,1)")
    db.execute("INSERT INTO assets VALUES(4,'/tmp/x.jpg','x',1,'image/jpeg','active')")
    db.execute("INSERT INTO access_uploads VALUES(4,'incoming','x',1)")
    db.commit()
    assert worker.eligible(db) is None
    db.close()


def test_execute_remains_gated_until_hard_child_budget(tmp_path):
    path = db_fixture(tmp_path)
    originals = tmp_path / 'originals'; originals.mkdir()
    derived = tmp_path / 'derived'; derived.mkdir()
    models = tmp_path / 'models'; models.mkdir()
    checkpoint = models / 'face.onnx'; checkpoint.write_bytes(b'synthetic')
    with pytest.raises(SystemExit, match='execution_requires_child_budget'):
        worker.main([
            '--database', str(path), '--originals', str(originals),
            '--derived', str(derived), '--stop-file', str(tmp_path / 'stop'),
            '--model-path', str(checkpoint), '--insightface-root', str(models),
            '--model-version', 'test-v1', '--execute',
        ])
