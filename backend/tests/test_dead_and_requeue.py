import time
from fastapi.testclient import TestClient
from app.main import SessionLocal, Task, Asset, executor


def _add_task(session, **kwargs):
    t = Task(**kwargs)
    session.add(t)
    session.commit()
    return t


def test_dead_task_and_requeue(client: TestClient):
    # Configure fast retry backoff for this test
    import os
    os.environ['RETRY_BACKOFF_BASE_SECONDS'] = '0.01'
    os.environ['RETRY_BACKOFF_CAP_SECONDS'] = '0.02'
    os.environ['RETRY_BACKOFF_JITTER'] = '0.0'
    # Reinitialize executor to pick new settings
    from app.main import get_settings, reinit_executor_for_tests
    get_settings.cache_clear()  # type: ignore
    reinit_executor_for_tests()
    from app.main import executor  # updated reference
    # Add an asset row to satisfy embed task dependency
    import uuid
    with SessionLocal() as s:
        a = Asset(path=f'dummy_{uuid.uuid4().hex}.jpg', hash_sha256=uuid.uuid4().hex*2, width=10, height=10, file_size=1)
        s.add(a)
        s.flush()
        fail_task = Task(type='fail_transient', state='pending', priority=10, retry_count=0, payload_json={'asset_id': a.id})
        s.add(fail_task)
        s.commit()
        dead_id = fail_task.id

    # Run executor until task moves to dead (max retries = settings.max_task_retries default 3)
    for _ in range(200):
        executor.run_once()
        time.sleep(0.005)
        with SessionLocal() as s:
            t = s.get(Task, dead_id)
            if t and t.state == 'dead':
                break
    with SessionLocal() as s:
        t = s.get(Task, dead_id)
        assert t and t.state == 'dead'

    # List dead tasks endpoint
    resp = client.get('/admin/tasks/dead')
    assert resp.status_code == 200
    js = resp.json()
    ids = [t['id'] for t in js['tasks']]
    assert dead_id in ids

    # Requeue
    resp2 = client.post(f'/admin/tasks/{dead_id}/requeue')
    assert resp2.status_code == 200
    js2 = resp2.json()
    assert js2['state'] == 'pending'

    # Run once to process (will fail again and eventually dead again, but at least leaves pending first)
    executor.run_once()
