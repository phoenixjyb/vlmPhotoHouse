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
    print(json.dumps({'ready':True}),flush=True)
    for line in sys.stdin:
        message=json.loads(line)
        if message.get('command')=='quit':
            break
        if message.get('command')=='mutate':
            # Strict synthetic scenarios; no caller-supplied SQL or file paths.
            scenario=message['scenario']
            if scenario=='revoke-member':
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
            else:
                raise ValueError('Unknown synthetic scenario')
            print(json.dumps({'id':message['id'],'ok':True}),flush=True);continue
        fixture.client.cookies.clear()
        response=fixture.client.request(message['method'],message['path'],
            headers=message['headers'],content=base64.b64decode(message.get('body','')),
            follow_redirects=False)
        fixture.client.cookies.clear()
        print(json.dumps({'id':message['id'],'status':response.status_code,
            'headers':dict(response.headers),'body':base64.b64encode(response.content).decode()}),flush=True)
finally:
    fixture.doCleanups()
    LibraryReadTests.tearDownClass()
