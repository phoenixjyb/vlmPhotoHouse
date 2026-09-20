"""Protected gallery media filtering over the existing synthetic access fixture."""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
import test_library_reads as fixture
from app.access.transport import AccessRuntime
from app.main import create_app
from test_access_foundation import NOW


class GalleryMediaFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-gallery-media-filter-')
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'synthetic.sqlite'
        with closing(sqlite3.connect(self.path)) as db:
            fixture.LibraryReadTests.template.backup(db)
            db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at)
                VALUES (104,'private-synthetic/104.mp4','private-hash-104','active','video/mp4',640,480,'2026-01-03')''')
            db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at)
                VALUES (105,'private-synthetic/105.jpg','private-hash-105','active','image/jpeg',640,480,'2026-01-02T12:00:00')''')
            db.execute('INSERT INTO access_asset_libraries VALUES (104,\'family-a\')')
            db.execute('INSERT INTO access_asset_libraries VALUES (105,\'family-a\')')
            db.commit()
        runtime = AccessRuntime(self.connection, 'https://photohouse.test', clock=lambda: NOW)
        self.client = TestClient(create_app(access_runtime=runtime), base_url='https://photohouse.test')
        self.client.headers['Sec-Fetch-Site'] = 'same-origin'
        self.addCleanup(self.client.close)
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start()
            self.addCleanup(guard.stop)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path)
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
        finally:
            db.close()

    def mutate(self, sql, args=()):
        with self.connection() as db:
            db.execute(sql, args)
            db.commit()

    def get(self, path, token=None):
        token = token or fixture.LibraryReadTests.member_token
        return self.client.get(path, headers={'Authorization': 'Bearer ' + token})

    def test_default_and_all_preserve_existing_response_and_original_grant(self):
        default = self.get('/assets?library=family-a').json()
        explicit = self.get('/assets?library=family-a&media=all').json()
        self.assertEqual(default, explicit)
        self.mutate('UPDATE access_memberships SET originals=1 WHERE account_id=?',
                    (fixture.LibraryReadTests.member_id,))
        self.assertTrue(self.get('/assets?library=family-a&media=video').json()['originals_allowed'])

    def test_mime_filter_counts_and_pages_before_pagination(self):
        self.mutate("UPDATE assets SET mime='video/mp4' WHERE id=101")
        all_first = self.get('/assets?library=family-a&page_size=2').json()
        self.assertEqual([item['id'] for item in all_first['items']], ['104', '105'])
        videos = self.get('/assets?library=family-a&media=video&page_size=1').json()
        self.assertEqual((videos['total'], [item['id'] for item in videos['items']]), (2, ['104']))
        self.assertEqual([item['id'] for item in
                          self.get('/assets?library=family-a&media=video&page=2&page_size=1').json()['items']],
                         ['101'])
        images = self.get('/assets?library=family-a&media=image&page_size=1').json()
        self.assertEqual((images['total'], [item['id'] for item in images['items']]), (2, ['105']))

    def test_filter_excludes_inactive_and_foreign_scope_rows(self):
        self.mutate("INSERT INTO assets(id,path,hash_sha256,status,mime,taken_at) VALUES (106,'private/106.mp4','hash-106','hidden','video/mp4','2026-01-04')")
        self.mutate("INSERT INTO assets(id,path,hash_sha256,status,mime,taken_at) VALUES (107,'private/107.mp4','hash-107','active','video/mp4','2026-01-05')")
        self.mutate('INSERT INTO access_asset_libraries VALUES (106,\'family-a\')')
        self.mutate('INSERT INTO access_asset_libraries VALUES (107,\'family-b\')')
        result = self.get('/assets?library=family-a&media=video').json()
        self.assertNotIn('106', [item['id'] for item in result['items']])
        self.assertNotIn('107', [item['id'] for item in result['items']])
        self.assertEqual(result['total'], 1)
        self.assertEqual([item['id'] for item in result['items']], ['104'])

    def test_filter_uses_same_case_sensitive_kind_as_response(self):
        self.mutate("UPDATE assets SET mime='VIDEO/mp4' WHERE id=104")
        response = self.get('/assets?library=family-a&media=video').json()
        self.assertEqual(response['total'], 0)
        self.assertEqual(response['items'], [])

    def test_invalid_duplicate_and_injection_media_are_bad_requests(self):
        for query in ('media=', 'media=audio', 'media=IMAGE', 'media=video%27%20OR%201%3D1',
                      'media=image&media=video'):
            self.assertEqual(self.get('/assets?library=family-a&' + query).status_code, 400)

    def test_denial_and_revocation_still_precede_filtered_gallery(self):
        self.assertEqual(self.client.get('/assets?library=family-a&media=video').status_code, 401)
        self.assertEqual(self.get('/assets?library=family-b&media=video').status_code, 401)
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                    (fixture.LibraryReadTests.member_id,))
        self.assertEqual(self.get('/assets?library=family-a&media=video').status_code, 401)


if __name__ == '__main__':
    unittest.main()
