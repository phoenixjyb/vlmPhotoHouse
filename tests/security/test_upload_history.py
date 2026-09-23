"""Current-account receipt reads; no filesystem or processing side effects."""
from contextlib import closing
from unittest.mock import patch
import unittest
import test_upload as fixture
from app.access.service import AccessDenied, AccessService
from app.access.transport import COOKIE


class UploadHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.UploadTests.setUpClass()

    @classmethod
    def tearDownClass(cls): fixture.UploadTests.tearDownClass()

    def setUp(self):
        self.f = fixture.UploadTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.client = self.f.client()
        self.headers = {'Authorization': 'Bearer ' + self.f.member_token}

    def get(self, path='/uploads', **kwargs):
        return self.client.get(path, headers=kwargs.pop('headers', self.headers), **kwargs)

    def mutate(self, sql, args=()):
        with closing(self.f.connection()) as db:
            db.execute(sql, args); db.commit()

    def accepted(self, pad=b'', token=None):
        return self.f.upload(fixture.png(64, 64, pad), token=token)['asset_id']

    def test_own_receipts_only_no_paths_names_hashes_or_work(self):
        aid = self.accepted(); self.accepted(b'owner', self.f.owner_token)
        before = [tuple(r) for r in self.f.rows('SELECT * FROM tasks')]
        original_stat = fixture.Path.stat
        def no_media_stat(path, *args, **kwargs):
            if path.is_relative_to(self.f.incoming) or path.is_relative_to(self.f.originals):
                raise AssertionError('No media IO')
            return original_stat(path, *args, **kwargs)
        with patch('pathlib.Path.stat', no_media_stat):
            result = self.get()
        self.assertEqual(200, result.status_code)
        self.assertEqual(result.json(), {'page': 1, 'page_size': 10, 'total': 1, 'items': [{
            'asset_id': aid, 'created_at': fixture.NOW, 'bytes': len(fixture.png(64, 64)),
            'kind': 'image', 'state': 'awaiting_review', 'library_id': None}]})
        self.assertEqual(before, [tuple(r) for r in self.f.rows('SELECT * FROM tasks')])
        self.assertIn('no-store', result.headers['cache-control'])

    def test_available_only_with_current_destination_access_and_active_asset(self):
        aid = self.accepted()
        self.mutate("UPDATE access_uploads SET state='assigned' WHERE asset_id=?", (aid,))
        self.mutate("INSERT INTO access_asset_libraries VALUES (?,'family-a')", (aid,))
        self.assertEqual('available', self.get().json()['items'][0]['state'])
        self.assertEqual('family-a', self.get().json()['items'][0]['library_id'])
        self.mutate("UPDATE assets SET status='suppressed' WHERE id=?", (aid,))
        self.assertEqual('unavailable', self.get().json()['items'][0]['state'])
        self.assertIsNone(self.get().json()['items'][0]['library_id'])

    def test_foreign_destination_not_disclosed_even_for_own_upload(self):
        aid = self.accepted()
        self.mutate("INSERT INTO access_libraries(id,state,bootstrap_operator) SELECT 'other-private-library','active',bootstrap_operator FROM access_libraries WHERE id='family-a'")
        self.mutate("UPDATE access_uploads SET state='assigned' WHERE asset_id=?", (aid,))
        self.mutate("INSERT INTO access_asset_libraries VALUES (?,'other-private-library')", (aid,))
        result = self.get()
        self.assertEqual('unavailable', result.json()['items'][0]['state'])
        self.assertNotIn('other-private-library', result.text)
        self.assertIsNone(result.json()['items'][0]['library_id'])

    def test_pagination_uses_receipt_order_and_dedup_does_not_add_history(self):
        ids = [self.accepted(str(i).encode()) for i in range(12)]
        self.accepted(b'0')
        first, second = self.get().json(), self.get('/uploads?page=2').json()
        self.assertEqual(12, first['total'])
        self.assertEqual(ids[::-1][:10], [r['asset_id'] for r in first['items']])
        self.assertEqual(ids[::-1][10:], [r['asset_id'] for r in second['items']])
        self.assertEqual([], self.get('/uploads?page=100000').json()['items'])

    def test_revocation_expiry_and_disabled_account_deny_history(self):
        self.accepted()
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (self.f.member_id,))
        self.assertEqual(401, self.get().status_code)
        self.mutate("UPDATE access_memberships SET status='approved',expires_at=? WHERE account_id=?", (fixture.NOW, self.f.member_id))
        self.assertEqual(401, self.get().status_code)
        self.mutate("UPDATE access_memberships SET expires_at=NULL WHERE account_id=?", (self.f.member_id,))
        self.mutate("UPDATE access_accounts SET state='disabled' WHERE id=?", (self.f.member_id,))
        self.assertEqual(401, self.get().status_code)

    def test_session_logout_and_anonymous_deny(self):
        self.accepted()
        self.assertEqual(401, self.get(headers={}).status_code)
        with closing(self.f.connection()) as db: AccessService(db, clock=lambda: fixture.NOW).logout(self.f.member_token)
        self.assertEqual(401, self.get().status_code)

    def test_browser_cookie_requires_same_origin_and_cannot_mix_credentials(self):
        self.accepted()
        cookie = {'Cookie': COOKIE + '=' + self.f.member_token}
        self.assertEqual(403, self.get(headers=cookie).status_code)
        self.assertEqual(200, self.get(headers={**cookie, 'Sec-Fetch-Site': 'same-origin'}).status_code)
        self.assertEqual(403, self.get(headers={**cookie, 'Origin': 'https://other.test'}).status_code)
        self.assertEqual(401, self.get(headers={**cookie, **self.headers}).status_code)

    def test_query_allowlist_and_upload_post_query_remain_closed(self):
        for suffix in ('?page=0', '?page=-1', '?page=100001', '?page=x', '?page=1&page=2', '?account_id=other', '?library=family-a', '?token=secret'):
            self.assertEqual(400, self.get('/uploads' + suffix).status_code, suffix)
        self.assertEqual(400, self.client.post('/uploads?page=1', headers=self.f.headers(), content=fixture.png(64,64)).status_code)
        self.assertEqual(403, self.client.head('/uploads', headers=self.headers).status_code)

    def test_disabled_runtime_returns_unavailable_without_receipts(self):
        self.accepted()
        self.assertEqual(503, self.f.client(upload_runtime=None).get('/uploads', headers=self.headers).status_code)

    def test_inconsistent_pending_mapping_fails_closed(self):
        aid = self.accepted()
        self.mutate("INSERT INTO access_asset_libraries VALUES (?,'family-a')", (aid,))
        item = self.get().json()['items'][0]
        self.assertEqual('unavailable', item['state']); self.assertIsNone(item['library_id'])
