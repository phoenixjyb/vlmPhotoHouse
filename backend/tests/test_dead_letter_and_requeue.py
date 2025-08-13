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
        t = Task(type='fail_transient', priority=10, payload_json={})
        s.add(t)
        s.commit()
        tid = t.id
    # run once should mark dead immediately due to max retries 0
    app_main.executor.run_once()
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
