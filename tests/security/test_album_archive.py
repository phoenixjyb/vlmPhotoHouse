"""Archiving an album against migrated synthetic SQLite and real ASGI routes.

The properties that matter: archiving hides an album without deleting anything, restoring brings
it back, and the pair is revision-bound so two owners cannot silently lose a change.
"""
import unittest
import uuid
import test_library_reads as fixture

# A sentinel, so `token=None` means "no credential at all" rather than falling back to the owner.
# `token or self.token` silently authenticated the denial case and made it pass as a 200.
_AS_OWNER = object()


class AlbumArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls): fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.f = fixture.LibraryReadTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.client = self.f.client
        self.token = self.f.owner_token
        self.member = self.f.member_token

    def headers(self, token=_AS_OWNER):
        if token is None:
            return {}
        return {'Authorization': 'Bearer ' + (self.token if token is _AS_OWNER else token)}

    def body(self, **changes):
        return {'title': 'Our family', 'title_zh': '家人的时光', 'description': 'A story',
                'theme': 'trip', 'asset_ids': '101,102', 'cover_asset_id': '102',
                'mutation_id': str(uuid.uuid4()), **changes}

    def create(self, body=None, token=_AS_OWNER, library='family-a'):
        return self.client.post('/admin/albums?library=' + library,
                                headers=self.headers(token), json=body or self.body())

    def listing(self, token=_AS_OWNER, library='family-a', page=1):
        return self.client.get(f'/library-albums?library={library}&page={page}',
                               headers=self.headers(token))

    def archive(self, album, token=_AS_OWNER, library='family-a', revision=None):
        return self.client.post(f'/admin/albums/{album["id"]}/archive?library={library}',
                                headers=self.headers(token),
                                json={'revision': revision or album['revision']})

    def restore(self, album, token=_AS_OWNER, library='family-a'):
        # No revision: an archived album cannot be edited, so there is no lost update to guard
        # against, and the client could not obtain one anyway.
        return self.client.post(f'/admin/albums/{album["id"]}/restore?library={library}',
                                headers=self.headers(token), json={})

    def ids(self, response=None, token=_AS_OWNER):
        return [item['id'] for item in (response or self.listing(token)).json()['items']]

    def revision_of(self, album):
        with self.f.connection() as db:
            return db.execute('SELECT revision FROM access_album_libraries WHERE album_id=?',
                              (album['id'],)).fetchone()[0]

    def status_of(self, album):
        with self.f.connection() as db:
            return db.execute('SELECT status FROM albums WHERE id=?', (album['id'],)).fetchone()[0]

    def test_archiving_hides_the_album_and_restoring_brings_it_back(self):
        album = self.create().json()
        self.assertIn(album['id'], self.ids())
        self.assertEqual(self.archive(album).status_code, 200)
        self.assertNotIn(album['id'], self.ids(), 'an archived album leaves the list')
        self.assertEqual(self.status_of(album), 'archived')
        # The archive bumped the stored revision, which is the evidence it consumed one.
        self.assertEqual(self.revision_of(album), 2)
        self.assertEqual(self.restore(album).status_code, 200)
        self.assertIn(album['id'], self.ids(), 'a restored album returns to the list')
        self.assertEqual(self.status_of(album), 'draft')

    def test_archiving_deletes_nothing(self):
        """The whole point: a mistake is put away, not destroyed."""
        album = self.create().json()
        self.archive(album)
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM albums WHERE id=?',
                                        (album['id'],)).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM album_assets WHERE album_id=?',
                                        (album['id'],)).fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT count(*) FROM access_album_libraries WHERE album_id=?',
                                        (album['id'],)).fetchone()[0], 1)

    def test_an_archived_album_is_unreadable_while_archived(self):
        """Hiding is not cosmetic: every read refuses it, not just the list."""
        album = self.create().json()
        self.archive(album)
        # The edit path resolves through the same draft-only fetch, so it refuses too.
        put = self.client.put('/admin/albums/' + album['id'] + '?library=family-a',
                              headers=self.headers(),
                              json={'title': 'Renamed', 'title_zh': '', 'description': '',
                                    'theme': 'trip', 'asset_ids': '101',
                                    'cover_asset_id': '101', 'revision': album['revision']})
        self.assertEqual(put.status_code, 401)

    def test_it_refuses_a_stale_revision(self):
        album = self.create().json()
        self.assertEqual(self.archive(album, revision='0' * 64).status_code, 409)
        self.assertIn(album['id'], self.ids(), 'a refused archive changes nothing')

    def test_it_refuses_a_no_op_in_either_direction(self):
        album = self.create().json()
        self.assertEqual(self.restore(album).status_code, 409, 'a draft is not archived')
        self.archive(album)
        # The state check runs before the revision check, so a stale revision still reports the
        # state rather than a conflict: the album is simply not in the library any more.
        self.assertEqual(self.archive(album).status_code, 409,
                         'an archived album is not in the library')
        self.assertEqual(self.restore(album).status_code, 200)
        self.assertEqual(self.restore(album).status_code, 409, 'a restored album is not archived')

    def test_it_requires_the_owner(self):
        album = self.create().json()
        self.assertEqual(self.archive(album, token=self.member).status_code, 401)
        self.assertEqual(self.archive(album, token=self.f.other_token).status_code, 401)
        self.assertEqual(self.archive(album, token=None).status_code, 401)
        self.assertIn(album['id'], self.ids())

    def test_it_refuses_a_missing_or_foreign_album(self):
        album = self.create().json()
        self.assertEqual(self.archive({'id': '999999', 'revision': album['revision']}).status_code, 401)
        self.assertEqual(self.archive(album, library='family-b').status_code, 401)

    def archived_list(self, token=_AS_OWNER, library='family-a'):
        return self.client.get(f'/admin/albums/archived?library={library}',
                               headers=self.headers(token))

    def test_the_owner_can_find_an_archived_album_to_restore_it(self):
        """Without this read, archiving would hide an album with no way back."""
        album = self.create().json()
        self.assertEqual(self.archived_list().json()['total'], 0)
        self.archive(album)
        body = self.archived_list().json()
        self.assertEqual([item['id'] for item in body['items']], [album['id']])
        self.assertEqual(body['items'][0]['title'], 'Our family')
        # And restoring takes it back out of the recovery list.
        self.assertEqual(self.restore(album).status_code, 200)
        self.assertEqual(self.archived_list().json()['total'], 0)

    def test_the_archived_list_is_owner_only(self):
        album = self.create().json()
        self.archive(album)
        for token in (self.member, self.f.other_token, None):
            with self.subTest(token='member' if token == self.member else token):
                self.assertEqual(self.archived_list(token=token).status_code, 401)

    def test_the_change_is_audited(self):
        album = self.create().json()
        self.archive(album)
        with self.f.connection() as db:
            rows = db.execute("SELECT action FROM access_audit WHERE action LIKE 'album.archive%'").fetchall()
        self.assertEqual(rows, [('album.archive.' + album['id'],)])
