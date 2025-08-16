import time
from fastapi.testclient import TestClient
import app.main as app_main
from app.db import Task
from app.config import get_settings


def test_dead_letter_and_requeue(override_settings):
    # set tiny retries
    import os
    os.environ['MAX_TASK_RETRIES'] = '0'
    get_settings.cache_clear()  # type: ignore
    app_main.reinit_executor_for_tests()
    client = TestClient(app_main.app)
    SessionLocal = app_main.SessionLocal
    with SessionLocal() as s:
        from datetime import datetime, timedelta
        t = Task(type='fail_transient', priority=10, payload_json={})
        # Force scheduled_at to be in the past to guarantee immediate execution even if
        # DB default timestamp resolution or clock skew would otherwise delay claiming.
        t.scheduled_at = datetime.utcnow() - timedelta(seconds=5)
        s.add(t)
        s.commit()
        tid = t.id
    # Run executor until task processed (allow a few iterations in case of race)
    for _ in range(5):
        app_main.executor.run_once()
        with SessionLocal() as s:
            t = s.get(Task, tid)
            if t and t.state != 'pending':
                break
    with SessionLocal() as s:
        t = s.get(Task, tid)
        assert t is not None
        assert t.state == 'dead'
    # list dead
    r = client.get('/admin/tasks/dead')
    assert r.status_code == 200
    body = r.json()
    assert body['total'] >= 1
    # requeue
    r2 = client.post(f'/admin/tasks/{tid}/requeue')
    assert r2.status_code == 200
    # verify pending
    with SessionLocal() as s:
        t = s.get(Task, tid)
        assert t is not None
        assert t.state == 'pending'
    client.close()
