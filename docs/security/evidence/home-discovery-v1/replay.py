#!/usr/bin/env python3
"""Replay a pinned source tree in-process with synthetic metadata/media only."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, required=True)
args = parser.parse_args()
root = args.source_root.resolve(strict=True)
sys.path[:0] = [str(root/'backend'), str(root/'scripts')]
from fastapi.testclient import TestClient
from app.home_discovery import Configuration, create_home_discovery
from build_home_discovery_fixture import create

examples = json.loads((root/'docs/security/home-discovery-examples-v1.json').read_text())
checks = []
with tempfile.TemporaryDirectory(prefix='home-discovery-replay-') as temporary, ExitStack() as stack:
    for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system', 'sqlite3.connect'):
        stack.enter_context(patch(target, side_effect=AssertionError('External state forbidden')))
    publication = Path(temporary).resolve()/'publication'
    index_sha = create(publication)
    config = Configuration(publication/'control.json', publication/'prepared',
                           'https://home.photohouse.test:18444', ('192.168.40.0/24',))
    app = create_home_discovery(config, publication/'discovery.json', index_sha)
    with TestClient(app, base_url=config.origin, client=('192.168.40.20', 1)) as client:
        for facet in ('people', 'tags', 'locations'):
            response = client.get('/home/discovery/v1/facets?facet='+facet+'&page_size=1')
            assert response.status_code == 200 and response.json() == examples['facets_'+facet]
            assert response.headers['cache-control'] == 'no-store'
            checks.append('exact_'+facet+'_facet_example')
        response = client.post('/home/discovery/v1/search', json=examples['search_request'])
        assert response.status_code == 200 and response.json() == examples['search_response']
        checks.append('exact_combined_search_example')
        body = dict(examples['search_request'], filters={'people': {'ids': [202], 'match': 'any'}, 'caption': 'sample child'})
        assert client.post('/home/discovery/v1/search', json=body).json()['items'] == []
        checks.append('caption_mention_is_not_identity')
        body['revision'] = 6
        assert client.post('/home/discovery/v1/search', json=body).status_code == 409
        checks.append('stale_discovery_revision_rejected')
        catalog = client.get('/home/v2/catalog')
        assert catalog.status_code == 200 and catalog.json()['library'] == examples['search_response']['library']
        checks.append('v2_library_binding')
        video = client.get('/home/v2/assets/102/video?revision=1', headers={'Range': 'bytes=0-7'})
        assert video.status_code == 206 and video.content == (root/'tests/security/fixtures/home-video.mp4').read_bytes()[:8]
        checks.append('frozen_v2_video_range')
        assert client.get('/home/v2/assets/101/preview?variant=display&revision=1').status_code == 200
        checks.append('frozen_v2_photo_preview')
        assert client.get('/assets/101/original').status_code == 403
        checks.append('legacy_original_denied')
        control = publication/'control.json'; value = json.loads(control.read_text()); value['enabled'] = False
        control.write_text(json.dumps(value))
        assert client.get('/home/discovery/v1/facets').status_code == 403
        assert client.get('/home/v2/catalog').status_code == 403
        checks.append('shared_disable')
print(json.dumps({'status': 'PASS_SYNTHETIC_ASGI_ONLY', 'checks': checks, 'check_count': len(checks),
                  'discovery_fixture_sha256': index_sha,
                  'examples_sha256': hashlib.sha256((root/'docs/security/home-discovery-examples-v1.json').read_bytes()).hexdigest(),
                  'listener_started': False, 'real_data_accessed': False, 'deployment_acceptance': False}, indent=2))
