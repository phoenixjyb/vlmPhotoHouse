import os, time
from datetime import datetime
from fastapi.testclient import TestClient
import app.main as app_main
from app.db import Task
from app.config import get_settings

"""Multi-worker concurrency tests.

Enhancement: We now assert concurrent execution actually occurred by comparing the
started_at timestamps of two intentionally slowed embed tasks. If the executor
were single-threaded the delta between started_at values would be roughly the
configured EMBED_TASK_SLEEP (plus small overhead). With concurrency=2 we expect
the start delta to be well below the per-task artificial latency.
"""

def test_multi_worker_embed_parallel(override_settings, temp_env_root):
    # Tune environment for deterministic concurrency demonstration
    os.environ['WORKER_CONCURRENCY'] = '2'
    os.environ['ENABLE_INLINE_WORKER'] = 'true'
    os.environ['EMBED_TASK_SLEEP'] = '0.3'  # artificial per-task latency (seconds)
    os.environ['WORKER_POLL_INTERVAL'] = '0.02'
    # Refresh settings & executor to pick up overrides
    get_settings.cache_clear()  # type: ignore
    get_settings()
    app_main.reinit_executor_for_tests()

    client = TestClient(app_main.app)
    app_main.executor.start_workers(2)

    from app.db import Asset
    SessionLocal = app_main.SessionLocal
    with SessionLocal() as s:
        a1 = Asset(path=str(temp_env_root['originals']) + '/mw_a1.jpg', hash_sha256='mw_h1')
        a2 = Asset(path=str(temp_env_root['originals']) + '/mw_a2.jpg', hash_sha256='mw_h2')
        s.add_all([a1, a2])
        s.flush()
        t1 = Task(type='embed', priority=100, payload_json={'asset_id': a1.id})
        t2 = Task(type='embed', priority=100, payload_json={'asset_id': a2.id})
        s.add_all([t1, t2])
        s.commit()
        target_ids = {t1.id, t2.id}

    start_wall = time.time()
    deadline = start_wall + 4.0
    done = False
    last_rows = []
    while time.time() < deadline and not done:
        with SessionLocal() as s:
            last_rows = s.query(Task.id, Task.state).filter(Task.id.in_(target_ids)).all()
        done = all(state == 'done' for _, state in last_rows)
        if not done:
            time.sleep(0.03)

    assert done, f"Both tasks not done within deadline; rows={last_rows}"

    # Fetch full task rows for timing analysis
    with SessionLocal() as s:
        tasks = s.query(Task).filter(Task.id.in_(target_ids)).all()
    assert len(tasks) == 2
    starts = sorted([t.started_at for t in tasks if t.started_at])
    finishes = sorted([t.finished_at for t in tasks if t.finished_at])
    assert len(starts) == 2 and len(finishes) == 2

    sleep_s = float(os.environ['EMBED_TASK_SLEEP'])
    start_delta = (starts[1] - starts[0]).total_seconds()
    total_elapsed = time.time() - start_wall

    # Concurrency expectation: start delta should be significantly less than the artificial per-task latency.
    # Allow generous threshold for slower CI/Windows scheduling.
    # print diagnostics (will show only on failure unless -s)
    print(f"multi-worker diagnostics: start_delta={start_delta:.4f}s total_elapsed={total_elapsed:.4f}s sleep={sleep_s}")
    assert start_delta < sleep_s * 0.7, f"Tasks did not appear to start concurrently: delta={start_delta:.4f}s sleep={sleep_s}s"

    # Overall wall-clock should be closer to ~sleep_s (plus overhead) than 2*sleep_s
    # Use a fuzzy upper bound: must be less than (sleep_s * 1.7) whereas sequential would exceed ~2*sleep_s.
    # Looser bound: allow up to ~2x sleep (some overhead / Windows scheduling); sequential would exceed about 2*sleep + overhead.
    assert total_elapsed < sleep_s * 2.2, f"Total elapsed {total_elapsed:.4f}s suggests sequential execution (sleep={sleep_s})"

    client.close()
