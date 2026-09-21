"""Whole-wire replay and important native integration invariants, synthetic only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

from native_contract_v2_probe import capture

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / 'docs/contracts/protected-native-v2'


class ProtectedNativeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual = capture()
        cls.cases = {item['id']: item for item in cls.actual['cases']}

    def body(self, name):
        return self.cases[name]['response']['body']

    def test_entire_capture_matches_reviewed_wire_cases(self):
        self.assertEqual(self.actual, json.loads((PACK / 'cases.json').read_text(encoding='utf-8')))

    def test_manifest_pins_source_and_complete_payload(self):
        spec = importlib.util.spec_from_file_location('contract_verifier',
            ROOT / 'scripts/verify_protected_native_contract.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        manifest = module.verify(ROOT)
        self.assertEqual(manifest['case_count'], len(self.actual['cases']))

    def test_upload_retry_uses_canonical_receipt_without_library_access(self):
        first = self.body('upload_accepted')
        retry = self.body('upload_retry_other_batch')
        self.assertEqual(retry, {**first, 'tasks_enqueued': 0})
        self.assertEqual(first['tasks_enqueued'], 5)
        self.assertIsNone(first['library_id'])
        self.assertEqual(self.cases['upload_not_in_library']['response']['status'], 401)

    def test_invited_viewer_has_no_implicit_originals_or_other_library(self):
        memberships = self.body('invited_viewer_session')['memberships']
        self.assertEqual(len(memberships), 1)
        member = memberships[0]
        self.assertEqual((member['library_id'], member['role'], member['originals']),
                         ('family-a', 'viewer', 0))
        self.assertIs(member['available'], True)
        later = self.body('accepted_second_library_session')['memberships']
        self.assertEqual({m['library_id'] for m in later}, {'family-a', 'family-b'})

    def test_revoked_membership_is_not_a_logged_out_account(self):
        response = self.cases['revoked_session_still_authenticated']['response']
        self.assertEqual(response['status'], 200)
        self.assertTrue(all(not m['available'] for m in response['body']['memberships']))
        self.assertEqual(self.cases['revoked_story_list']['response']['status'], 401)

    def test_media_range_requires_grant_and_validates_bytes(self):
        self.assertEqual(self.cases['original_without_grant']['response']['status'], 401)
        part = self.cases['original_range']['response']
        self.assertEqual(part['status'], 206)
        data = (ROOT / 'tests/security/fixtures/home-8x8.jpg').read_bytes()
        self.assertEqual(part['body']['sha256'], hashlib.sha256(data[:16]).hexdigest())
        self.assertEqual(part['headers']['content-range'], f'bytes 0-15/{len(data)}')
        self.assertEqual(self.cases['original_if_range_full']['response']['status'], 200)
        self.assertEqual(self.body('original_if_range_full')['bytes'], len(data))

    def test_prepared_video_keeps_originals_denied_and_source_bound(self):
        self.assertEqual(self.cases['playback_head']['response']['status'],200)
        self.assertEqual(self.cases['playback_viewer_range']['response']['status'],206)
        self.assertEqual(self.cases['playback_original_still_denied']['response']['status'],401)
        self.assertEqual(self.cases['playback_source_changed']['response']['status'],409)
        self.assertEqual(self.cases['playback_without_provider']['response']['status'],503)

    def test_gallery_media_filter_cases_preserve_default_and_scope(self):
        default = self.body('gallery_media_default')
        explicit = self.body('gallery_media_all')
        self.assertEqual(default, explicit)
        self.assertEqual((self.body('gallery_media_image')['total'],
                          self.body('gallery_media_video_page_one')['total']), (2, 2))
        self.assertEqual([item['id'] for item in self.body('gallery_media_video_page_two')['items']], ['101'])
        self.assertEqual(self.cases['gallery_media_invalid']['response']['status'], 400)
        self.assertEqual(self.cases['gallery_media_duplicate']['response']['status'], 400)
        self.assertEqual(self.cases['gallery_media_revoked']['response']['status'], 401)

    def test_prepared_gallery_is_opt_in_scoped_and_counted_before_paging(self):
        one = self.body('prepared_gallery_page_one')
        self.assertEqual(one['total'], 1)
        self.assertEqual([a['id'] for a in one['items']], ['102'])
        self.assertFalse(one['originals_allowed'])
        self.assertEqual(self.body('prepared_gallery_page_two')['items'], [])
        for name in ('prepared_gallery_foreign', 'prepared_gallery_anonymous', 'prepared_gallery_revoked'):
            self.assertEqual(self.cases[name]['response']['status'], 401)
        self.assertEqual(self.cases['prepared_gallery_without_provider']['response']['status'], 503)

    def test_read_only_story_pages_conflicts_and_retry_semantics(self):
        first, second = self.body('story_list_page_one'), self.body('story_list_page_two')
        self.assertEqual((len(first['items']), len(second['items'])), (5, 1))
        self.assertIs(first['has_more'], True)
        self.assertIs(second['has_more'], False)
        self.assertIs(first['can_create'], False)
        self.assertTrue(all(not story['can_edit'] for story in first['items']))
        self.assertEqual(self.body('story_exact_old_retry')['revision'], 2)
        self.assertEqual(self.cases['story_stale_update']['response']['status'], 409)
        self.assertTrue(self.body('story_delete')['deleted'])
        self.assertEqual(self.body('story_deleted_search')['total'], 0)

    def test_no_live_origin_or_credentials_and_admission_is_bounded(self):
        encoded = json.dumps(self.actual)
        for forbidden in ('duckdns', '192.168.', 'C:\\Users', '/Users/yanbo'):
            self.assertNotIn(forbidden, encoded)
        for item in self.actual['cases']:
            request = item['request']
            self.assertIn(request['credential'], {'none', 'O'*43, 'V'*43, 'X'*43, 'N'*43, 'L'*43})
            self.assertEqual(item['response']['headers']['cache-control'], 'no-store')
        rate = self.cases['login_rate_limited']['response']
        self.assertEqual((rate['status'], rate['headers']['retry-after']), (429, '600'))
        for name in ('closed_upload', 'closed_voice_transcribe', 'closed_auth_refresh'):
            self.assertEqual(self.cases[name]['response']['status'], 403)


if __name__ == '__main__':
    unittest.main()
