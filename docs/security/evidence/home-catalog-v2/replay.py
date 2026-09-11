"""Replay synthetic contract/media checks from an explicitly extracted source tree."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from contextlib import ExitStack

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, required=True)
args = parser.parse_args()
root = args.source_root.resolve(strict=True)
sys.path[:0] = [str(root/'backend'), str(root/'scripts')]
from fastapi.testclient import TestClient
from app.home_catalog import create_home_catalog
from app.home_feed import Configuration
from build_home_catalog_fixture import build

checks = []
def check(name, condition):
    if not condition: raise AssertionError(name)
    checks.append(name)

with tempfile.TemporaryDirectory(prefix='catalog-replay-') as tmp, ExitStack() as stack:
    for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system', 'sqlite3.connect'):
        stack.enter_context(patch(target, side_effect=AssertionError('External state forbidden')))
    publication = Path(tmp).resolve()/'publication'
    build(publication)
    app = create_home_catalog(Configuration(publication/'control.json', publication/'prepared',
                'https://home.photohouse.test:18444', ('192.168.40.0/24',)))
    with TestClient(app, base_url='https://home.photohouse.test:18444', client=('192.168.40.20', 1)) as client:
        response = client.get('/home/v2/catalog')
        expected = json.loads((root/'docs/security/home-catalog-response-v2.example.json').read_text())
        check('exact_catalog_fixture', response.status_code == 200 and response.json() == expected)
        check('no_store', response.headers['cache-control'] == 'no-store')
        url = expected['items'][0]['video']['url']; data = (root/'tests/security/fixtures/home-video.mp4').read_bytes()
        check('complete_synthetic_mp4', client.get(url).content == data)
        response = client.get(url, headers={'Range': 'bytes=12-255'})
        check('range_exact_status_bytes_headers', response.status_code == 206 and response.content == data[12:256]
              and response.headers['content-range'] == f'bytes 12-255/{len(data)}')
        response = client.head(url, headers={'Range': 'bytes=12-255'})
        check('head_ignores_range', response.status_code == 200 and response.content == b'' and int(response.headers['content-length']) == len(data))
        check('multipart_denied', client.get(url, headers={'Range': 'bytes=0-1,4-5'}).status_code == 416)
        check('revision_required', client.get('/home/v2/catalog?page=2').status_code == 400)
        check('revision_conflict', client.get(url.replace('revision=1','revision=2')).status_code == 409)
        preview = client.get(expected['items'][1]['previews']['display']['url'])
        check('exact_jpeg', preview.content == (root/'tests/security/fixtures/home-8x8.jpg').read_bytes())
        check('legacy_original_denied', client.get('/assets/101/media').status_code == 403)
        control = publication/'control.json'; state = json.loads(control.read_text()); state['enabled'] = False
        control.write_text(json.dumps(state))
        check('disabled_stream_denied', client.get(url).status_code == 403)
    with TestClient(app, base_url='https://home.photohouse.test:18444', client=('203.0.113.20', 1)) as client:
        with patch('app.home_catalog.bounded_read', side_effect=AssertionError('Storage forbidden')):
            check('public_peer_denied_before_storage', client.get('/home/v2/catalog').status_code == 403)
print(json.dumps({'checks_passed': len(checks), 'checks': checks, 'real_media': False, 'listeners': False,
                  'contract_sha256': hashlib.sha256((root/'docs/security/home-catalog-contract-v2.json').read_bytes()).hexdigest()}))
