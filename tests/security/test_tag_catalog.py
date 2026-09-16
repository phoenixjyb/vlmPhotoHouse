"""Member-visible read-only tag catalog against migrated synthetic SQLite and real ASGI routes."""
import unittest
import test_library_reads as fixture


class TagCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls): fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.f = fixture.LibraryReadTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.client = self.f.client; self.member = self.f.member_token; self.owner = self.f.owner_token
        with self.f.connection() as db:
            for tag_id, name in [(1, 'beach'), (2, 'cake'), (3, 'deleted-only'), (4, 'foreign'),
                                 (5, 'unmapped'), (6, 'blocked'), (7, 'orphan-tag'), (8, '家人'),
                                 (9, 'x' * 130)]:
                db.execute('INSERT INTO tags(id,name,type) VALUES(?,?,?)', (tag_id, name, 'caption-auto'))
            # Only links to *visible* family-a assets may ever surface: 101 and 102 are visible,
            # 103 is deleted, 201 belongs to family-b and 999 is mapped to no library at all.
            for tag_id, asset in [(1, 101), (1, 102), (2, 101), (3, 103), (4, 201), (5, 999),
                                  (8, 102), (9, 101)]:
                db.execute('INSERT INTO asset_tags(asset_id,tag_id,source,score,model) VALUES(?,?,?,?,?)',
                           (asset, tag_id, 'cap', 0.5, 'private-model'))
            # Tag 6 is blocked on a visible asset but carries no link: legacy removal deletes the
            # link and records a block only to stop automatic re-adding, so it must not count.
            db.execute('INSERT INTO asset_tag_blocks(asset_id,tag_id) VALUES(101,6)')
            db.commit()

    def raw(self, path, token=None):
        return self.client.get(path, headers={} if token is None
                               else {'Authorization': 'Bearer ' + token})

    def catalog(self, query='', token=None, library='family-a', page=1):
        return self.raw(f'/tags?library={library}&page={page}&q={query}', token or self.member)

    def tag_assets(self, tag, token=None, library='family-a', page=1):
        return self.raw(f'/tags/{tag}/assets?library={library}&page={page}', token or self.member)

    def test_catalog_lists_only_visible_tags_with_visible_counts(self):
        response = self.catalog()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body['library_id'], body['page'], body['page_size']), ('family-a', 1, 25))
        self.assertEqual(body['total'], 4)
        self.assertEqual([(t['id'], t['name'], t['asset_count']) for t in body['items']],
                         [('1', 'beach', 2), ('2', 'cake', 1), ('9', 'x' * 128, 1), ('8', '家人', 1)])
        # A row is a name and a count of this library's own visible assets, and nothing else.
        self.assertEqual([sorted(item) for item in body['items']],
                         [['asset_count', 'id', 'name', 'name_truncated']] * 4)
        # A name wider than the declared column is truncated, never echoed whole.
        self.assertEqual([t['name_truncated'] for t in body['items']], [False, False, True, False])
        self.assertEqual(len(body['items'][2]['name']), 128)
        # No hidden tag, no derivation provenance and no per-link row detail.
        for forbidden in ('deleted-only', 'foreign', 'unmapped', 'orphan-tag', 'blocked',
                          'caption-auto', 'private-model', 'model', 'source', 'score'):
            self.assertNotIn(forbidden, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_every_approved_role_reads_the_catalog_and_no_role_can_write_it(self):
        self.assertEqual(self.catalog(token=self.owner).status_code, 200)
        for role in ('viewer', 'contributor'):
            self.f.mutate('UPDATE access_memberships SET role=? WHERE account_id=?',
                          (role, self.f.member_id))
            self.assertEqual(self.catalog().status_code, 200)
        # There is no member-facing write path at all: every route here is GET-only, so the
        # closed boundary refuses the rest before any handler is reached.
        for method in ('POST', 'PUT', 'DELETE'):
            for path in ('/tags', '/tags/1/assets'):
                self.assertEqual(self.client.request(method, path + '?library=family-a',
                    headers={'Authorization': 'Bearer ' + self.member}).status_code, 403)

    def test_no_foreign_deleted_or_linkless_tag_is_listed_or_probeable_by_id(self):
        for query in ('foreign', 'deleted-only', 'unmapped', 'orphan-tag', 'blocked'):
            self.assertEqual(self.catalog(query=query).json()['total'], 0)
        # A tag whose only assets are foreign, deleted, unmapped or absent is refused rather
        # than answered empty, so its existence is never confirmed to this library.
        for tag in (3, 4, 5, 6, 7, 999):
            response = self.tag_assets(tag)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {'detail': 'Access denied'})
        # The very same tag is visible to the library that actually owns its assets.
        self.assertEqual(self.tag_assets(4, token=self.f.other_token, library='family-b').json()['total'], 1)

    def test_catalog_denies_before_reading_any_tag_row(self):
        for token in (self.f.other_token, 'a' * 43):
            self.assertEqual(self.catalog(token=token).status_code, 401)
            self.assertEqual(self.tag_assets(1, token=token).status_code, 401)
        self.assertEqual(self.catalog(library='family-b').status_code, 401)
        self.f.trace.clear()
        self.assertEqual(self.raw('/tags?library=family-a').status_code, 401)
        self.assertEqual(self.raw('/tags/1/assets?library=family-a').status_code, 401)
        self.assertFalse(any('asset_tags' in sql for sql in self.f.trace))
        self.f.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                      (self.f.member_id,))
        self.f.trace.clear()
        self.assertEqual(self.catalog().status_code, 401)
        self.assertEqual(self.tag_assets(1).status_code, 401)
        self.assertFalse(any('asset_tags' in sql for sql in self.f.trace))

    def test_tag_assets_reuse_the_gallery_shape_and_stay_library_scoped(self):
        response = self.tag_assets(1)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body['library_id'], body['tag_id'], body['total']), ('family-a', '1', 2))
        self.assertEqual([a['id'] for a in body['items']], ['102', '101'])
        # The tag list is not a second asset surface: same row keys, same originals policy.
        gallery = self.f.get('/assets?library=family-a').json()
        self.assertEqual(body['originals_allowed'], gallery['originals_allowed'])
        self.assertEqual(set(body['items'][0]), set(gallery['items'][0]))
        for forbidden in ('path', 'hash', 'gps', 'private-', 'model', 'error'):
            self.assertNotIn(forbidden, response.text)

    def test_catalog_pages_and_searches_literally_over_visible_tags(self):
        with self.f.connection() as db:
            for i in range(100, 130):
                db.execute('INSERT INTO tags(id,name) VALUES(?,?)', (i, 'tag-%03d' % i))
                db.execute('INSERT INTO asset_tags(asset_id,tag_id) VALUES(101,?)', (i,))
            db.commit()
        first, second = self.catalog().json(), self.catalog(page=2).json()
        self.assertEqual((first['total'], len(first['items']), len(second['items'])), (34, 25, 9))
        self.assertEqual(len({t['id'] for t in first['items'] + second['items']}), 34)
        # Literal search: % and _ are searched as characters, never as wildcards.
        self.assertEqual(self.catalog(query='tag-12').json()['total'], 10)
        self.assertEqual(self.catalog(query='beach').json()['total'], 1)
        self.assertEqual(self.catalog(query='家人').json()['total'], 1)
        for value in ('%', '_', 'does-not-exist'):
            self.assertEqual(self.catalog(query=value).json()['total'], 0)


if __name__ == '__main__':
    unittest.main()
