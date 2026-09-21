"""Synthetic browser -> real ASGI approval workflow; no network listener or real media."""
import base64
import io
import json
import sys
from contextlib import closing

from fastapi.testclient import TestClient
from PIL import Image
from test_promotion import PromotionTests
from app.access.runtime import RuntimeConfiguration
from app.photo_delivery import PhotoCache

fixture = PromotionTests()
PromotionTests.setUpClass()
try:
    fixture.setUp()
    image = Image.new('RGB', (640, 480), '#b6c7b0')
    buffer = io.BytesIO(); image.save(buffer, format='JPEG')
    upload = fixture.upload(buffer.getvalue(), 'synthetic.jpg')
    for color in ('#d2ad89', '#8aa9c4'):
        buffer = io.BytesIO(); Image.new('RGB', (640, 480), color).save(buffer, format='JPEG')
        upload = fixture.upload(buffer.getvalue(), 'synthetic.jpg')
    derived = fixture.root/'derived'
    (derived/'thumbnails/256').mkdir(parents=True)
    image.save(derived/'thumbnails/256/900.jpg')
    image.save(fixture.originals/'900.jpg')
    with closing(fixture.connection()) as db:
        db.execute('UPDATE assets SET path=? WHERE id=900', (str(fixture.originals/'900.jpg'),)); db.commit()
    client = TestClient(RuntimeConfiguration(fixture.path, 'https://photohouse.test',
        (fixture.originals,), fixture.root/'derived',
        incoming_root=fixture.incoming, upload_review_enabled=True,
        # Resource admission is tested separately; this tiny synthetic image uses the real decoder.
        photo_cache=PhotoCache(fixture.root/'preview-cache', guard_factory=lambda _: lambda *a, **kw: None)).build_app(clock=fixture.access.clock),
        base_url='https://photohouse.test', client=('192.0.2.20', 23456))
    print(json.dumps(dict(ready=True, asset_id=upload['asset_id'])), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        if message.get('command') == 'quit': break
        if message.get('command') == 'revoke':
            with closing(fixture.connection()) as db:
                db.execute('UPDATE access_sessions SET revoked=1'); db.commit()
            print(json.dumps(dict(id=message['id'], ok=True)), flush=True); continue
        client.cookies.clear()
        response = client.request(message['method'], message['path'], headers=message.get('headers'),
                                  content=base64.b64decode(message.get('body', '')))
        print(json.dumps(dict(id=message['id'], status=response.status_code,
            headers=dict(response.headers), body=base64.b64encode(response.content).decode())), flush=True)
    client.close()
finally:
    fixture.doCleanups()
    PromotionTests.tearDownClass()
