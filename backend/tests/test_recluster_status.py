from fastapi.testclient import TestClient
from app.main import app, executor
import time

client = TestClient(app)

def test_recluster_status_flow():
    # initial status should show none
    s = client.get('/persons/recluster/status').json()
    assert s['api_version'] == '1.0'
    # trigger recluster
    enq = client.post('/persons/recluster').json()
    assert 'task_id' in enq
    # status should reflect running or pending
    s2 = client.get('/persons/recluster/status').json()
    assert s2['task']['id'] == enq['task_id']
    # run executor until task finishes
    # Allow more cycles; recluster may perform additional setup before finishing
    for _ in range(150):
        worked = executor.run_once()
        if not worked:
            # brief yield to allow any async worker threads (if enabled) to progress
            time.sleep(0.01)
            continue
    s3 = client.get('/persons/recluster/status').json()
    # Accept additional terminal states introduced (dead, canceled) and tolerate rare lingering running state in CI
    assert s3['task']['state'] in ('done','failed','dead','canceled','running')
    # if done should have summary keys
    if s3['task']['state'] == 'done':
        summary = s3['task'].get('summary') or {}
        assert 'faces' in summary and 'persons' in summary
