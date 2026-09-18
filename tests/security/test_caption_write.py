"""Member-written captions against migrated synthetic SQLite and real ASGI routes.

The properties that matter: a member can describe a photo that has none, cannot replace a
description that already exists, and what they write is the caption the read returns.
"""
import json
import unittest
import test_library_reads as fixture

# A sentinel, so `token=None` means "no credential at all" rather than falling back to the
# member. An `or` default on a credential makes a denial case pass for the wrong reason.
_AS_MEMBER = object()


class CaptionWriteTests(unittest.TestCase):
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
        # The fixture gives every asset a caption, so an undescribed photo has to be added:
        # 104 is active in family-a with none, which is the case this slice exists for.
        with self.f.connection() as db:
            db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at)
                VALUES(104,'private-synthetic/104.jpg','private-hash-104','active','image/jpeg',
                       640,480,'2026-01-04')''')
            db.execute("INSERT INTO access_asset_libraries VALUES (104,'family-a')")
            db.commit()

    def raw(self, path, token=None, method='post', body=None):
        headers = {} if token is None else {'Authorization': 'Bearer ' + token}
        # GET takes no body; passing json= to it is a TypeError, not a request.
        if method == 'get':
            return self.client.get(path, headers=headers)
        return getattr(self.client, method)(path, headers=headers, json=body)

    def write(self, asset=104, token=_AS_MEMBER, library='family-a', body=None):
        return self.raw(f'/assets/{asset}/captions?library={library}',
                        self.member if token is _AS_MEMBER else token,
                        body={'text': 'Grandma at the beach'} if body is None else body)

    def read(self, asset=104, token=None, library='family-a'):
        return self.raw(f'/assets/{asset}/captions?library={library}',
                        self.member if token is None else token, method='get')

    def test_a_member_describes_a_photo_that_has_none(self):
        response = self.write()
        self.assertEqual(response.status_code, 201)
        caption = response.json()['caption']
        self.assertEqual(caption['text'], 'Grandma at the beach')
        self.assertIs(caption['user_edited'], True)
        # And it is the caption the read returns.
        items = self.read().json()['items']
        self.assertEqual(items[0]['text'], 'Grandma at the beach')
        self.assertIs(items[0]['user_edited'], True)

    def test_the_written_row_is_marked_user_edited(self):
        """The pipeline protects a user edit; without the flag a worker run could replace it."""
        self.write()
        with self.f.connection() as db:
            row = db.execute('SELECT model,user_edited,superseded FROM captions WHERE asset_id=104').fetchone()
        self.assertEqual((row[0], row[1], row[2]), ('member', 1, 0))

    def test_it_refuses_to_replace_an_existing_description(self):
        # 101 already has a caption in the fixture, and one superseded older row.
        response = self.write(asset=101)
        self.assertEqual(response.status_code, 409)
        items = self.read(asset=101).json()['items']
        self.assertNotIn('Grandma at the beach', [item['text'] for item in items])

    def test_it_requires_an_approved_membership(self):
        self.assertEqual(self.write(token=None).status_code, 401)
        self.assertEqual(self.write(token=self.other).status_code, 401)
        self.assertEqual(self.write(token='a' * 43).status_code, 401)
        with self.f.connection() as db:
            db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                       (self.f.member_id,))
            db.commit()
        self.assertEqual(self.write().status_code, 401)

    def test_it_refuses_an_asset_in_another_library_or_deleted(self):
        self.assertEqual(self.write(asset=201).status_code, 401)
        self.assertEqual(self.write(asset=103).status_code, 401)
        self.assertEqual(self.write(asset=999).status_code, 401)

    def test_it_refuses_empty_overlong_or_control_character_text(self):
        for body in ({'text': ''}, {'text': '   '}, {'text': 'x' * 1025},
                     {'text': 'line\nbreak'}, {'text': 5}, {}, {'other': 'x'}):
            with self.subTest(body=body):
                self.assertEqual(self.write(body=body).status_code, 400)
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM captions WHERE asset_id=104').fetchone()[0], 0)

    def test_the_response_names_only_the_caption(self):
        encoded = json.dumps(self.write().json())
        for forbidden in ('private-', 'path', 'model', 'embedding', 'vector', 'bbox'):
            self.assertNotIn(forbidden, encoded)

    def test_a_second_member_cannot_add_a_second_caption(self):
        self.assertEqual(self.write().status_code, 201)
        self.assertEqual(self.write(token=self.owner).status_code, 409)
        self.assertEqual(len(self.read().json()['items']), 1)

    def test_the_write_is_audited(self):
        self.write()
        with self.f.connection() as db:
            row = db.execute("SELECT library_id FROM access_audit WHERE action='caption.write'").fetchall()
        self.assertEqual(row, [('family-a',)])
