"""The real app.main factory with explicit synthetic storage, never legacy startup."""
from contextlib import contextmanager
import importlib.abc
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.routing import Route
from starlette.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.main import create_app
from app.access.boundary import ClosedBoundary
from app.access.media import AuthorizedMediaResponse, MediaRuntime
from app.access.transport import AccessRuntime, COOKIE
from app.access.service import AccessDenied, AccessService
from app.access.admission import apply_schema as apply_admission
from test_access_foundation import database, OWNER, OTHER_OWNER, MEMBER, PASSWORD, NOW
from access.bootstrap import bootstrap_owner


class ImportIsolationTests(unittest.TestCase):
    def test_cold_package_and_entrypoint_import_do_not_touch_runtime(self):
        prefix = '_photohouse_cold_import'
        before = set(sys.modules)
        handlers = list(logging.getLogger().handlers)
        class ForbidRuntime(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.')[-1] in {'config', 'dependencies', 'tasks', 'db', 'logging', 'legacy_main'} and fullname.startswith(prefix):
                    raise AssertionError('Runtime import: ' + fullname)
        finder = ForbidRuntime()
        sys.meta_path.insert(0, finder)
        try:
            with patch('sqlite3.connect', side_effect=AssertionError('Database on import')), \
                 patch('threading.Thread.start', side_effect=AssertionError('Worker on import')), \
                 patch('socket.socket.connect', side_effect=AssertionError('Network on import')), \
                 patch('socket.socket.bind', side_effect=AssertionError('Listener on import')):
                spec = importlib.util.spec_from_file_location(prefix, ROOT / 'backend/app/__init__.py',
                    submodule_search_locations=[str(ROOT / 'backend/app')])
                package = importlib.util.module_from_spec(spec)
                sys.modules[prefix] = package
                spec.loader.exec_module(package)
                main = importlib.import_module(prefix + '.main')
                self.assertIsNone(main.app.state.access_runtime)
                self.assertIsNone(main.app.state.media_runtime)
                self.assertEqual(len(main.app.routes), 23)
                self.assertEqual(main.app.router.on_startup, [])
                self.assertEqual(main.app.router.on_shutdown, [])
                self.assertEqual(logging.getLogger().handlers, handlers)
        finally:
            sys.meta_path.remove(finder)
            for name in set(sys.modules) - before:
                if name.startswith(prefix):
                    del sys.modules[name]

    def test_retired_main_refuses_import_before_any_runtime_dependency(self):
        spec = importlib.util.spec_from_file_location('_retired_api', ROOT / 'backend/app/legacy_main.py')
        with self.assertRaisesRegex(RuntimeError, 'Legacy API is retired'):
            spec.loader.exec_module(importlib.util.module_from_spec(spec))


class ClosedApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = database()
        cls.template.execute('BEGIN')
        apply_admission(cls.template.execute)
        cls.template.execute('CREATE TABLE face_detections(id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(id))')
        cls.template.executemany('INSERT INTO face_detections VALUES (?,?)', [(301, 101), (302, 201), (303, 102)])
        cls.template.commit()
        cls.owner_id = bootstrap_owner(cls.template, phone=OWNER, password=PASSWORD, library_id='family-a')
        bootstrap_owner(cls.template, phone=OTHER_OWNER, password=PASSWORD, library_id='family-b')
        service = AccessService(cls.template, clock=lambda: NOW)
        cls.owner_token = service.login(OWNER, PASSWORD)
        cls.other_token = service.login(OTHER_OWNER, PASSWORD)
        code = service.invite(cls.owner_token, 'family-a', MEMBER)
        cls.member_token = service.register(MEMBER, PASSWORD, code)
        cls.member_id = service.profile(cls.member_token)['account_id']
        cls.template.executemany('INSERT INTO access_asset_libraries VALUES (?,?)', [(101, 'family-a'), (102, 'family-a'), (201, 'family-b')])
        cls.template.execute('UPDATE access_memberships SET originals=1 WHERE account_id=?', (cls.member_id,))
        cls.template.commit()

    @classmethod
    def tearDownClass(cls):
        cls.template.close()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='photohouse-closed-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.originals, self.derived = self.root / 'originals', self.root / 'derived'
        self.originals.mkdir()
        self.derived.mkdir()
        self.path = self.root / 'synthetic.sqlite'
        seed = sqlite3.connect(self.path)
        self.template.backup(seed)
        for asset_id in (101, 102, 201, 999):
            path = self.originals / f'{asset_id}.mp4'
            path.write_bytes(f'synthetic-video-{asset_id}-0123456789'.encode())
            seed.execute('UPDATE assets SET path=? WHERE id=?', (str(path), asset_id))
            path = self.derived / 'thumbnails/256' / f'{asset_id}.jpg'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f'synthetic-thumbnail-{asset_id}'.encode())
        for face_id in (301, 302, 303):
            path = self.derived / 'faces/256' / f'{face_id}.jpg'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f'synthetic-crop-{face_id}'.encode())
        seed.commit()
        seed.close()
        self.now = NOW
        self.access = AccessRuntime(self.connection, 'https://photohouse.test', clock=lambda: self.now)
        self.media = MediaRuntime((self.originals,), self.derived)
        self.app = create_app(access_runtime=self.access, media_runtime=self.media)
        self.client = TestClient(self.app, base_url='https://photohouse.test', client=('192.0.2.10', 23456))
        self.client.headers['Sec-Fetch-Site'] = 'same-origin'
        self.addCleanup(self.client.close)
        for target in ('socket.socket.bind', 'socket.socket.connect', 'socket.socket.connect_ex', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start()
            self.addCleanup(guard.stop)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path)
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            yield conn
        finally:
            conn.close()

    def mutate(self, sql, args=()):
        with self.connection() as conn:
            conn.execute(sql, args)
            conn.commit()

    def headers(self, token=None, **extra):
        return {'Authorization': 'Bearer ' + (token or self.member_token), **extra}

    def assert_private(self, response):
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.headers['cross-origin-resource-policy'], 'same-origin')
        self.assertNotIn(str(self.root), response.text if not response.headers.get('content-type', '').startswith(('image/', 'video/')) else '')

    def test_default_app_and_lifespan_remain_closed_without_storage(self):
        with patch('sqlite3.connect', side_effect=AssertionError('Implicit storage')):
            with TestClient(create_app(), base_url='https://photohouse.test') as client:
                for path in ('/auth/session', '/assets/101/media?library=family-a'):
                    self.assertEqual(client.get(path, headers=self.headers()).status_code, 503)
                self.assertEqual(client.get('/health').status_code, 403)

    def test_complete_runtime_route_set_matches_active_inventory(self):
        inventory = json.loads((ROOT / 'docs/security/route_capabilities.json').read_text())
        expected = {(r['method'], r['path']) for r in inventory['routes'] if r['surface'] == 'photohouse'}
        actual = [(method, route.path) for route in self.app.routes for method in route.methods]
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), 23)
        for method, path in actual:
            sample = re.sub(r'\{[^}]+\}', '1', path)
            self.assertTrue(ClosedBoundary.allowed(method, sample))

    def test_every_retired_route_is_denied_or_replaced_by_a_protected_route(self):
        inventory = json.loads((ROOT / 'docs/security/route_capabilities.json').read_text())
        # No credential/data request may create a DB connection at the boundary.
        with patch.object(AccessRuntime, 'call', side_effect=AssertionError('Retired account dispatch')), \
             patch.object(MediaRuntime, 'open_file', side_effect=AssertionError('Retired media dispatch')):
            checked = 0
            for entry in inventory['routes']:
                if entry['surface'] != 'photohouse-retired':
                    continue
                path = re.sub(r'\{[^}]+\}', '1', entry['path'])
                response = self.client.request(entry['method'], path)
                self.assertIn(response.status_code, (401, 403))
                self.assert_private(response)
                checked += 1
            self.assertGreater(checked, 90)
        # Even an owner cannot call unfinished operational/mutation endpoints.
        for path in ('/health', '/search', '/albums/time', '/voice/command', '/assets/101/delete', '/new-route'):
            for method in ('GET', 'POST', 'HEAD', 'OPTIONS'):
                response = self.client.request(method, path, headers=self.headers(self.owner_token))
                self.assertEqual(response.status_code, 403)

    def test_ui_shell_is_public_but_has_no_data_endpoint_bypass(self):
        response = self.client.get('/ui')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers['content-type'])
        self.assert_private(response)
        self.assertEqual(self.client.get('/ui/app.js').status_code, 200)
        self.assertEqual(self.client.get('/ui/styles.css').status_code, 200)
        self.assertEqual(self.client.get('/ui/../assets', follow_redirects=False).status_code, 401)

    def test_safe_ui_has_strict_csp_and_legacy_deep_links_drop_private_query(self):
        response = self.client.get('/ui')
        self.assertIn("default-src 'none'", response.headers['content-security-policy'])
        self.assertIn("frame-ancestors 'none'", response.headers['content-security-policy'])
        self.assertEqual(response.headers['x-frame-options'], 'DENY')
        self.assertNotIn('unpkg', response.text)
        self.assertNotIn('voice-toggle', response.text)
        for path in ('/ui/search?q=private-synthetic', '/ui/admin?token=private-synthetic'):
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.headers['location'], '/ui')
            self.assertNotIn('private-synthetic', response.text)
        self.assertEqual(self.client.get('/ui/access/index.html').status_code, 403)

    def test_head_denials_have_no_asgi_body_even_before_an_http_server(self):
        import asyncio
        for path in ('/unfinished', '/assets/101/media'):
            messages = []
            async def send(message):
                messages.append(message)
            async def receive():
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
                'http_version': '1.1', 'method': 'HEAD', 'scheme': 'https', 'path': path,
                'raw_path': path.encode(), 'query_string': b'library=family-a',
                'headers': [(b'host', b'photohouse.test')], 'client': ('192.0.2.1', 1234),
                'server': ('photohouse.test', 443), 'root_path': ''}
            asyncio.run(self.app(scope, receive, send))
            self.assertIn(messages[0]['status'], (401,403))
            self.assertEqual(b''.join(m.get('body',b'') for m in messages), b'')
            self.assertIn((b'cross-origin-resource-policy', b'same-origin'), messages[0]['headers'])

    def test_oversized_query_is_rejected_before_sql_or_media_lookup(self):
        with patch.object(AccessRuntime, 'call', side_effect=AssertionError('Query reached domain')), \
             patch.object(MediaRuntime, 'open_file', side_effect=AssertionError('Query reached media')):
            for path in ('/assets/101/media', '/assets/101/thumbnail', '/faces/301/crop',
                         '/assets', '/assets/101/captions', '/libraries/family-a/members'):
                response = self.client.get(path + '?library=family-a&unknown=' + 'x'*1100, headers=self.headers())
                self.assertEqual(response.status_code,400)
                self.assert_private(response)

    def test_unreviewed_route_and_shadowed_login_handler_are_denied(self):
        effects = []
        async def accidental_endpoint(request):
            effects.append('leak')
            return JSONResponse({'private': 'synthetic'})
        # Deliberate malicious runtime registration in this test, including a
        # shadow of an otherwise allowed URL. Neither reaches the handler.
        self.app.router.routes.insert(0, Route('/accidental', accidental_endpoint, methods=['GET']))
        self.app.router.routes.insert(0, Route('/auth/login', accidental_endpoint, methods=['POST']))
        self.assertEqual(self.client.get('/accidental').status_code, 403)
        self.assertEqual(self.client.post('/auth/login').status_code, 403)
        self.assertEqual(effects, [])

    def test_account_router_runs_in_real_app(self):
        response = self.client.post('/auth/login', json={'phone': MEMBER, 'password': PASSWORD, 'transport': 'native'})
        self.assertEqual(response.status_code, 200)
        token = response.json()['access_token']
        self.assertEqual(self.client.get('/auth/session', headers=self.headers(token)).json()['account_id'], self.member_id)

    def test_approved_original_cached_thumbnail_crop_and_head(self):
        for path, expected in (('/assets/101/media', b'synthetic-video-101-0123456789'),
                               ('/assets/101/thumbnail', b'synthetic-thumbnail-101'),
                               ('/faces/301/crop', b'synthetic-crop-301')):
            response = self.client.get(path + '?library=family-a', headers=self.headers())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, expected)
            self.assert_private(response)
            response = self.client.head(path + '?library=family-a', headers=self.headers())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b'')
            self.assertEqual(response.headers['content-length'], str(len(expected)))
        response = self.client.get('/assets/101/media?library=family-a&download=true', headers=self.headers())
        self.assertEqual(response.headers['content-disposition'], 'attachment; filename="asset-101.mp4"')

    def test_range_suffix_open_ended_if_range_and_416(self):
        path = '/assets/101/media?library=family-a'
        full = self.client.get(path, headers=self.headers())
        for requested, expected in [('bytes=0-8', full.content[:9]), ('bytes=10-', full.content[10:]),
                                     ('bytes=-4', full.content[-4:]), ('bytes=-999', full.content)]:
            response = self.client.get(path, headers=self.headers(Range=requested))
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.content, expected)
            self.assertEqual(int(response.headers['content-length']), len(expected))
            self.assert_private(response)
        self.assertTrue(full.headers['etag'].startswith('W/'))
        for validator in (full.headers['etag'], 'Tue, 01 Sep 2026 00:00:00 GMT'):
            response = self.client.get(path, headers=self.headers(**{'Range': 'bytes=0-8', 'If-Range': validator}))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, full.content)
        self.assertEqual(self.client.get(path, headers=self.headers(**{'Range': 'bytes=0-8', 'If-Range': 'stale'})).content, full.content)
        for requested in ('bytes=999-', 'bytes=9-2', 'bytes=-0'):
            response = self.client.get(path, headers=self.headers(Range=requested))
            self.assertEqual(response.status_code, 416)
            self.assertEqual(response.headers['content-range'], f'bytes */{len(full.content)}')
            self.assert_private(response)
        for requested in ('bytes=0-1,3-4', 'bad', 'bytes=-', 'bytes=' + '9'*101 + '-'):
            self.assertEqual(self.client.get(path, headers=self.headers(Range=requested)).status_code, 400)

    def test_real_denial_matrix_precedes_every_media_filesystem_lookup(self):
        changes = [
            ('requested', "UPDATE access_memberships SET status='requested' WHERE account_id=?", (self.member_id,)),
            ('revoked', "UPDATE access_memberships SET status='revoked' WHERE account_id=?", (self.member_id,)),
            ('expired-membership', 'UPDATE access_memberships SET expires_at=? WHERE account_id=?', (NOW, self.member_id)),
            ('disabled-account', "UPDATE access_accounts SET state='disabled' WHERE id=?", (self.member_id,)),
            ('expired-session', 'UPDATE access_sessions SET expires_at=? WHERE digest IN (SELECT digest FROM access_sessions WHERE account_id=?)', (NOW, self.member_id)),
            ('revoked-session', 'UPDATE access_sessions SET revoked=1 WHERE account_id=?', (self.member_id,)),
        ]
        paths = ('/assets/101/media', '/assets/101/thumbnail', '/faces/301/crop')
        with patch('pathlib.Path.resolve', side_effect=AssertionError('Filesystem resolve before policy')), \
             patch('app.access.media.os.open', side_effect=AssertionError('Filesystem open before policy')):
            for token in (None, 'invalid', 'a'*43, self.other_token):
                for path in paths:
                    for method in ('GET', 'HEAD'):
                        headers = {'Range': 'bytes=0-8'}
                        if token:
                            headers.update(self.headers(token))
                        self.assertEqual(self.client.request(method, path + '?library=family-a', headers=headers).status_code, 401)
            for name, sql, args in changes:
                self.mutate(sql, args)
                for path in paths:
                    with self.subTest(case=name, path=path):
                        self.assertEqual(self.client.get(path + '?library=family-a', headers=self.headers(Range='bytes=0-8')).status_code, 401)
                self.mutate("UPDATE access_memberships SET status='approved',expires_at=NULL WHERE account_id=?", (self.member_id,))
                self.mutate("UPDATE access_accounts SET state='active' WHERE id=?", (self.member_id,))
                self.mutate('UPDATE access_sessions SET expires_at=?,revoked=0 WHERE account_id=?', (NOW+86400, self.member_id))

    def test_foreign_deleted_missing_and_unassigned_parent_ids_never_touch_files(self):
        paths = ('/assets/201/media', '/assets/201/thumbnail', '/faces/302/crop',
                 '/assets/102/media', '/assets/102/thumbnail', '/faces/303/crop',
                 '/assets/999/media', '/assets/123456/media', '/faces/123456/crop')
        with patch('pathlib.Path.resolve', side_effect=AssertionError('Filesystem lookup for denied object')):
            for path in paths:
                self.assertEqual(self.client.get(path + '?library=family-a', headers=self.headers()).status_code, 401)
            self.assertEqual(self.client.get('/assets/101/media?library=family-b', headers=self.headers()).status_code, 401)

    def test_original_grant_is_separate_even_for_owner_and_range(self):
        for token in (self.owner_token, self.member_token):
            self.mutate('UPDATE access_memberships SET originals=0')
            with patch('pathlib.Path.resolve', side_effect=AssertionError('Unauthorized original lookup')):
                response = self.client.get('/assets/101/media?library=family-a', headers=self.headers(token, Range='bytes=0-8'))
                self.assertEqual(response.status_code, 401)
            self.assertEqual(self.client.get('/assets/101/thumbnail?library=family-a', headers=self.headers(token)).status_code, 200)

    def test_web_cookie_media_and_revocation_between_range_requests(self):
        self.client.cookies.set(COOKIE, self.member_token)
        path = '/assets/101/media?library=family-a'
        response = self.client.get(path, headers={'Range': 'bytes=0-8'})
        self.assertEqual(response.status_code, 206)
        etag = response.headers['etag']
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (self.member_id,))
        with patch('pathlib.Path.resolve', side_effect=AssertionError('Revoked retry file access')):
            response = self.client.get(path, headers={'Range': 'bytes=9-', 'If-Range': etag})
            self.assertEqual(response.status_code, 401)
            self.assertNotIn('content-range', response.headers)
            self.assertNotIn('etag', response.headers)

    def test_revoke_after_response_construction_before_open(self):
        request = Request({'type': 'http', 'scheme': 'https', 'method': 'GET', 'path': '/assets/101/media',
            'query_string': b'library=family-a', 'headers': [(b'host', b'photohouse.test')], 'app': self.app})
        response = AuthorizedMediaResponse(request, self.member_token, 'family-a', 101, 'original', 256, False)
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (self.member_id,))
        import asyncio
        messages = []
        async def send(message):
            messages.append(message)
        async def receive():
            return {'type': 'http.disconnect'}
        with patch('pathlib.Path.resolve', side_effect=AssertionError('Stale grant file access')):
            asyncio.run(response(request.scope, receive, send))
        self.assertEqual(messages[0]['status'], 401)

    def test_outside_path_and_symlink_escape_are_denied(self):
        outside = self.root / 'outside.mp4'
        outside.write_bytes(b'private-synthetic-outside')
        self.mutate('UPDATE assets SET path=? WHERE id=101', (str(outside),))
        self.assertEqual(self.client.get('/assets/101/media?library=family-a', headers=self.headers()).status_code, 401)
        link = self.originals / 'escape.mp4'
        link.symlink_to(outside)
        self.mutate('UPDATE assets SET path=? WHERE id=101', (str(link),))
        self.assertEqual(self.client.get('/assets/101/media?library=family-a', headers=self.headers()).status_code, 401)
        thumb = self.derived / 'thumbnails/256/101.jpg'
        thumb.unlink()
        thumb.symlink_to(outside)
        self.assertEqual(self.client.get('/assets/101/thumbnail?library=family-a', headers=self.headers()).status_code, 401)

    def test_direct_service_cannot_bypass_parent_policy_or_traverse_variant_path(self):
        with patch('pathlib.Path.resolve', side_effect=AssertionError('Direct policy bypass')):
            for token, object_id, variant, size in ((self.other_token, 101, 'original', 256),
                    (self.member_token, 302, 'crop', 256), (self.member_token, 101, 'thumbnail', '../../faces'),
                    (self.member_token, 101, 'unknown', 256)):
                with self.assertRaises(AccessDenied):
                    self.media.open_file(self.access, token, 'family-a', object_id, variant, size)

    def test_membership_cannot_change_during_file_open_even_in_wal_mode(self):
        with self.connection() as conn:
            self.assertEqual(conn.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        actual_open = os.open
        events = []
        def during_open(*args, **kwargs):
            competing = sqlite3.connect(self.path, timeout=0)
            try:
                with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                    competing.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (self.member_id,))
                events.append('revocation-serialized')
            finally:
                competing.close()
            return actual_open(*args, **kwargs)
        with patch('app.access.media.os.open', side_effect=during_open):
            handle, _, _ = self.media.open_file(self.access, self.member_token, 'family-a', 101, 'original', 256)
        try:
            self.assertEqual(events, ['revocation-serialized'])
            self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (self.member_id,))
            # Already-authorized in-flight bytes are not a promise of recall.
            self.assertTrue(handle.read().startswith(b'synthetic-video'))
        finally:
            handle.close()
        self.assertEqual(self.client.get('/assets/101/media?library=family-a', headers=self.headers()).status_code, 401)

    def test_missing_cached_derivative_does_not_generate_or_fallback_to_original(self):
        path = self.derived / 'thumbnails/256/101.jpg'
        path.unlink()
        response = self.client.get('/assets/101/thumbnail?library=family-a', headers=self.headers())
        self.assertEqual(response.status_code, 404)
        self.assertFalse(path.exists())

    def test_pinned_descriptor_is_not_reopened_after_response_headers(self):
        import asyncio
        source = self.originals / '101.mp4'
        expected = source.read_bytes()
        request = Request({'type': 'http', 'asgi': {'spec_version': '2.4'}, 'scheme': 'https', 'method': 'GET',
            'path': '/assets/101/media', 'query_string': b'library=family-a',
            'headers': [(b'host', b'photohouse.test')], 'app': self.app})
        response = AuthorizedMediaResponse(request, self.member_token, 'family-a', 101, 'original', 256, False)
        messages = []
        async def send(message):
            if message['type'] == 'http.response.start':
                source.rename(self.originals / 'previous-101.mp4')
                source.write_bytes(b'synthetic-replacement-must-not-be-read')
            messages.append(message)
        async def receive():
            return {'type': 'http.disconnect'}
        asyncio.run(response(request.scope, receive, send))
        self.assertEqual(messages[0]['status'], 200)
        self.assertEqual(b''.join(m.get('body', b'') for m in messages), expected)

    def test_descriptor_closes_on_success_range_error_and_disconnect(self):
        import asyncio
        from starlette.requests import ClientDisconnect
        opened = []
        original_fdopen = os.fdopen
        def capture(*args, **kwargs):
            handle = original_fdopen(*args, **kwargs)
            opened.append(handle)
            return handle
        with patch('app.access.media.os.fdopen', side_effect=capture):
            for requested in (None, 'bytes=999-', 'invalid'):
                headers = self.headers(**({'Range': requested} if requested else {}))
                self.client.get('/assets/101/media?library=family-a', headers=headers)
                self.assertTrue(opened[-1].closed)
            request = Request({'type': 'http', 'asgi': {'spec_version': '2.4'}, 'scheme': 'https', 'method': 'GET',
                'path': '/assets/101/media', 'query_string': b'library=family-a',
                'headers': [(b'host', b'photohouse.test')], 'app': self.app})
            response = AuthorizedMediaResponse(request, self.member_token, 'family-a', 101, 'original', 256, False)
            async def send(message):
                raise OSError('Synthetic disconnect')
            async def receive():
                return {'type': 'http.disconnect'}
            with self.assertRaises(ClientDisconnect):
                asyncio.run(response(request.scope, receive, send))
        self.assertEqual(len(opened), 4)
        self.assertTrue(all(handle.closed for handle in opened))

    def test_query_credentials_duplicates_unknown_size_and_origin_rejected(self):
        for query in ('', '?library=family-a&token=secret', '?library=family-a&library=family-b',
                      '?library=family-a&size=../256', '?library=family-a&size=2048'):
            self.assertEqual(self.client.get('/assets/101/thumbnail' + query, headers=self.headers()).status_code, 400)
        self.assertEqual(self.client.get('/assets/101/thumbnail?library=family-a', headers=self.headers(Origin='https://evil.test')).status_code, 403)
        self.assertEqual(self.client.post('/assets/101/media?library=family-a', headers=self.headers()).status_code, 403)


if __name__ == '__main__':
    unittest.main()
