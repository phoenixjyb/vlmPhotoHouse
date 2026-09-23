"""Synthetic browser -> real ASGI approval workflow; no network listener or real media."""
import base64
import io
import json
import sys
from datetime import datetime, timezone
from contextlib import closing

from fastapi.testclient import TestClient
from PIL import Image
from test_promotion import PromotionTests
from test_access_foundation import NOW
from app.access.runtime import RuntimeConfiguration
from app.photo_delivery import PhotoCache

fixture = PromotionTests()
PromotionTests.setUpClass()
try:
    fixture.setUp()
    image = Image.new('RGB', (640, 480), '#b6c7b0')
    buffer = io.BytesIO(); image.save(buffer, format='JPEG')
    upload = fixture.upload(buffer.getvalue(), 'synthetic.jpg')
    uploads = [upload]
    for color in ('#d2ad89', '#8aa9c4'):
        buffer = io.BytesIO(); Image.new('RGB', (640, 480), color).save(buffer, format='JPEG')
        upload = fixture.upload(buffer.getvalue(), 'synthetic.jpg')
        uploads.append(upload)
    # Put more than one gallery page of dated existing assets ahead of the upload receipt time.
    # Their real captured dates must continue to sort chronologically, while the approved upload
    # (which has taken_at NULL) should use its access_uploads.created_at fallback.
    dated = [(1000 + i, datetime.fromtimestamp(NOW - (i + 1) * 86400, timezone.utc).isoformat())
             for i in range(25)]
    with closing(fixture.connection()) as db:
        db.executemany('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at)
            VALUES (?,?,?,'active','image/jpeg',640,480,?)''',
            [(asset_id, f'captured/{asset_id}.jpg', f'hash-{asset_id}', taken_at)
             for asset_id, taken_at in dated])
        db.executemany('INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (?,?)',
                       [(asset_id, 'family-a') for asset_id, _ in dated])
        db.commit()
    derived = fixture.root/'derived'
    (derived/'thumbnails/256').mkdir(parents=True)
    image.save(derived/'thumbnails/256/900.jpg')
    for item in uploads:
        image.save(derived/f"thumbnails/256/{item['asset_id']}.jpg")
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
        if message.get('command') == 'seed_video':
            import hashlib
            from pathlib import Path
            from app.access.resumable import Transfers
            data=(Path(__file__).parent/'fixtures/home-video.mp4').read_bytes()
            transfers=Transfers(fixture.uploads)
            row=transfers.create(fixture.member_token,dict(request_id='1'*32,batch='2'*32,
                filename='synthetic.mp4',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),kind='video'))
            transfers.append(fixture.member_token,row['upload_id'],0,data,hashlib.sha256(data).hexdigest())
            receipt=transfers.complete(fixture.member_token,row['upload_id'])
            print(json.dumps(dict(id=message['id'],asset_id=receipt['asset_id'])),flush=True);continue
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
