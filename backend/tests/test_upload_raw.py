from fastapi.testclient import TestClient


def test_raw_upload_and_dedup(client: TestClient):
    img_bytes = b'RAWTEST' + b'0' * 128
    headers = {'Content-Type': 'application/octet-stream'}
    # First upload (raw body)
    resp = client.post('/assets/upload?filename=test1.jpg', content=img_bytes, headers=headers)
    assert resp.status_code == 200, resp.text
    first = resp.json()
    assert first['tasks_enqueued'] == 5
    asset_id = first['asset']['id']

    # Second upload same bytes (dedupe -> zero new tasks)
    resp2 = client.post('/assets/upload?filename=test1.jpg', content=img_bytes, headers=headers)
    assert resp2.status_code == 200
    second = resp2.json()
    assert second['asset']['id'] == asset_id
    assert second['tasks_enqueued'] == 0

    # Inspect DB to ensure exactly 5 tasks reference this asset id
    from app.main import SessionLocal, Task  # type: ignore
    with SessionLocal() as s:
        tasks = s.query(Task).all()
        linked = [t for t in tasks if isinstance(getattr(t, 'payload_json', None), dict) and t.payload_json.get('asset_id') == asset_id]
        assert len(linked) == 5
