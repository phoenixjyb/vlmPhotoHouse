import sqlite3
import sys

import pytest

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import approved_face_queue as queue


def fixture_db():
    db = sqlite3.connect(":memory:")
    db.executescript("""
    CREATE TABLE alembic_version(version_num TEXT);
    INSERT INTO alembic_version VALUES ('a8d4c2e6f901');
    CREATE TABLE tasks(id INTEGER PRIMARY KEY,type TEXT,payload_json TEXT,state TEXT,
      priority INTEGER DEFAULT 100,retry_count INTEGER DEFAULT 0,cancel_requested INTEGER DEFAULT 0,
      scheduled_at TEXT,started_at TEXT,finished_at TEXT,last_error TEXT);
    CREATE TABLE assets(id INTEGER PRIMARY KEY,path TEXT,hash_sha256 TEXT,file_size INTEGER,mime TEXT,status TEXT);
    CREATE TABLE access_uploads(asset_id INTEGER,state TEXT,sha256 TEXT,bytes INTEGER);
    CREATE TABLE access_asset_libraries(asset_id INTEGER,library_id TEXT);
    CREATE TABLE access_libraries(id TEXT,state TEXT);
    CREATE TABLE face_detections(id INTEGER PRIMARY KEY,asset_id INTEGER);
    CREATE TABLE face_embedding_artifacts(id INTEGER PRIMARY KEY,face_id INTEGER,model TEXT,
      model_version TEXT,dim INTEGER,alignment TEXT,storage_path TEXT,vector_checksum TEXT,status TEXT);
    """)
    return db


def approve(db, asset_id=1, *, path="/originals/a.jpg", digest="abc", size=12,
            mime="image/jpeg", asset_status="active", receipt_state="assigned",
            receipt_digest=None, receipt_size=None, library_state="active", library="family"):
    db.execute("INSERT INTO assets VALUES(?,?,?,?,?,?)",
               (asset_id, path, digest, size, mime, asset_status))
    db.execute("INSERT INTO access_uploads VALUES(?,?,?,?)",
               (asset_id, receipt_state, digest if receipt_digest is None else receipt_digest,
                size if receipt_size is None else receipt_size))
    db.execute("INSERT INTO access_libraries VALUES(?,?)", (library, library_state))
    db.execute("INSERT INTO access_asset_libraries VALUES(?,?)", (asset_id, library))


def task(db, task_id, kind="face", payload='{"asset_id":1}', *, cancel=0):
    db.execute("INSERT INTO tasks(id,type,payload_json,state,cancel_requested,scheduled_at) VALUES(?,?,?,'pending',?,datetime('now'))",
               (task_id, kind, payload, cancel))


def test_schema_validates_exact_revision_tables_and_columns():
    db = fixture_db()
    queue.validate_schema(db)
    db.execute("UPDATE alembic_version SET version_num='other'")
    with pytest.raises(queue.QueueRefused, match="unsupported_schema"):
        queue.validate_schema(db)


def test_malformed_and_extra_payloads_are_skipped_without_sql_json_errors():
    db = fixture_db(); approve(db)
    task(db, 1, payload="not-json")
    task(db, 2, payload='{"asset_id":1,"extra":true}')
    task(db, 3, payload='{"asset_id":true}')
    task(db, 4)
    assert queue.select_candidate(db)["task_id"] == 4


@pytest.mark.parametrize("kwargs", [
    {"asset_status": "inactive"}, {"receipt_state": "incoming"},
    {"receipt_digest": "wrong"}, {"receipt_size": 13},
    {"library_state": "inactive"}, {"mime": "image/gif"},
])
def test_candidate_requires_active_approved_matching_source_and_supported_media(kwargs):
    db = fixture_db(); approve(db, **kwargs); task(db, 1)
    assert queue.select_candidate(db) is None


def test_duplicate_library_mapping_is_rejected():
    db = fixture_db(); approve(db); db.execute("INSERT INTO access_libraries VALUES('other','active')")
    db.execute("INSERT INTO access_asset_libraries VALUES(1,'other')"); task(db, 1)
    assert queue.select_candidate(db) is None


def test_face_embed_payload_resolves_face_to_approved_asset():
    db = fixture_db(); approve(db)
    db.execute("INSERT INTO face_detections VALUES(19,1)")
    task(db, 8, "face_embed", '{"face_id":19}')
    got = queue.select_candidate(db)
    assert (got["kind"], got["asset_id"], got["face_id"]) == ("face_embed", 1, 19)
    assert got["path"] == "/originals/a.jpg"


def test_claim_rechecks_approval_and_verify_rechecks_cancellation_and_metadata():
    db = fixture_db(); approve(db); task(db, 1)
    db.commit()
    candidate = queue.select_candidate(db)
    assert queue.claim(db, candidate)
    db.execute("BEGIN IMMEDIATE")
    assert queue.verify_claim(db, candidate)
    db.commit()
    db.execute("UPDATE tasks SET cancel_requested=1 WHERE id=1")
    db.commit()
    db.execute("BEGIN IMMEDIATE")
    assert not queue.verify_claim(db, candidate)
    db.rollback()
    db.execute("UPDATE tasks SET cancel_requested=0 WHERE id=1")
    db.execute("UPDATE assets SET hash_sha256='changed' WHERE id=1")
    db.commit()
    db.execute("BEGIN IMMEDIATE")
    assert not queue.verify_claim(db, candidate)
    db.rollback()


def test_claim_rechecks_approval_before_transition():
    db = fixture_db(); approve(db); task(db, 1)
    db.commit()
    candidate = queue.select_candidate(db)
    db.execute("UPDATE access_uploads SET sha256='changed'")
    db.commit()
    assert not queue.claim(db, candidate)
    assert db.execute("SELECT state FROM tasks WHERE id=1").fetchone()[0] == "pending"


def test_failure_and_recovery_only_touch_owned_running_tasks_and_bound_retries():
    db = fixture_db(); approve(db); task(db, 1)
    db.commit()
    candidate = queue.select_candidate(db); assert queue.claim(db, candidate)
    assert queue.record_failure(db, candidate, "arbitrary secret")
    assert db.execute("SELECT state,retry_count,last_error FROM tasks WHERE id=1").fetchone() == (
        "pending", 1, "worker_error")
    # An unrelated running task is not adopted by recovery.
    db.execute("INSERT INTO tasks(id,type,payload_json,state,last_error,retry_count) VALUES(2,'caption','{}','running','other-owner',0)")
    task(db, 3)
    db.commit()
    c3 = queue.select_candidate(db); assert queue.claim(db, c3)
    assert queue.recover_owned(db) == 1
    assert db.execute("SELECT state,retry_count FROM tasks WHERE id=3").fetchone() == ("pending", 1)
    assert db.execute("SELECT state,last_error FROM tasks WHERE id=2").fetchone() == ("running", "other-owner")
    # At the retry ceiling, owned abandoned work becomes dead; unrelated terminal rows stay intact.
    db.execute("UPDATE tasks SET retry_count=2 WHERE id=3")
    db.commit()
    assert queue.claim(db, queue.select_candidate(db))
    assert queue.recover_owned(db) == 1
    assert db.execute("SELECT state,retry_count FROM tasks WHERE id=3").fetchone() == ("dead", 3)
    db.execute("INSERT INTO tasks(id,type,payload_json,state,last_error) VALUES(4,'face','{}','failed','old')")
    db.commit()
    assert queue.recover_owned(db) == 0
    assert db.execute("SELECT state,last_error FROM tasks WHERE id=4").fetchone() == ("failed", "old")


def test_permanent_source_mismatch_requires_review_not_automatic_retry():
    db = fixture_db(); approve(db); task(db, 9)
    db.commit()
    candidate = queue.select_candidate(db); assert queue.claim(db, candidate)
    assert queue.record_failure(db, candidate, 'source_changed')
    assert db.execute('SELECT state,retry_count,last_error FROM tasks WHERE id=9').fetchone() == (
        'failed', 1, 'source_changed')
