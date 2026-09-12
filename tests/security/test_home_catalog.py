"""Synthetic offline catalog, real synthetic JPEG/MP4 and ASGI; no listeners/models."""
import asyncio
import copy
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from native_home_guards import install_windows_asyncio_wakeup

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'scripts')]
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from starlette.routing import Route
from app import home_catalog as home
from app.home_feed import create_home_feed
from app.main import create_app
import build_home_catalog
import build_home_catalog_fixture
import home_catalog_app


def sha(data): return hashlib.sha256(data).hexdigest()


class CatalogTests(unittest.TestCase):
    def setUp(self):
        install_windows_asyncio_wakeup(self)
        temp = tempfile.TemporaryDirectory(prefix='home-catalog-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.media = self.root/'prepared'; self.media.mkdir()
        self.control = self.root/'control.json'
        self.jpeg = (ROOT/'tests/security/fixtures/home-8x8.jpg').read_bytes()
        self.mp4 = (ROOT/'tests/security/fixtures/home-video.mp4').read_bytes()
        self.preview = {'state': 'ready', 'width': 8, 'height': 8, 'bytes': len(self.jpeg), 'sha256': sha(self.jpeg)}
        self.missing = {'state': 'unavailable', 'reason': 'not_prepared'}
        for variant in ('grid', 'display', 'video'): (self.media/variant).mkdir()
        for variant in ('grid', 'display'): (self.media/variant/'101.jpg').write_bytes(self.jpeg)
        self.video = self.video_files(self.mp4)
        self.value = {'version': 2, 'revision': 1, 'library_id': 'synthetic-library', 'title': 'Synthetic / 合成',
            'assets': [{'id': 102, 'kind': 'video', 'label': 'Synthetic video', 'width': None, 'height': None,
                        'previews': {'grid': dict(self.missing), 'display': dict(self.missing)}, 'video': self.video},
                       {'id': 101, 'kind': 'photo', 'label': 'Synthetic photo', 'width': 8, 'height': 8,
                        'previews': {'grid': dict(self.preview), 'display': dict(self.preview)}, 'video': None}]}
        self.publish()
        self.config = home.Configuration(self.control, self.media, 'https://home.photohouse.test:18444', ('192.168.40.0/24',))
        self.app = home.create_home_catalog(self.config)
        self.client = self.client_for(self.app)
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system', 'sqlite3.connect'):
            guard = patch(target, side_effect=AssertionError('External state forbidden')); guard.start(); self.addCleanup(guard.stop)

    def client_for(self, app, **kwargs):
        client = TestClient(app, base_url=self.config.origin, client=kwargs.get('peer', ('192.168.40.20', 1)),
                            raise_server_exceptions=kwargs.get('raise_errors', True))
        self.addCleanup(client.close); return client

    def video_files(self, data):
        chunks = json.dumps([sha(data[i:i+home.CHUNK_BYTES]) for i in range(0, len(data), home.CHUNK_BYTES)]).encode()
        (self.media/'video/102.mp4').write_bytes(data)
        (self.media/'video/102.chunks.json').write_bytes(chunks)
        return {'state': 'ready', 'mime': 'video/mp4', 'video_codec': 'h264', 'audio_codec': 'aac',
                'width': 320, 'height': 180, 'duration_ms': 500, 'bytes': len(data),
                'sha256': sha(data), 'chunks_sha256': sha(chunks)}

    def publish(self, enabled=True):
        raw = json.dumps(self.value).encode(); (self.root/'catalog.json').write_bytes(raw)
        self.state = {'version': 2, 'enabled': enabled, 'revision': self.value['revision'], 'catalog_sha256': sha(raw)}
        self.write_control()

    def write_control(self):
        pending = self.root/'control.new'; pending.write_text(json.dumps(self.state)); pending.replace(self.control)

    def video_url(self, revision=1): return f'/home/v2/assets/102/video?revision={revision}'
    def preview_url(self): return '/home/v2/assets/101/preview?variant=display&revision=1'

    def test_paging_exact_shape_and_missing_states_without_fallback(self):
        first = self.client.get('/home/v2/catalog?page_size=1').json()
        self.assertEqual((first['version'], first['revision'], first['total'], first['has_more']), (2, 1, 2, True))
        item = first['items'][0]; self.assertEqual(item['id'], 102)
        self.assertNotIn('url', item['previews']['grid']); self.assertFalse(item['originals_allowed'])
        self.assertNotIn('chunks_sha256', item['video']); self.assertEqual(item['video']['url'], self.video_url())
        second = self.client.get('/home/v2/catalog?page=2&page_size=1&revision=1').json()
        self.assertEqual([i['id'] for i in second['items']], [101]); self.assertFalse(second['has_more'])
        self.assertNotIn(str(self.root), json.dumps(first))

    def test_frozen_response_example_and_route_contract_match_actual_app(self):
        expected = json.loads((ROOT/'docs/security/home-catalog-response-v2.example.json').read_text())
        self.assertEqual(self.client.get('/home/v2/catalog').json(), expected)
        contract = json.loads((ROOT/'docs/security/home-catalog-contract-v2.json').read_text())
        self.assertEqual({(r['method'], r['path']) for r in contract['routes']},
                         {(method, r.path) for r in self.app.routes for method in r.methods})
        output = self.root/'new-fixture'
        self.assertEqual(build_home_catalog_fixture.build(output), expected)
        config = home.Configuration(output/'control.json', output/'prepared', self.config.origin, self.config.allowed_networks)
        client = self.client_for(home.create_home_catalog(config))
        self.assertEqual(client.get('/home/v2/catalog').json(), expected)
        self.assertEqual(client.get(self.video_url()).content, self.mp4)

    def test_stream_rechecks_disable_between_chunks(self):
        data = b'x' * (home.CHUNK_BYTES+40)
        self.value['assets'][0]['video'] = self.video_files(data); self.publish()
        chunks = []
        async def send(message):
            if message['type'] == 'http.response.body' and message.get('body'):
                chunks.append(message['body'])
                self.state['enabled'] = False; self.write_control()
        async def receive(): return {'type': 'http.request', 'body': b'', 'more_body': False}
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'}, 'http_version': '1.1',
                 'method': 'GET', 'scheme': 'https', 'path': '/home/v2/assets/102/video',
                 'query_string': b'revision=1', 'headers': [(b'host', b'home.photohouse.test:18444')],
                 'client': ('192.168.40.20', 1), 'server': ('home.photohouse.test', 18444), 'root_path': ''}
        with self.assertRaises(home.Refused): asyncio.run(self.app(scope, receive, send))
        self.assertEqual(chunks, [data[:home.CHUNK_BYTES]])
        self.state['enabled'] = True; self.write_control()
        self.assertEqual(self.client.get('/home/v2/catalog').status_code, 200)

    def test_launcher_check_never_listens_and_serve_uses_only_v2(self):
        from contextlib import redirect_stdout
        import io
        from unittest.mock import Mock
        with patch.object(home_catalog_app, 'load_config', return_value=(self.config, {'proxy_headers': False})):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(home_catalog_app.main(['--config', str(self.root/'config.json'), '--check-publication']), 0)
            self.assertFalse(json.loads(output.getvalue())['listener_started'])
            run = Mock()
            self.assertEqual(home_catalog_app.main(['--config', str(self.root/'config.json'), '--serve'], server_run=run), 0)
            app = run.call_args.args[0]
            self.assertEqual(self.client_for(app).get('/home/v2/catalog').status_code, 200)
            self.assertEqual(self.client_for(app).get('/home/v1/feed').status_code, 403)

    def test_larger_than_v1_catalog_has_complete_stable_pagination(self):
        template = self.value['assets'][1]
        self.value['assets'] = [dict(template, id=i) for i in range(27842, 0, -1)]; self.publish()
        body = self.client.get('/home/v2/catalog?page=279&page_size=100&revision=1').json()
        self.assertEqual((body['total'], len(body['items']), body['items'][-1]['id'], body['has_more']), (27842, 42, 1, False))
        self.assertEqual(self.client.get('/home/v2/catalog?page=280&page_size=100&revision=1').json()['items'], [])

    def test_exact_parameters_and_revision_required_for_following_pages(self):
        for query, code in [('page=2', 400), ('page_size=101', 400), ('page=0', 400), ('page=01', 400),
                            ('revision=2', 409), ('page=1&page=2', 400), ('path=/anything', 400)]:
            with self.subTest(query=query): self.assertEqual(self.client.get('/home/v2/catalog?'+query).status_code, code)
        self.assertEqual(self.client.get(self.video_url(2)).status_code, 409)
        self.assertEqual(self.client.get('/home/v2/assets/102/video').status_code, 400)

    def test_denied_peers_hosts_and_credentials_before_storage(self):
        for peer in [('203.0.113.5', 1), ('192.168.41.1', 1), ('127.0.0.1', 1), ('::1', 1), None]:
            with self.subTest(peer=peer), patch.object(home, 'bounded_read', side_effect=AssertionError('Storage forbidden')):
                client = self.client_for(self.app, peer=peer)
                self.assertEqual(client.get('/home/v2/catalog', headers={'X-Forwarded-For': '192.168.40.20'}).status_code, 403)
        for headers in [{'Host': 'wrong.test'}, {'Authorization': 'Bearer synthetic'}, {'Cookie': 'session=synthetic'},
                        {'Origin': 'https://other.test'}, {'Sec-Fetch-Site': 'cross-site'}]:
            self.assertEqual(self.client.get(self.video_url(), headers=headers).status_code, 403)

    def test_closed_routes_and_unreviewed_shadow(self):
        for path in ('/assets/101/media', '/home/v1/feed', '/auth/session', '/health', '/search', '/voice', '/albums',
                     '/openapi.json', '/home/v2/assets/101/original', '/home/v2/catalog/'):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.post('/home/v2/catalog').status_code, 403)
        async def shadow(request): return JSONResponse({'unsafe': True})
        self.app.router.routes.insert(0, Route('/home/v2/catalog', shadow, methods=['GET']))
        self.assertEqual(self.client.get('/home/v2/catalog').status_code, 403)

    def test_v1_and_phone_do_not_mount_v2(self):
        for app in (create_home_feed(self.config), create_app()):
            self.assertEqual(self.client_for(app).get('/home/v2/catalog').status_code, 403)

    def test_jpeg_exact_bytes_head_and_no_range(self):
        result = self.client.get(self.preview_url())
        self.assertEqual((result.status_code, result.content), (200, self.jpeg))
        head = self.client.head(self.preview_url()); self.assertEqual(head.content, b'')
        self.assertEqual(int(head.headers['content-length']), len(self.jpeg))
        self.assertEqual(self.client.get(self.preview_url(), headers={'Range': 'bytes=0-1'}).status_code, 400)
        self.assertEqual(self.client.get('/home/v2/assets/102/preview?variant=grid&revision=1').status_code, 404)

    def test_video_get_and_head_exact_and_private(self):
        for _ in range(6):  # Leases must be released after each stream.
            result = self.client.get(self.video_url())
            self.assertEqual((result.status_code, result.content), (200, self.mp4))
            self.assertEqual(result.headers['cache-control'], 'no-store')
            self.assertEqual(result.headers['content-type'], 'video/mp4')
            self.assertEqual(result.headers['accept-ranges'], 'bytes')
        result = self.client.head(self.video_url(), headers={'Range': 'bytes=1-3'})
        self.assertEqual((result.status_code, result.content), (200, b''))  # RFC: HEAD ignores Range.
        self.assertEqual(int(result.headers['content-length']), len(self.mp4))
        self.assertNotIn('content-range', result.headers)

    def test_valid_ranges_exact_bytes_and_headers(self):
        n = len(self.mp4)
        for header, start, end in [('bytes=0-0', 0, 0), ('bytes=5-19', 5, 19), ('bytes=8-', 8, n-1),
                                    ('bytes=-10', n-10, n-1), ('bytes=9-999999', 9, n-1), ('bytes=-999999', 0, n-1)]:
            with self.subTest(header=header):
                result = self.client.get(self.video_url(), headers={'Range': header})
                self.assertEqual((result.status_code, result.content), (206, self.mp4[start:end+1]))
                self.assertEqual(result.headers['content-range'], f'bytes {start}-{end}/{n}')
                self.assertEqual(int(result.headers['content-length']), end-start+1)

    def test_invalid_ranges_and_if_range_fail_without_full_file(self):
        for header in ('bytes=999999-', 'bytes=9-1', 'bytes=-0', 'bytes=-', 'bytes=0-1,4-5',
                       'bytes=x-1', 'items=1-2', 'bytes=0-99999999999999'):
            with self.subTest(header=header):
                result = self.client.get(self.video_url(), headers={'Range': header})
                self.assertEqual(result.status_code, 416)
                self.assertEqual(result.headers['content-range'], f'bytes */{len(self.mp4)}')
                self.assertNotEqual(result.content, self.mp4)
        self.assertEqual(self.client.get(self.video_url(), headers={'If-Range': 'synthetic'}).status_code, 400)
        self.assertEqual(self.client.get(self.video_url(), headers=[('Range', 'bytes=0-1'), ('Range', 'bytes=2-3')]).status_code, 400)

    def test_range_crosses_hash_chunks_without_full_file_buffer(self):
        # Synthetic framing bytes deliberately repeated only for transport-boundary tests.
        data = b'x' * (home.CHUNK_BYTES+40)
        self.value['assets'][0]['video'] = self.video_files(data); self.publish()
        result = self.client.get(self.video_url(), headers={'Range': f'bytes={home.CHUNK_BYTES-3}-{home.CHUNK_BYTES+7}'})
        self.assertEqual((result.status_code, result.content), (206, b'x'*11))

    def test_tampered_first_chunk_never_sends_media(self):
        path = self.media/'video/102.mp4'; value = bytearray(self.mp4); value[-1] ^= 1; path.write_bytes(value)
        for _ in range(6): self.assertEqual(self.client.get(self.video_url()).status_code, 503)

    def test_tampered_later_chunk_not_emitted_and_lease_released(self):
        data = b'x' * home.CHUNK_BYTES + b'correct'
        self.value['assets'][0]['video'] = self.video_files(data); self.publish()
        path = self.media/'video/102.mp4'; path.write_bytes(b'x'*home.CHUNK_BYTES+b'corrupt')
        with self.assertRaises(home.Refused): self.client.get(self.video_url())
        self.assertEqual(self.client.get('/home/v2/catalog').status_code, 200)

    def test_disable_and_changed_publication_fail_closed_after_cache_load(self):
        self.assertEqual(self.client.get('/home/v2/catalog').status_code, 200)
        self.state['enabled'] = False; self.write_control()
        self.assertEqual(self.client.get(self.video_url()).status_code, 403)
        self.state['enabled'] = True; self.write_control()
        self.assertEqual(self.client.get('/home/v2/catalog').status_code, 200)
        self.state['revision'] = 2; self.write_control()
        self.assertEqual(self.client.get('/home/v2/catalog').json()['error'], 'publication_changed')

    def test_control_malformed_missing_and_catalog_replacement_have_no_stale_fallback(self):
        self.client.get('/home/v2/catalog')
        self.control.write_text('{}'); self.assertEqual(self.client.get('/home/v2/catalog').status_code, 503)
        self.control.unlink(); self.assertEqual(self.client.get('/home/v2/catalog').status_code, 503)
        self.write_control()
        self.value['assets'].pop(); self.publish()
        self.assertEqual(self.client.get('/home/v2/catalog').status_code, 503)

    def test_duplicate_json_keys_and_extra_path_fields_rejected(self):
        self.control.write_text(self.control.read_text().replace('"version": 2', '"version": 2, "version": 2'))
        self.assertEqual(self.client.get('/home/v2/catalog').status_code, 503)
        self.value['assets'][0]['path'] = '/secret'; self.publish()
        self.assertEqual(self.client.get('/home/v2/catalog').status_code, 503)

    def test_order_duplicates_dimensions_and_unreviewed_codec_rejected(self):
        for mutate in [lambda v: v['assets'].reverse(), lambda v: v['assets'][0].update(id=101),
                       lambda v: v['assets'][0]['video'].update(video_codec='hevc'),
                       lambda v: v['assets'][0]['video'].update(width=3840),
                       lambda v: v['assets'][1]['previews']['grid'].update(width=513)]:
            value = copy.deepcopy(self.value); mutate(value)
            with self.assertRaises(home.Refused): home.validate_catalog(value)

    def test_symlink_media_and_catalog_rejected(self):
        path = self.media/'video/102.mp4'; moved = self.root/'elsewhere.mp4'; path.rename(moved); path.symlink_to(moved)
        self.assertEqual(self.client.get(self.video_url()).status_code, 503)
        catalog = self.root/'catalog.json'; moved = self.root/'elsewhere.json'; catalog.rename(moved); catalog.symlink_to(moved)
        self.assertEqual(self.client.get('/home/v2/catalog').status_code, 503)

    def test_unavailable_video_and_photo_video_endpoint(self):
        self.value['assets'][0]['video'] = dict(self.missing); self.publish()
        self.assertEqual(self.client.get(self.video_url()).status_code, 404)
        self.assertEqual(self.client.get('/home/v2/assets/101/video?revision=1').status_code, 404)
        self.assertEqual(self.client.get('/home/v2/assets/999/video?revision=1').status_code, 404)

    def test_stream_cleanup_on_send_failure_and_all_slots_busy(self):
        cleaned = []
        async def send(message): raise OSError('synthetic disconnected peer')
        async def receive(): return {'type': 'http.disconnect'}
        response = home.LeasedStream(iter([b'x']), cleanup=lambda: cleaned.append(True))
        with self.assertRaises(Exception):
            asyncio.run(response({'type': 'http', 'asgi': {'spec_version': '2.4'}}, receive, send))
        self.assertEqual(cleaned, [True])
        class Busy:
            def __init__(self, n): pass
            def acquire(self, **kwargs): return False
        with patch.object(home.threading, 'BoundedSemaphore', Busy):
            app = home.create_home_catalog(self.config)
        result = self.client_for(app).get(self.video_url())
        self.assertEqual((result.status_code, result.headers['retry-after']), (429, '2'))


class ExportTests(unittest.TestCase):
    def test_readonly_all_visible_ids_no_paths_no_copy_and_disabled_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); db = root/'synthetic.sqlite'
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute('CREATE TABLE assets (id INTEGER PRIMARY KEY,mime TEXT,width INTEGER,height INTEGER,status TEXT,path TEXT)')
                conn.executemany('INSERT INTO assets VALUES(?,?,?,?,?,?)', [
                    (1, 'image/jpeg', 8, 8, 'active', '/never/read/secret.jpg'),
                    (2, 'video/mp4', None, None, None, '/never/read/secret.mp4'),
                    (3, 'image/jpeg', 8, 8, 'hidden', '/never/read/hidden.jpg')])
            before = db.read_bytes(); output = root/'publication'
            result = build_home_catalog.export(db, output, 1)
            self.assertEqual(result['assets'], 2); self.assertFalse(result['enabled'])
            self.assertEqual(db.read_bytes(), before)
            catalog = json.loads((output/'catalog.json').read_text())
            self.assertEqual([a['id'] for a in catalog['assets']], [2, 1])
            self.assertNotIn('secret', json.dumps(catalog)); self.assertEqual(list((output/'prepared').iterdir()), [])
            with self.assertRaises(ValueError): build_home_catalog.export(db, output, 2)
            self.assertEqual(db.read_bytes(), before)


if __name__ == '__main__': unittest.main()
