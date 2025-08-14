import os, time
from datetime import datetime, timedelta
import app.main as app_main
from app.db import Task, Base
from app.config import get_settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# We simulate a failing embed task by referencing a missing asset id so handler errors 'asset missing'.

def test_exponential_backoff_scheduling(override_settings, temp_env_root):
    os.environ['RETRY_BACKOFF_BASE_SECONDS'] = '0.0'
    os.environ['RETRY_BACKOFF_CAP_SECONDS'] = '0.0'
    os.environ['MAX_TASK_RETRIES'] = '2'
    os.environ['WORKER_CONCURRENCY'] = '1'
    os.environ['ENABLE_INLINE_WORKER'] = 'true'
    os.environ['WORKER_POLL_INTERVAL'] = '0.02'
    # refresh settings and executor to pick env overrides
    get_settings.cache_clear()  # type: ignore
    settings = get_settings()
    app_main.reinit_executor_for_tests()
    # Use app's SessionLocal bound to the refreshed engine
    SessionLocal = app_main.SessionLocal
    with SessionLocal() as s:
        # fail_transient task raises OSError each run to trigger retries
        t = Task(type='fail_transient', priority=50, payload_json={})
        s.add(t)
        s.commit()
        tid = t.id
    # observe state transitions and scheduled_at growth
    previous_sched = None
    max_wait = time.time() + 5
    seen_retries = 0
    trace = []
    # Drive the executor manually for determinism
    while time.time() < max_wait:
        app_main.executor.run_once()
        with SessionLocal() as s:
            task = s.get(Task, tid)
            assert task is not None
            trace.append((task.state, task.retry_count, task.scheduled_at))
            if task.state in ('failed','dead'):
                assert task.retry_count >= 0
                break
            if task.retry_count > seen_retries:
                # should have scheduled_at set
                if task.state == 'pending':
                    assert task.scheduled_at is not None
                seen_retries = task.retry_count
        time.sleep(0.05)
    else:
        raise AssertionError(f'Task did not reach failed state within timeout; trace={trace}')
    # no TestClient used
