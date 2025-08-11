import pytest
from fastapi.testclient import TestClient
from app.main import app, get_db, SessionLocal
from app import db as models

client = TestClient(app)

def test_health_endpoint():
    r = client.get('/health')
    assert r.status_code == 200
    data = r.json()
    assert data['api_version'] == '1.0'
    assert 'ok' in data and 'db_ok' in data
    assert 'pending_tasks' in data
    assert 'index' in data and 'initialized' in data['index']


def test_metrics_endpoint_empty():
    r = client.get('/metrics')
    assert r.status_code == 200
    data = r.json()
    assert data['api_version'] == '1.0'
    assert 'assets' in data and 'total' in data['assets']
    assert 'tasks' in data and 'total' in data['tasks']
    assert 'vector_index' in data


def test_metrics_after_ingest(tmp_path):
    # create a fake image file
    import numpy as np
    from PIL import Image
    img_path = tmp_path / 'test.jpg'
    arr = (np.random.rand(64,64,3)*255).astype('uint8')
    Image.fromarray(arr).save(img_path)
    # ingest
    r = client.post('/ingest/scan', json={'roots': [str(tmp_path)]})
    assert r.status_code == 200
    # fetch metrics
    r2 = client.get('/metrics')
    assert r2.status_code == 200
    m = r2.json()
    assert m['assets']['total'] >= 1
    # Assets might not have embeddings yet (worker may not have processed) but counts present
    assert 'tasks' in m and 'total' in m['tasks']
