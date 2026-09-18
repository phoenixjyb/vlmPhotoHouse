"""Member-visible photos-of-a-person read against migrated synthetic SQLite and real ASGI routes.

This completes the member people directory: `browse` lists a person, and this opens their
photos. The properties that matter are that it opens **no audience the directory would not
already list**, and that it names photos rather than faces.
"""
import json
import unittest
import test_library_reads as fixture

# A sentinel, so `token=None` means "no credential at all" rather than falling back to the
# member. Using `token or self.member` made the denial case pass a real member token.
_AS_MEMBER = object()


class PersonAssetsTests(unittest.TestCase):
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
            # 101 and 102 are visible in family-a; 103 is deleted, 201 is family-b and 999 is
            # mapped to no library at all.
            db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(1,'Ada',4)")
            db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(2,'Bo',1)")
            db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(3,'',1)")
            db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(4,'Deleted',1)")
            db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(5,'Twice',2)")
            db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(6,'Foreign',1)")
            rows = [(11, 101, 1), (12, 102, 1), (13, 201, 1), (14, 999, 1),
                    (21, 201, 2), (31, 101, 3), (41, 103, 4), (51, 101, 5), (52, 101, 5),
                    (61, 201, 6)]
            for face, asset, person in rows:
                db.execute('''INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h)
                    VALUES(?,?,?,0,0,1,1)''', (face, asset, person))
            # Person 6 is owned by family-b, so even a family-a face must not surface it.
            owner_id = db.execute("""SELECT account_id FROM access_memberships
                WHERE library_id='family-a' AND role='owner'""").fetchone()[0]
            db.execute("""INSERT INTO access_person_libraries(person_id,library_id,creator_id,revision)
                VALUES(6,'family-b',?,1)""", (owner_id,))
            db.commit()

    def raw(self, path, token=None):
        return self.client.get(path, headers={} if token is None
                               else {'Authorization': 'Bearer ' + token})

    def photos(self, person, token=_AS_MEMBER, library='family-a', page=1):
        return self.raw(f'/people/{person}/assets?library={library}&page={page}',
                        self.member if token is _AS_MEMBER else token)

    def test_it_returns_the_library_scoped_photos_of_one_person(self):
        body = self.photos(1).json()
        self.assertEqual(body['person_id'], '1')
        self.assertEqual(body['library_id'], 'family-a')
        self.assertEqual(body['page_size'], 25)
        # Only the two family-a photos: not the family-b one, not the unmapped one.
        self.assertEqual(sorted(item['id'] for item in body['items']), ['101', '102'])
        self.assertEqual(body['total'], 2)

    def test_a_photo_with_two_faces_of_one_person_appears_once(self):
        """Counting faces would overstate what the member is about to page through."""
        body = self.photos(5).json()
        self.assertEqual([item['id'] for item in body['items']], ['101'])
        self.assertEqual(body['total'], 1)

    def test_it_carries_the_gallery_shape_and_nothing_about_faces(self):
        item = self.photos(1).json()['items'][0]
        self.assertEqual(sorted(item), ['duration_sec', 'height', 'id', 'kind', 'taken_at',
                                        'thumbnail_url', 'width'])
        encoded = json.dumps(self.photos(1).json())
        for forbidden in ('bbox', 'confidence', 'embedding', 'vector', 'face_id', 'display_name'):
            self.assertNotIn(forbidden, encoded)

    def test_a_person_the_directory_would_not_list_is_refused(self):
        # Only a family-b face; unnamed; only a deleted photo; owned by another library.
        for person in (2, 3, 4, 6):
            with self.subTest(person=person):
                self.assertEqual(self.photos(person).status_code, 401)

    def test_any_approved_role_reads_and_no_role_can_write(self):
        for token in (self.member, self.owner):
            with self.subTest(role='member' if token == self.member else 'owner'):
                self.assertEqual(self.photos(1, token=token).status_code, 200)
        for method in ('post', 'put', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    '/people/1/assets?library=family-a',
                    headers={'Authorization': 'Bearer ' + self.owner})
                self.assertEqual(response.status_code, 403)

    def test_it_denies_before_answering_for_another_library_or_no_credential(self):
        self.assertEqual(self.photos(1, token=None).status_code, 401)
        self.assertEqual(self.photos(1, token=self.other).status_code, 401)
        self.assertEqual(self.raw('/people/1/assets').status_code, 401)

    def test_it_refuses_a_duplicate_or_unbounded_query(self):
        for query in ('?library=family-a&page=1&page=2', '?library=family-a&page=0',
                      '?library=family-a&page=abc', '?page=1'):
            with self.subTest(query=query):
                self.assertNotEqual(self.raw('/people/1/assets' + query,
                                             token=self.member).status_code, 200)

    def test_page_two_of_a_single_page_is_empty_but_still_states_the_total(self):
        body = self.photos(1, page=2).json()
        self.assertEqual(body['items'], [])
        self.assertEqual(body['total'], 2)
