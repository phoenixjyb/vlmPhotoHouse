from fastapi.testclient import TestClient
from app.main import app, executor

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
    for _ in range(50):
        worked = executor.run_once()
        if not worked:
            break
    s3 = client.get('/persons/recluster/status').json()
    assert s3['task']['state'] in ('done','failed')
    # if done should have summary keys
    if s3['task']['state'] == 'done':
        summary = s3['task'].get('summary') or {}
        assert 'faces' in summary and 'persons' in summary
