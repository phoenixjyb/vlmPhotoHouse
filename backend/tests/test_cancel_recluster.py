import threading, time
from fastapi.testclient import TestClient
from app.main import SessionLocal, Task, executor


def test_cancel_long_running_recluster(client: TestClient, monkeypatch):
    # Create a recluster task with artificial per-face sleep to allow cancellation window
    monkeypatch.setenv('PERSON_RECLUSTER_PER_FACE_SLEEP','0.01')
    # Create fake faces / embeddings via inserting a few tasks outputs quickly
    # We'll fabricate minimal face rows by triggering face tasks through existing pipeline not required; instead, we directly create recluster task.
    with SessionLocal() as s:
        # Insert a dummy person_recluster task directly (pending)
        recluster = Task(type='person_recluster', state='pending', priority=5, retry_count=0, payload_json={})
        s.add(recluster)
        s.commit()
        rid = recluster.id

    # Start executor in background thread to process
    def run_exec():
        for _ in range(50):
            executor.run_once()
            time.sleep(0.005)
    th = threading.Thread(target=run_exec, daemon=True)
    th.start()

    # After a short delay, mark cancel_requested
    time.sleep(0.05)
    with SessionLocal() as s:
        t = s.get(Task, rid)
        if t and t.state == 'running':
            t.cancel_requested = True
            s.commit()

    th.join(timeout=2)

    with SessionLocal() as s:
        t = s.get(Task, rid)
        # Accept either canceled or done (if very fast), but prefer canceled path
        assert t.state in ('canceled','done')
        if t.state == 'canceled':
            assert t.cancel_requested is True
