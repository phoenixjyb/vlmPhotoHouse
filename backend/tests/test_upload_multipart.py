import io
from fastapi.testclient import TestClient

def test_multipart_upload(client: TestClient):
    # Create a small in-memory PNG (1x1) to minimize dependencies.
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (1,1), (255,0,0)).save(buf, format='PNG')
        data = buf.getvalue()
    except Exception:
        # Fallback raw bytes if Pillow missing (should be installed though)
        data = b'\x89PNG\r\n\x1a\n' + b'0'*64
    files = {'file': ('tiny.png', data, 'image/png')}
    resp = client.post('/assets/upload/multipart', files=files)
    assert resp.status_code == 200, resp.text
    js = resp.json()
    assert js['asset']['id'] > 0
    assert js['asset']['hash_sha256']
    # second upload should dedupe and enqueue 0 tasks
    resp2 = client.post('/assets/upload/multipart', files=files)
    assert resp2.status_code == 200
    js2 = resp2.json()
    assert js2['tasks_enqueued'] == 0
