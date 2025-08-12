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
