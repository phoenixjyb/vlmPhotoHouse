import pytest
from fastapi.testclient import TestClient
from app.main import app, get_db


def test_metrics_prometheus_endpoint():
    client = TestClient(app)
    r = client.get('/metrics.prom')
    assert r.status_code == 200
    body = r.text
    assert 'tasks_processed_total' in body
    assert 'vector_index_size' in body
    assert 'tasks_dead' in body


def test_dead_tasks_gauge_updates(override_settings):
    # force a dead task
    import os
    from app.config import get_settings
    import app.main as app_main
    from app.db import Task
    os.environ['MAX_TASK_RETRIES'] = '0'
    get_settings.cache_clear()  # type: ignore
    app_main.reinit_executor_for_tests()
    SessionLocal = app_main.SessionLocal
    with SessionLocal() as s:
        t = Task(type='fail_transient', priority=5, payload_json={})
        s.add(t)
        s.commit()
        tid = t.id
    # run task -> becomes dead
    app_main.executor.run_once()
    client = TestClient(app_main.app)
    r = client.get('/metrics.prom')
    assert r.status_code == 200
    body = r.text.splitlines()
    # find tasks_dead metric sample (may include type suffix for help/type lines)
    dead_lines = [ln for ln in body if ln.startswith('tasks_dead') and not ln.startswith('#')]
    assert dead_lines, 'tasks_dead gauge not exported'
    # Should be >=1 since we created one dead task
    value = float(dead_lines[0].split()[-1])
    assert value >= 1.0
    client.close()
