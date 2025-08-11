import time
from fastapi.testclient import TestClient
from app.main import app, SessionLocal
from app.db import Task

client = TestClient(app)

def test_recluster_enqueue():
    r = client.post('/persons/recluster')
    assert r.status_code == 200
    data = r.json()
    assert 'api_version' in data and 'task_id' in data
    time.sleep(0.05)
    with SessionLocal() as s:
        t = s.query(Task).filter(Task.type=='person_recluster').order_by(Task.id.desc()).first()
        assert t is not None
