"""Prepared catalog discovery remains scoped and does not inspect video bytes."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from test_protected_prepared_video import ProtectedPreparedVideoTests


class PreparedGalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ProtectedPreparedVideoTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        ProtectedPreparedVideoTests.tearDownClass()

    def setUp(self):
        self.fixture = ProtectedPreparedVideoTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.e = self.fixture.e
        self.provider = self.fixture.provider
        for name, kind in [('mime', 'TEXT'), ('width', 'INTEGER'), ('height', 'INTEGER'),
                           ('duration_sec', 'REAL'), ('taken_at', 'TEXT')]:
            self.e.mutate(f'ALTER TABLE assets ADD COLUMN {name} {kind}')
        self.e.mutate("UPDATE assets SET mime='video/mp4'")
        # This intentionally small video fixture predates member uploads. Real
        # runtimes require that table; gallery ordering now reads receipt times.
        self.e.mutate('CREATE TABLE access_uploads(asset_id INTEGER UNIQUE, created_at INTEGER)')

    def get(self, query='library=family-a&media=prepared_video', headers=None):
        return self.e.client.get('/assets?' + query, headers=headers or self.e.headers())

    def test_prepared_filter_counts_before_pagination_without_opening_media(self):
        with patch.object(self.provider, 'open', side_effect=AssertionError('No video reads')):
            response = self.get('library=family-a&media=prepared_video&page_size=1')
        self.assertEqual(response.status_code, 200)
        self.e.assert_private(response)
        body = response.json()
        self.assertEqual(body['total'], 1)
        self.assertEqual([a['id'] for a in body['items']], ['101'])
        self.assertEqual(body['items'][0]['kind'], 'video')
        self.assertFalse(body['originals_allowed'])
        self.assertEqual(self.get('library=family-a&media=prepared_video&page_size=1&page=2').json()['items'], [])

    def test_other_library_and_hidden_assets_do_not_leak(self):
        self.assertEqual(self.get('library=family-b&media=prepared_video').status_code, 401)
        self.e.mutate("UPDATE assets SET status='hidden' WHERE id=101")
        self.assertEqual(self.get().json()['total'], 0)

    def test_missing_provider_is_unavailable_only_for_prepared_filter(self):
        self.e.app.state.media_runtime = replace(self.e.app.state.media_runtime, prepared_videos=None)
        self.assertEqual(self.get().status_code, 503)
        self.assertEqual(self.get('library=family-a&media=video').status_code, 200)

    def test_denial_precedes_provider_inspection(self):
        self.e.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (self.e.member_id,))
        with patch.object(self.provider, 'current', side_effect=AssertionError('Must authorize first')):
            self.assertEqual(self.get().status_code, 401)

    def test_changed_index_is_refused_and_does_not_hide_failure_as_empty(self):
        self.fixture.index.write_bytes(b'changed')
        self.assertEqual(self.get().status_code, 409)

    def test_prepared_index_does_not_turn_photos_into_videos(self):
        self.e.mutate("UPDATE assets SET mime='image/jpeg' WHERE id=101")
        self.assertEqual(self.get().json()['total'], 0)

    def test_duplicate_or_unknown_media_is_rejected(self):
        for query in ('library=family-a&media=prepared_video&media=all',
                      'library=family-a&media=prepared',
                      'library=family-a&media=prepared_video%27%20OR%201=1'):
            self.assertEqual(self.get(query).status_code, 400)
