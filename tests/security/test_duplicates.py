"""Member-visible exact-duplicate groups against migrated synthetic SQLite and real ASGI routes.

The properties that matter: a group counts only the **library's own** copies, a copy that is
deleted, foreign or unmapped never counts or appears, and the response carries no path, filename
or content hash.
"""
import json
import unittest
import test_library_reads as fixture

# A sentinel, so `token=None` means "no credential at all" rather than falling back to the
# member. An `or` default on a credential makes a denial case pass for the wrong reason.
_AS_MEMBER = object()


class DuplicateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls): fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.f = fixture.LibraryReadTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.client = self.f.client
        self.member = self.f.member_token
        self.owner = self.f.owner_token
        self.other = self.f.other_token
        with self.f.connection() as db:
            # 101 and 102 are family-a and active; 103 is family-a but deleted, 201 is family-b
            # and 999 is mapped to no library. Only 101 and 102 may count for family-a.
            db.execute("UPDATE assets SET hash_sha256='dup-a' WHERE id IN (101,102,103,201,999)")
            for asset_id in (104, 105, 106, 107):
                db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height)
                    VALUES(?,?,?,'active','image/jpeg',640,480)''',
                    (asset_id, f'private-synthetic/{asset_id}.jpg',
                     'dup-b' if asset_id != 107 else 'unique-c'))
                db.execute('INSERT INTO access_asset_libraries VALUES (?,?)', (asset_id, 'family-a'))
            db.commit()

    def raw(self, path, token=None):
        return self.client.get(path, headers={} if token is None
                               else {'Authorization': 'Bearer ' + token})

    def groups(self, token=_AS_MEMBER, library='family-a', page=1):
        return self.raw(f'/duplicates?library={library}&page={page}',
                        self.member if token is _AS_MEMBER else token)

    def test_it_lists_only_groups_this_library_itself_repeats(self):
        body = self.groups().json()
        self.assertEqual(body['library_id'], 'family-a')
        self.assertEqual(body['total'], 2)
        self.assertEqual([item['copy_count'] for item in body['items']], [2, 3])

    def test_a_deleted_foreign_or_unmapped_copy_never_counts_or_appears(self):
        """A copy outside this library is not this library's duplicate."""
        first = self.groups().json()['items'][0]
        self.assertEqual(first['group_id'], '101')
        self.assertEqual(sorted(copy['id'] for copy in first['copies']), ['101', '102'])

    def test_a_hash_that_does_not_repeat_here_is_not_a_group(self):
        encoded = json.dumps(self.groups().json())
        self.assertNotIn('107', encoded)

    def test_it_exposes_no_path_filename_or_content_hash(self):
        encoded = json.dumps(self.groups().json())
        for forbidden in ('private-synthetic', 'private-hash', 'dup-a', 'dup-b', 'unique-c',
                          'path', 'filename', 'hash'):
            self.assertNotIn(forbidden, encoded)

    def test_copies_reuse_the_gallery_shape(self):
        copy = self.groups().json()['items'][0]['copies'][0]
        self.assertEqual(sorted(copy), ['duration_sec', 'height', 'id', 'kind', 'taken_at',
                                        'thumbnail_url', 'width'])
        self.assertTrue(copy['thumbnail_url'].startswith('/assets/'))

    def test_the_group_id_is_the_lowest_asset_id_and_paging_is_stable(self):
        page_one = self.groups().json()
        self.assertEqual([item['group_id'] for item in page_one['items']], ['101', '104'])
        page_two = self.groups(page=2).json()
        self.assertEqual(page_two['items'], [])
        self.assertEqual(page_two['total'], 2, 'an empty page still states the total')

    def test_any_approved_role_reads_and_no_role_can_write(self):
        for token in (self.member, self.owner):
            with self.subTest(role='member' if token == self.member else 'owner'):
                self.assertEqual(self.groups(token=token).status_code, 200)
        for method in ('post', 'put', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)('/duplicates?library=family-a',
                    headers={'Authorization': 'Bearer ' + self.owner})
                self.assertEqual(response.status_code, 403)

    def test_it_denies_for_another_library_or_no_credential(self):
        self.assertEqual(self.groups(token=self.other).status_code, 401)
        self.assertEqual(self.groups(token=None).status_code, 401)
        self.assertEqual(self.groups(library='family-b').status_code, 401)
        self.assertEqual(self.raw('/duplicates').status_code, 401)

    def test_it_refuses_a_duplicate_or_unbounded_query(self):
        for query in ('?library=family-a&page=1&page=2', '?library=family-a&page=0',
                      '?library=family-a&page=abc', '?page=1'):
            with self.subTest(query=query):
                self.assertNotEqual(self.raw('/duplicates' + query, token=self.member).status_code, 200)
