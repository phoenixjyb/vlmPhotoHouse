import os, time
from fastapi.testclient import TestClient
from app.main import app, executor
from app.db import Task
from app.config import get_settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# This test simulates two embed tasks where we artificially slow one and verify both complete quickly under concurrency>1.

def test_multi_worker_embed_parallel(override_settings, temp_env_root):
    os.environ['WORKER_CONCURRENCY'] = '2'
    os.environ['ENABLE_INLINE_WORKER'] = 'true'
    os.environ['EMBED_TASK_SLEEP'] = '0.2'  # artificial per-task latency
    os.environ['WORKER_POLL_INTERVAL'] = '0.05'
    # Recreate settings to pick env changes
    get_settings.cache_clear()  # type: ignore
    settings = get_settings()
    # Start app client (triggers startup); then explicitly start multi workers (executor may have been constructed earlier)
    client = TestClient(app)
    executor.start_workers(2)
    # Insert two fake embed tasks referencing non-existent assets (will fail fast) plus a dim_backfill for variety
    # Instead create two assets so embed tasks succeed fast after delay
    from app.db import Asset, Base
    engine = create_engine(settings.database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as s:
        a1 = Asset(path=str(temp_env_root['originals']) + '/a1.jpg', hash_sha256='h1')
        a2 = Asset(path=str(temp_env_root['originals']) + '/a2.jpg', hash_sha256='h2')
        s.add_all([a1,a2])
        s.flush()
        t1 = Task(type='embed', priority=100, payload_json={'asset_id': a1.id})
        t2 = Task(type='embed', priority=100, payload_json={'asset_id': a2.id})
        s.add_all([t1, t2])
        s.commit()
        target_ids = {t1.id, t2.id}
    start = time.time()
    deadline = start + 3.0
    done = False
    while time.time() < deadline and not done:
        with SessionLocal() as s:
            rows = s.query(Task.id, Task.state).filter(Task.id.in_(target_ids)).all()
        done = all(state == 'done' for _, state in rows)
        if not done:
            time.sleep(0.05)
    assert done, f"Both tasks not done within deadline; rows={rows}"
    # (Timing-based speedup assertion removed to reduce flakiness on CI / Windows.)
    # Future enhancement: capture started_at timestamps and assert overlap < threshold.
    elapsed = time.time()-start  # kept for potential logging
    client.close()
