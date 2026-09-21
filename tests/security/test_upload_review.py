"""Protected HTTP review of member uploads.

These tests compose ``PromotionTests`` for its migrated synthetic database and file roots.  They
deliberately do not subclass it: importing this module must not discover and rerun the promotion
or operator-command suites.
"""
from contextlib import closing
from pathlib import Path
import sys
import unittest
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
import test_promotion as promotion_base
from app.access.transport import csrf_token, COOKIE
from app.access.media import MediaRuntime
from app.photo_delivery import PhotoCache


class UploadReviewTests(unittest.TestCase):
    """The review route is a library-scoped, owner/operator-only capability."""

    @classmethod
    def setUpClass(cls):
        promotion_base.PromotionTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        promotion_base.PromotionTests.tearDownClass()

    def setUp(self):
        self.fixture = promotion_base.PromotionTests(
            'test_promotion_moves_the_file_and_makes_the_photo_visible')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

        # Import the new runtime lazily so this file remains a pure composition test while the
        # backend feature is being developed in parallel.
        from app.access.upload_review import UploadReviewRuntime
        self.UploadReviewRuntime = UploadReviewRuntime
        self.runtime = UploadReviewRuntime(upload=self.fixture.uploads, photo_cache=None)
        self.client = TestClient(
            self._app(self.runtime), base_url='https://photohouse.test',
            client=('192.0.2.41', 23457))
        self.addCleanup(self.client.close)

    def _app(self, runtime=None, *, cache=None):
        from app.main import create_app
        if runtime is None:
            runtime = self.UploadReviewRuntime(upload=self.fixture.uploads, photo_cache=cache)
        return create_app(access_runtime=self.fixture.access,
                          upload_review_runtime=runtime)

    def _headers(self, token, **extra):
        values = {'Authorization': 'Bearer ' + token}
        values.update(extra)
        return values

    def _upload(self, data=None, filename='photo.png'):
        return self.fixture.upload(data or promotion_base.png(640, 480), filename=filename)

    def _rows(self, sql, args=()):
        return self.fixture.rows(sql, args)

    def _review(self, asset_id, token=None, library='family-a'):
        token = token or self.fixture.owner_token
        return self.client.post(
            f'/admin/uploads/{asset_id}/review?library={library}',
            headers=self._headers(token), json={})

    def _approve(self, asset_id, plan, token=None, library='family-a', **headers):
        token = token or self.fixture.owner_token
        values = self._headers(token, **headers)
        return self.client.post(
            f'/admin/uploads/{asset_id}/approve?library={library}',
            headers=values, json={'plan': plan})

    def test_owner_review_approve_moves_one_photo_and_makes_it_visible(self):
        uploaded = self._upload()
        asset_id = int(uploaded['asset_id'])
        self.assertNotIn(str(asset_id), self.fixture.gallery(self.fixture.owner_token))

        reviewed = self._review(asset_id)
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        body = reviewed.json()
        self.assertEqual(set(body), {
            'plan', 'asset_id', 'library_id', 'current_readers', 'current_original_readers'})
        self.assertIsInstance(body['plan'], str)
        self.assertEqual(body['asset_id'], str(asset_id))
        self.assertEqual(body['library_id'], 'family-a')
        self.assertNotIn('path', reviewed.text.lower())

        approved = self._approve(asset_id, body['plan'])
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json(), {
            'asset_id': str(asset_id), 'library_id': 'family-a', 'state': 'assigned'})
        self.assertIn(str(asset_id), self.fixture.gallery(self.fixture.owner_token))
        self.assertEqual(self._rows(
            'SELECT count(*) FROM access_provisioning_receipts')[0][0], 1)
        self.assertEqual(self._rows(
            'SELECT state FROM access_uploads WHERE asset_id=?', (asset_id,))[0][0], 'assigned')

    def test_list_is_paginated_and_reveals_only_reviewable_member_uploads(self):
        uploaded = [self._upload(data=promotion_base.png(320 + i, 240), filename=f'{i}.png')
                    for i in range(11)]
        response = self.client.get('/admin/uploads?library=family-a&page=1',
                                   headers=self._headers(self.fixture.owner_token))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['library_id'], 'family-a')
        self.assertEqual(body['page'], 1)
        self.assertEqual(body['page_size'], 10)
        self.assertEqual(body['total'], 11)
        self.assertTrue(body['can_review'])
        self.assertEqual(len(body['items']), 10)
        self.assertEqual(set(body['items'][0]),
                         {'id', 'uploader', 'created_at', 'bytes', 'width', 'height', 'preview_url'})
        self.assertNotIn(str(self.fixture.incoming), response.text)
        second_page = self.client.get('/admin/uploads?library=family-a&page=2',
                                      headers=self._headers(self.fixture.owner_token))
        self.assertEqual(second_page.status_code, 200, second_page.text)
        self.assertEqual(len(second_page.json()['items']), 1)
        self.assertEqual({item['id'] for item in body['items']} |
                         {item['id'] for item in second_page.json()['items']},
                         {str(item['asset_id']) for item in uploaded})

    def test_member_nonoperator_sees_empty_list_and_cannot_review_or_approve(self):
        uploaded = self._upload()
        listing = self.client.get('/admin/uploads?library=family-a&page=1',
                                  headers=self._headers(self.fixture.member_token))
        self.assertEqual(listing.status_code, 401, listing.text)
        self.assertIn(self._review(int(uploaded['asset_id']), self.fixture.member_token).status_code,
                      (401, 403, 404))

    def test_owner_role_without_operator_registration_sees_no_review_records(self):
        uploaded = self._upload()
        with closing(self.fixture.connection()) as db:
            db.execute("UPDATE access_memberships SET role='owner' WHERE account_id=? AND library_id=?",
                       (self.fixture.member_id, 'family-a'))
            db.commit()
        listing = self.client.get('/admin/uploads?library=family-a&page=1',
                                  headers=self._headers(self.fixture.member_token))
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertFalse(listing.json()['can_review'])
        self.assertEqual(listing.json()['items'], [])
        self.assertNotIn(str(uploaded['asset_id']), listing.text)

    def test_foreign_library_and_foreign_upload_are_denied_without_metadata(self):
        uploaded = self._upload()
        asset_id = int(uploaded['asset_id'])
        for token, library in ((self.fixture.other_token, 'family-b'),
                               (self.fixture.owner_token, 'family-b')):
            with self.subTest(token=token, library=library):
                response = self.client.get(f'/admin/uploads?library={library}&page=1',
                                           headers=self._headers(token))
                self.assertIn(response.status_code, (200, 401, 403, 404))
                self.assertNotIn(str(asset_id), response.text)
                detail = self._review(asset_id, token=token, library=library)
                self.assertIn(detail.status_code, (401, 403, 404))
                self.assertNotIn(str(asset_id), detail.text)

    def test_revoked_uploader_cannot_be_reviewed_or_approved(self):
        uploaded = self._upload()
        asset_id = int(uploaded['asset_id'])
        with closing(self.fixture.connection()) as db:
            db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                       (self.fixture.member_id,))
            db.commit()
        response = self.client.get('/admin/uploads?library=family-a&page=1',
                                   headers=self._headers(self.fixture.owner_token))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['items'], [])
        self.assertIn(self._review(asset_id).status_code, (401, 403, 404))

    def test_plan_is_bound_to_actor_library_asset_and_current_revisions(self):
        uploaded = self._upload()
        asset_id = int(uploaded['asset_id'])
        plan = self._review(asset_id).json()['plan']
        envelope = json.loads(plan)
        tampered_seal = dict(envelope)
        tampered_seal['seal'] = '0' * len(tampered_seal['seal'])
        tampered_target = json.loads(plan)
        tampered_target['plan']['target']['library_id'] = 'family-b'
        tampered_expected = json.loads(plan)
        tampered_expected['plan']['expected']['current_readers'] += 1
        cases = [
            ('tampered-seal', json.dumps(tampered_seal), self.fixture.owner_token, 'family-a'),
            ('tampered-target', json.dumps(tampered_target), self.fixture.owner_token, 'family-a'),
            ('tampered-expected', json.dumps(tampered_expected), self.fixture.owner_token, 'family-a'),
            ('foreign-library', plan, self.fixture.owner_token, 'family-b'),
            ('foreign-actor', plan, self.fixture.other_token, 'family-a'),
        ]
        for name, candidate, token, library in cases:
            with self.subTest(name=name):
                response = self._approve(asset_id, candidate, token=token, library=library)
                self.assertIn(response.status_code, (400, 401, 403, 404, 409))
        with closing(self.fixture.connection()) as db:
            db.execute('UPDATE access_memberships SET revision=revision+1 WHERE account_id=?',
                       (self.fixture.owner_id,))
            db.commit()
        stale = self._approve(asset_id, plan)
        self.assertEqual(stale.status_code, 409, stale.text)

    def test_uploader_revocation_and_expiry_between_review_and_approval_are_rejected(self):
        uploaded = self._upload()
        asset_id = int(uploaded['asset_id'])
        plan = self._review(asset_id).json()['plan']
        with closing(self.fixture.connection()) as db:
            db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                       (self.fixture.member_id,))
            db.commit()
        self.assertIn(self._approve(asset_id, plan).status_code, (401, 409))

        with closing(self.fixture.connection()) as db:
            db.execute("UPDATE access_memberships SET status='approved' WHERE account_id=?",
                       (self.fixture.member_id,))
            db.commit()
        uploaded = self._upload(data=promotion_base.png(641, 480), filename='expiry.png')
        asset_id = int(uploaded['asset_id'])
        plan = self._review(asset_id).json()['plan']
        object.__setattr__(self.fixture.access, 'clock', lambda: promotion_base.NOW + 901)
        self.assertEqual(self._approve(asset_id, plan).status_code, 409)

    def test_actor_revocation_invalidates_a_plan(self):
        uploaded = self._upload()
        asset_id = int(uploaded['asset_id'])
        plan = self._review(asset_id).json()['plan']
        with closing(self.fixture.connection()) as db:
            db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id=?",
                       (self.fixture.owner_id, 'family-a'))
            db.commit()
        revoked = self._approve(asset_id, plan)
        self.assertIn(revoked.status_code, (401, 403, 404, 409))

    def test_logout_invalidates_a_plan(self):
        uploaded = self._upload()
        asset_id = int(uploaded['asset_id'])
        plan = self._review(asset_id).json()['plan']
        logout = self.client.post('/auth/logout', headers=self._headers(self.fixture.owner_token))
        self.assertEqual(logout.status_code, 200, logout.text)
        after_logout = self._approve(asset_id, plan)
        self.assertIn(after_logout.status_code, (401, 403, 404, 409))

    def test_exact_retry_is_idempotent_and_emits_one_receipt(self):
        uploaded = self._upload()
        asset_id = int(uploaded['asset_id'])
        plan = self._review(asset_id).json()['plan']
        first = self._approve(asset_id, plan)
        retry = self._approve(asset_id, plan)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()['state'], 'assigned')
        self.assertEqual(self._rows('SELECT count(*) FROM access_provisioning_receipts')[0][0], 1)
        self.assertEqual([p for p in self.fixture.incoming.rglob('*') if p.is_file()], [])

    def test_replay_after_offline_unassignment_is_rejected(self):
        uploaded = self._upload()
        asset_id = int(uploaded['asset_id'])
        plan = self._review(asset_id).json()['plan']
        approved = self._approve(asset_id, plan)
        self.assertEqual(approved.status_code, 200, approved.text)

        # Simulate the reviewed offline inverse operation that removes the current mapping and
        # returns the bytes to the incoming root. The original web plan must remain unusable.
        unassign = self.fixture.planned('unassign', library_id='family-a',
                                         operator_account_id=self.fixture.owner_id,
                                         asset_ids=[asset_id])
        promotion_base.unassign_assets(unassign, review=self.fixture.review(unassign),
                                       clock=lambda: promotion_base.NOW)
        replay = self._approve(asset_id, plan)
        self.assertEqual(replay.status_code, 409, replay.text)

    def test_disabled_default_is_503_and_preview_requires_configured_cache(self):
        from app.main import create_app
        disabled = TestClient(create_app(access_runtime=self.fixture.access),
                              base_url='https://photohouse.test')
        self.addCleanup(disabled.close)
        response = disabled.get('/admin/uploads?library=family-a&page=1',
                                headers=self._headers(self.fixture.owner_token))
        self.assertEqual(response.status_code, 503)
        uploaded = self._upload()
        preview = self.client.get(f"/admin/uploads/{uploaded['asset_id']}/preview?library=family-a",
                                  headers=self._headers(self.fixture.owner_token))
        self.assertIn(preview.status_code, (403, 404, 503))
        ordinary = self.client.get(f"/assets/{uploaded['asset_id']}/thumbnail?library=family-a",
                                   headers=self._headers(self.fixture.owner_token))
        self.assertIn(ordinary.status_code, (403, 404, 503))

    def test_configured_media_runtime_still_denies_incoming_thumbnail(self):
        from app.main import create_app
        from app.access.media import MediaRuntime
        runtime = self.UploadReviewRuntime(upload=self.fixture.uploads, photo_cache=None)
        app = create_app(access_runtime=self.fixture.access,
                          media_runtime=MediaRuntime((self.fixture.originals,), self.fixture.root / 'derived'),
                          upload_review_runtime=runtime)
        client = TestClient(app, base_url='https://photohouse.test')
        self.addCleanup(client.close)
        uploaded = self._upload()
        response = client.get(f"/assets/{uploaded['asset_id']}/thumbnail?library=family-a",
                              headers=self._headers(self.fixture.owner_token))
        self.assertIn(response.status_code, (401, 403, 404))

    def test_runtime_configuration_requires_explicit_review_opt_in(self):
        from app.access.runtime import RuntimeConfiguration
        disabled = RuntimeConfiguration(
            self.fixture.path.resolve(), 'https://photohouse.test',
            (self.fixture.originals,), self.fixture.root / 'derived',
            incoming_root=self.fixture.incoming).build_app()
        self.assertIsNone(getattr(disabled.state, 'upload_review_runtime', None))
        enabled = RuntimeConfiguration(
            self.fixture.path.resolve(), 'https://photohouse.test',
            (self.fixture.originals,), self.fixture.root / 'derived',
            incoming_root=self.fixture.incoming, upload_review_enabled=True).build_app()
        self.assertIsInstance(enabled.state.upload_review_runtime, self.UploadReviewRuntime)

    def test_cookie_writes_require_standard_csrf_and_preview_is_jpeg(self):
        uploaded = self._upload()
        cache = PhotoCache(self.fixture.root / 'photo-cache')
        runtime = self.UploadReviewRuntime(upload=self.fixture.uploads, photo_cache=cache)
        client = TestClient(self._app(runtime), base_url='https://photohouse.test')
        self.addCleanup(client.close)
        client.cookies.set(COOKIE, self.fixture.owner_token)
        no_csrf = client.post(
            f"/admin/uploads/{uploaded['asset_id']}/review?library=family-a")
        self.assertEqual(no_csrf.status_code, 403)
        csrf = csrf_token(self.fixture.owner_token)
        with patch.object(PhotoCache, 'render_opened', return_value=b'\xff\xd8\xff\xd9'):
            reviewed = client.post(
                f"/admin/uploads/{uploaded['asset_id']}/review?library=family-a",
                headers={'Origin': 'https://photohouse.test', 'X-CSRF-Token': csrf}, json={})
            self.assertEqual(reviewed.status_code, 200, reviewed.text)
            preview = client.get(
                f"/admin/uploads/{uploaded['asset_id']}/preview?library=family-a",
                headers={'Origin': 'https://photohouse.test'})
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.headers['content-type'].split(';')[0], 'image/jpeg')
        self.assertNotIn(str(self.fixture.incoming), preview.text)

    def test_preview_rechecks_actor_and_uploader_after_decode(self):
        cache = PhotoCache(self.fixture.root / 'photo-cache')
        runtime = self.UploadReviewRuntime(upload=self.fixture.uploads, photo_cache=cache)
        client = TestClient(self._app(runtime), base_url='https://photohouse.test')
        self.addCleanup(client.close)
        uploaded = self._upload()

        def revoke_actor(*_args):
            with closing(self.fixture.connection()) as db:
                db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id=?",
                           (self.fixture.owner_id, 'family-a'))
                db.commit()
            return b'\xff\xd8\xff\xd9'

        with patch.object(PhotoCache, 'render_opened', side_effect=revoke_actor):
            response = client.get(f"/admin/uploads/{uploaded['asset_id']}/preview?library=family-a",
                                  headers=self._headers(self.fixture.owner_token))
        self.assertIn(response.status_code, (401, 403, 409))
        self.assertNotEqual(response.headers.get('content-type'), 'image/jpeg')

    def test_preview_rechecks_uploader_after_decode(self):
        cache = PhotoCache(self.fixture.root / 'photo-cache')
        runtime = self.UploadReviewRuntime(upload=self.fixture.uploads, photo_cache=cache)
        client = TestClient(self._app(runtime), base_url='https://photohouse.test')
        self.addCleanup(client.close)
        uploaded = self._upload()

        def revoke_uploader(*_args):
            with closing(self.fixture.connection()) as db:
                db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id=?",
                           (self.fixture.member_id, 'family-a'))
                db.commit()
            return b'\xff\xd8\xff\xd9'

        with patch.object(PhotoCache, 'render_opened', side_effect=revoke_uploader):
            response = client.get(f"/admin/uploads/{uploaded['asset_id']}/preview?library=family-a",
                                  headers=self._headers(self.fixture.owner_token))
        self.assertIn(response.status_code, (401, 403, 409))
        self.assertNotEqual(response.headers.get('content-type'), 'image/jpeg')


if __name__ == '__main__':
    unittest.main()
