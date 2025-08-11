from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_embedding_backend_status_basic():
    r = client.get('/embedding/backend')
    assert r.status_code == 200
    data = r.json()
    assert data['api_version'] == '1.0'
    assert 'image_model' in data and 'text_model' in data
    assert 'device' in data and 'dim' in data
    assert 'reembed_scheduled' in data and 'total_assets' in data
    # stub defaults should have non-negative dim
    assert data['dim'] > 0
