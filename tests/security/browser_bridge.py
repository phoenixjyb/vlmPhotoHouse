"""Synthetic browser-to-ASGI JSON-lines bridge over stdin/stdout; opens no port.

Only run from the browser security test. All storage lives in temporary fixtures.
"""
import base64
import json
from pathlib import Path
import sys

from test_library_reads import LibraryReadTests
from app.access.runtime import RuntimeConfiguration
from fastapi.testclient import TestClient

fixture = LibraryReadTests()
LibraryReadTests.setUpClass()
head_503 = False
try:
    fixture.setUp()
    # Tiny generated JPEG fixtures, never real family media. Pillow is a test-only
    # dependency; the application itself does not import it on this path.
    from PIL import Image, ImageDraw
    root = fixture.path.parent
    originals, derived = root / 'originals', root / 'derived'
    originals.mkdir(); (derived / 'thumbnails/256').mkdir(parents=True)
    for asset_id,color in ((101,'#b6c7b0'),(102,'#d2ad89'),(201,'#8aa9c4')):
        image=Image.new('RGB',(400,300),color)
        draw=ImageDraw.Draw(image);draw.rectangle((30,30,370,270),outline='#fff9ed',width=3)
        draw.text((135,145),f'SYNTHETIC {asset_id}',fill='#302c28')
        image.save(derived / f'thumbnails/256/{asset_id}.jpg')
        image.save(originals / f'{asset_id}.jpg')
        fixture.mutate('UPDATE assets SET path=? WHERE id=?',(str(originals / f'{asset_id}.jpg'),asset_id))
    fixture.client=TestClient(RuntimeConfiguration(fixture.path.resolve(), 'https://photohouse.test',
        (originals,), derived).build_app(clock=lambda:fixture.now),
        base_url='https://photohouse.test',client=('192.0.2.20',23456))
    fixture.addCleanup(fixture.client.close)
    (derived/'faces/256').mkdir(parents=True)
    with fixture.connection() as db:
        for person,name in [(1,'Alice'),(2,'Shared person'),*[(i,f'Person {i:02}') for i in range(10,37)]]:
            db.execute('INSERT INTO persons(id,display_name,face_count) VALUES(?,?,1)',(person,name))
            db.execute('INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h) VALUES(?,101,?,0,0,1,1)',(person,person))
            Image.new('RGB',(100,100),'#b6c7b0').save(derived/f'faces/256/{person}.jpg')
        db.execute('INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h) VALUES(99,201,2,0,0,1,1)')
        db.execute('INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h) VALUES(200,102,0,0,1,1)')
        Image.new('RGB',(100,100),'#d2ad89').save(derived/'faces/256/200.jpg')
        db.commit()
    print(json.dumps({'ready':True}),flush=True)
    for line in sys.stdin:
        message=json.loads(line)
        if message.get('command')=='quit':
            break
        if message.get('command')=='mutate':
            # Strict synthetic scenarios; no caller-supplied SQL or file paths.
            scenario=message['scenario']
            if scenario=='person-name-html':
                fixture.mutate("UPDATE persons SET display_name=?,updated_at='changed-by-test' WHERE id=1",('<img src=x onerror="window.syntheticXSS=true">',))
            elif scenario=='face-assignment-changed':
                fixture.mutate("UPDATE face_detections SET label_source='dnn',label_score=0.2 WHERE id=200")
            elif scenario=='album-title-changed':
                fixture.mutate("UPDATE albums SET title='Changed elsewhere' WHERE id IN (SELECT album_id FROM access_album_libraries)")
                fixture.mutate('UPDATE access_album_libraries SET revision=revision+1')
            elif scenario=='china-login':
                fixture.mutate("UPDATE access_accounts SET phone_login='+8610000000000' WHERE id=?", (fixture.member_id,))
            elif scenario=='international-login':
                fixture.mutate("UPDATE access_accounts SET phone_login='+12025550102' WHERE id=?", (fixture.member_id,))
            elif scenario=='revoke-member':
                fixture.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(fixture.member_id,))
            elif scenario=='restore-member':
                fixture.mutate("UPDATE access_memberships SET status='approved' WHERE account_id=?",(fixture.member_id,))
            elif scenario=='change-joined-membership':
                fixture.mutate("UPDATE access_memberships SET revision=revision+1 WHERE account_id IN (SELECT id FROM access_accounts WHERE phone_login='+12025550103')")
            elif scenario=='expire-sessions':
                fixture.mutate('UPDATE access_sessions SET expires_at=0')
            elif scenario=='caption-html':
                fixture.mutate("UPDATE captions SET text=? WHERE id=101",('<img src=x onerror="window.syntheticXSS=true">',))
            elif scenario=='member-second-library':
                from app.access.service import AccessService
                from test_access_foundation import MEMBER
                with fixture.connection() as db:
                    service=AccessService(db,clock=lambda:fixture.now)
                    code=service.invite(fixture.other_token,'family-b',MEMBER)
                    service.accept_invitation(fixture.member_token,code)
            elif scenario=='prepare-1024-thumbnail':
                from PIL import Image
                (derived/'thumbnails/1024').mkdir(parents=True,exist_ok=True)
                image=Image.open(derived/'thumbnails/256/101.jpg')
                image.resize((1024,768)).save(derived/'thumbnails/1024/101.jpg')
            elif scenario=='thumbnail-head-503':
                head_503=True
            else:
                raise ValueError('Unknown synthetic scenario')
            print(json.dumps({'id':message['id'],'ok':True}),flush=True);continue
        fixture.client.cookies.clear()
        if (head_503 and message['method']=='HEAD' and
                message['path'].startswith('/assets/101/thumbnail?') and
                'size=1024' in message['path']):
            head_503=False
            print(json.dumps({'id':message['id'],'status':503,'headers':{},'body':''}),flush=True)
            continue
        response=fixture.client.request(message['method'],message['path'],
            headers=message['headers'],content=base64.b64decode(message.get('body','')),
            follow_redirects=False)
        fixture.client.cookies.clear()
        print(json.dumps({'id':message['id'],'status':response.status_code,
            'headers':dict(response.headers),'body':base64.b64encode(response.content).decode()}),flush=True)
finally:
    fixture.doCleanups()
    LibraryReadTests.tearDownClass()
