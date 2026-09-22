"""HTTP and transaction coverage for named libraries and reviewed asset moves.

The fixture is deliberately composed from the synthetic library-read database.  It exercises the
same bearer/cookie transport used by the browser while keeping all media and SQL local.
"""
from contextlib import closing
import json
import sys
import uuid
from pathlib import Path
import unittest
from unittest.mock import patch

import test_promotion as _promotion_fixture

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.transport import COOKIE, csrf_token, TransportError
from app.access.service import AccessDenied, AccessService
from test_access_foundation import NOW


class LibraryOrganizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.access.library_organization import LibraryOrganization, create_presets
        cls.LibraryOrganization = LibraryOrganization
        cls.create_presets = create_presets
        _promotion_fixture.PromotionTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        _promotion_fixture.PromotionTests.tearDownClass()

    def setUp(self):
        self.fixture = _promotion_fixture.PromotionTests('test_promotion_moves_the_file_and_makes_the_photo_visible')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        for name in ('path', 'now', 'client', 'owner_token', 'other_token', 'member_token',
                     'owner_id', 'other_id', 'member_id', 'connection', 'mutate', 'rows'):
            if hasattr(self.fixture, name):
                setattr(self, name, getattr(self.fixture, name))
        self.client = self._app_client()
        self.addCleanup(self.client.close)

    def _app_client(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        return TestClient(create_app(access_runtime=self.fixture.access),
                          base_url='https://photohouse.test', client=('192.0.2.41', 23457))

    def headers(self, token=None, **extra):
        values = {'Authorization': 'Bearer ' + (token or self.owner_token)}
        values.update(extra)
        return values

    def add_destination(self, library='documents'):
        """Give the existing operator an explicit owner membership for a destination preset."""
        self.mutate('INSERT OR IGNORE INTO access_libraries(id,state,bootstrap_operator) VALUES (?,\'active\',?)',
                    (library, self.owner_id))
        self.mutate('''INSERT OR IGNORE INTO access_memberships
            (account_id,library_id,status,role,revision,expires_at,originals,approved_by)
            VALUES (?,?,'approved','owner',1,NULL,0,?)''',
                    (self.owner_id, library, self.owner_id))

    def move_review(self, asset_ids, destination='documents', token=None, library='family-a'):
        body = {'asset_ids': ','.join(str(value) for value in asset_ids), 'destination': destination}
        return self.client.post('/admin/library-transfers/review?library=' + library,
                                headers=self.headers(token), json=body)

    def test_failed_move_diagnostics_do_not_log_request_or_exception_contents(self):
        from app.access.library_organization import _call, LibraryOrganization
        with patch.object(LibraryOrganization, 'confirm', side_effect=RuntimeError('private-token-and-path')):
            with self.assertLogs('app.access.library_organization', level='WARNING') as logs:
                with self.assertRaises(RuntimeError):
                    _call(None, 'confirm', 'private-token', 'private-library', 'private-plan')
        output=' '.join(logs.output)
        self.assertIn('action=confirm kind=RuntimeError', output)
        self.assertNotIn('private', output)

    def test_create_presets_is_explicit_transaction_operator_only_and_idempotent(self):
        self.mutate("UPDATE access_libraries SET bootstrap_operator=? WHERE id='family-b'", (self.owner_id,))
        self.mutate("UPDATE access_memberships SET account_id=?,approved_by=? WHERE library_id='family-b'",
                    (self.owner_id, self.owner_id))
        with closing(self.connection()) as db:
            access = AccessService(db, clock=lambda: NOW)
            with access._transaction(write=True):
                first = type(self).create_presets(access, self.owner_id)
            with access._transaction(write=True):
                second = type(self).create_presets(access, self.owner_id)
            self.assertEqual(len(first['created']), 5)
            self.assertEqual(second['created'], [])
            self.assertEqual(first['items'], second['items'])
            self.assertEqual(first['items'][0]['title'], 'Yanbo’s Work')
            self.assertEqual(db.execute(
                'SELECT count(*) FROM access_memberships WHERE account_id=?', (self.owner_id,)).fetchone()[0], 7)
            with self.assertRaises(AccessDenied):
                with access._transaction(write=True):
                    type(self).create_presets(access, self.member_id)

    def test_full_50_asset_review_and_confirm_fits_bounded_transport(self):
        self.add_destination()
        for asset in range(1000,1050):
            self.mutate("INSERT INTO assets(id,path,hash_sha256,status,mime) VALUES (?,?,?,'active','video/mp4')", (asset,str(asset),str(asset)))
            self.mutate("INSERT INTO access_asset_libraries VALUES (?,'family-a')", (asset,))
        response=self.move_review(list(range(1000,1050)))
        self.assertEqual(response.status_code,200,response.text)
        result=self.client.post('/admin/library-transfers/confirm?library=family-a', headers=self.headers(),json={'plan':response.json()['plan']})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['asset_count'],50)
        self.assertEqual(len(self.rows("SELECT asset_id FROM access_asset_libraries WHERE library_id='documents'")),50)
        self.assertEqual(self.move_review(list(range(1000,1051))).status_code,400)

    def test_revoked_session_cannot_replay_confirm(self):
        self.add_destination()
        response=self.move_review([900])
        self.assertEqual(response.status_code,200,response.text)
        self.mutate('UPDATE access_sessions SET revoked=1')
        result=self.client.post('/admin/library-transfers/confirm?library=family-a',headers=self.headers(),json={'plan':response.json()['plan']})
        self.assertEqual(result.status_code,401)
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=900')[0][0],'family-a')

    def test_create_presets_does_not_claim_existing_foreign_library(self):
        self.mutate("INSERT INTO access_libraries(id,state,bootstrap_operator) VALUES ('documents','active',?)",
                    (self.other_id,))
        before = self.rows('SELECT bootstrap_operator,state FROM access_libraries WHERE id=?', ('family-b',))[0]
        with closing(self.connection()) as db:
            access = AccessService(db, clock=lambda: NOW)
            with self.assertRaises((AccessDenied, TransportError)):
                with access._transaction(write=True):
                    type(self).create_presets(access, self.owner_id)
        self.assertEqual(self.rows('SELECT bootstrap_operator,state FROM access_libraries WHERE id=?', ('family-b',))[0], before)

    def test_catalogue_exposes_only_memberships_names_counts_and_can_create(self):
        self.add_destination()
        response = self.client.get('/library-catalogue', headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body['can_create'])
        self.assertEqual({item['id'] for item in body['items']}, {'family-a', 'documents'})
        self.assertEqual(next(item for item in body['items'] if item['id'] == 'documents')['title_zh'], '文档')
        for forbidden in ('path', 'hash', 'phone_login', 'account_id', 'bootstrap_operator'):
            self.assertNotIn(forbidden, response.text)
        member = self.client.get('/library-catalogue', headers=self.headers(self.member_token))
        self.assertEqual(member.status_code, 200, member.text)
        self.assertFalse(member.json()['can_create'])
        self.assertEqual([item['id'] for item in member.json()['items']], ['family-a'])

    def test_source_viewer_nonoperator_foreign_and_mixed_assets_are_rejected(self):
        self.add_destination()
        self.mutate("INSERT INTO assets(id,path,hash_sha256,status,mime,width,height) VALUES (901,'private-synthetic/901.jpg','private-hash-901','active','image/jpeg',640,480)")
        self.mutate("INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (901,'family-b')")
        cases = [
            (self.member_token, [900], (401, 403)),
            (self.other_token, [900], (401, 403)),
            (self.owner_token, [901], (401, 403)),
            (self.owner_token, [900, 901], (401, 403)),
        ]
        for token, ids, statuses in cases:
            with self.subTest(token=token, ids=ids):
                response = self.move_review(ids, token=token)
                self.assertIn(response.status_code, statuses, response.text)

    def test_review_confirm_transfers_story_hides_old_album_and_preserves_bytes(self):
        self.add_destination()
        original = self.rows('SELECT path,hash_sha256 FROM assets WHERE id=900')[0]
        story_id = str(uuid.uuid4())
        with closing(self.connection()) as db:
            db.execute('''INSERT INTO access_stories
                (id,asset_id,library_id,author_id,revision,title,text,language,byline,created_at,updated_at,deleted)
                VALUES (?,?,?,?,1,?,?,?,?,?,?,0)''',
                       (story_id, 900, 'family-a', self.owner_id, 'Trip', 'A story', 'en', 'Me', NOW, NOW))
            db.execute('''INSERT INTO access_story_revisions
                (story_id,revision,editor_id,mutation_id,request_digest,title,text,language,byline,occurred_at,deleted)
                VALUES (?,?,?,?,?,?,?,?,?,?,0)''',
                       (story_id, 1, self.owner_id, str(uuid.uuid4()), 'digest', 'Trip', 'A story', 'en', 'Me', NOW))
            db.execute("INSERT INTO albums(title,status,source_kind) VALUES ('Old album','draft','manual')")
            album_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            db.execute('INSERT INTO album_assets(album_id,asset_id,position) VALUES (?,900,1)', (album_id,))
            db.commit()
        reviewed = self.move_review([900])
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        plan = reviewed.json()['plan']
        self.assertEqual(reviewed.json()['story_count'], 1)
        self.assertEqual(self.client.post('/admin/library-transfers/confirm?library=family-a',
                                          headers=self.headers(), json={'plan': plan}).status_code, 200)
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=900')[0][0], 'documents')
        self.assertEqual(self.rows('SELECT library_id FROM access_stories WHERE id=?', (story_id,))[0][0], 'documents')
        self.assertEqual(self.rows('SELECT path,hash_sha256 FROM assets WHERE id=900')[0], original)
        self.assertEqual(self.client.get('/assets/900/stories?library=family-a', headers=self.headers()).status_code, 401)
        self.assertEqual(self.client.get('/assets/900/stories?library=documents', headers=self.headers()).status_code, 200)
        self.assertEqual(self.rows('SELECT count(*) FROM album_assets WHERE album_id=?', (album_id,))[0][0], 1)

    def test_stale_metadata_expiry_revoked_cookie_csrf_invalid_query_body_limit_and_replay(self):
        self.add_destination()
        reviewed = self.move_review([900])
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        plan = reviewed.json()['plan']
        self.mutate("UPDATE access_memberships SET revision=revision+1 WHERE account_id=? AND library_id='family-a'",
                    (self.owner_id,))
        self.assertEqual(self.client.post('/admin/library-transfers/confirm?library=family-a',
                                          headers=self.headers(), json={'plan': plan}).status_code, 409)

        self.mutate("UPDATE access_memberships SET revision=revision-1,expires_at=? WHERE account_id=? AND library_id='family-a'",
                    (NOW, self.owner_id))
        self.assertIn(self.move_review([900]).status_code, (401, 403))
        self.mutate("UPDATE access_memberships SET expires_at=NULL,status='approved' WHERE account_id=? AND library_id='family-a'",
                    (self.owner_id,))
        self.client.cookies.set(COOKIE, self.owner_token)
        self.assertEqual(self.client.post('/admin/library-transfers/review?library=family-a', json={}).status_code, 403)
        self.assertEqual(self.client.post('/admin/library-transfers/review?library=family-a',
                                          headers={'Origin': 'https://photohouse.test',
                                                   'X-CSRF-Token': csrf_token(self.owner_token)}, json={}).status_code, 400)
        self.client.cookies.clear()
        for path in ('/admin/library-transfers', '/admin/library-transfers?library=family-a&extra=x',
                     '/admin/library-transfers?library=', '/admin/library-transfers?library=' + 'a' * 129):
            self.assertIn(self.client.get(path, headers=self.headers()).status_code, (400, 401, 403))
        for body in ({}, {'asset_ids': '900'}, {'asset_ids': '1,' * 50, 'destination': 'documents'}):
            response = self.client.post('/admin/library-transfers/review?library=family-a',
                                        headers=self.headers(), json=body)
            self.assertIn(response.status_code, (400, 401, 403, 409))
        self.client.cookies.clear()

        # A valid plan is single-use at the state layer, while an exact retry is idempotent.
        self.mutate("UPDATE access_asset_libraries SET library_id='family-a' WHERE asset_id=900")
        fresh = self.move_review([900])
        self.assertEqual(fresh.status_code, 200, fresh.text)
        exact = self.client.post('/admin/library-transfers/confirm?library=family-a', headers=self.headers(),
                                 json={'plan': fresh.json()['plan']})
        self.assertEqual(exact.status_code, 200, exact.text)
        replay = self.client.post('/admin/library-transfers/confirm?library=family-a', headers=self.headers(),
                                  json={'plan': fresh.json()['plan']})
        self.assertEqual(replay.status_code, 200, replay.text)


if __name__ == '__main__':
    unittest.main()
