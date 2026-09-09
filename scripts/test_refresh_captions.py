import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_captions import fingerprint, reason_for

GOOD = ('EN: A person holds a dark phone beside a wooden table. The room has pale walls and a bright window. '
        'A blue case surrounds the phone, with a raised camera opening at the top.\n\n'
        'ZH-CN: 一位成人在木桌旁手持一部深色手机。房间有浅色墙壁和明亮的窗户。手机配有蓝色保护壳，顶部有凸起的相机开口。')


class SelectionTests(unittest.TestCase):
    def test_missing_and_old_one_liners_selected(self):
        self.assertEqual(reason_for([]), 'missing')
        self.assertEqual(reason_for([(1, 'A family outside.', 'old', False, False)]), 'replace_old_or_short')

    def test_manual_history_protected(self):
        self.assertIsNone(reason_for([(1, 'My words.', 'old', True, True)]))

    def test_good_bilingual_skipped_and_short_bilingual_selected(self):
        model = 'qwen3-vl-http|bilingual-en-zh-cn'
        self.assertIsNone(reason_for([(1, GOOD, model, False, False)]))
        self.assertEqual(reason_for([(1, 'EN: A room.\n\nZH-CN: 一个房间。', model, False, False)]), 'replace_old_or_short')

    def test_fingerprint_tracks_edits_and_is_order_independent(self):
        rows = [(1, 'a', 'old', False, False), (2, 'b', 'old', False, False)]
        self.assertEqual(fingerprint(rows), fingerprint(rows[::-1]))
        self.assertNotEqual(fingerprint(rows), fingerprint([(1, 'edited', 'old', False, False)]))

    def test_sqlite_and_orm_booleans_have_identical_fingerprints(self):
        self.assertEqual(fingerprint([(1, 'a', 'old', 0, 1)]),
                         fingerprint([(1, 'a', 'old', False, True)]))


@unittest.skipUnless(importlib.util.find_spec('sqlalchemy'), 'Windows runtime dependencies required')
class RefreshPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'VLM_DATA_ROOT': self.tmp.name,
            'DERIVED_PATH': str(Path(self.tmp.name)/'derived'), 'CAPTION_AUTO_TAG_ENABLE': 'false',
            'CAPTION_WORD_LIMIT': '0', 'CAPTION_POLICY_MAX_RETRIES': '0',
            'CAPTION_ENABLE_STUB_FALLBACK': 'false', 'CAPTION_INFANT_CARE_ASSET_IDS': ''})
        self.env.start()
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.db import Base, Asset, Caption, Task
        from app.tasks import TaskExecutor
        from app.caption_policy import DEFAULT_DETAILED_CAPTION_PROMPT
        os.environ['CAPTION_PROMPT'] = DEFAULT_DETAILED_CAPTION_PROMPT
        self.Caption, self.Task = Caption, Task
        self.engine = create_engine('sqlite:///'+str(Path(self.tmp.name)/'test.sqlite'))
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.session = self.sessions()
        asset = Asset(path=str(Path(self.tmp.name)/'test.jpg'), mime='image/jpeg', hash_sha256='a'*64, status='active')
        self.session.add(asset)
        self.session.commit()
        self.aid = asset.id
        for i in range(4):
            self.session.add(Caption(asset_id=self.aid, text=f'Old one-liner {i}.', model='old'))
        self.session.commit()
        self.task = Task(type='caption', state='running', payload_json={'asset_id': self.aid, 'replace_generated': True})
        self.executor = TaskExecutor.__new__(TaskExecutor)
        from PIL import Image
        self.executor._load_caption_image = lambda asset: Image.new('RGB', (8,8))
        self.provider = Mock()
        self.provider.generate_caption.return_value = GOOD
        self.provider.get_model_name.return_value = 'qwen3-vl-http'
        self.provider_patch = patch('app.caption_service.get_caption_provider', return_value=self.provider)
        self.provider_patch.start()

    def tearDown(self):
        self.provider_patch.stop()
        self.session.close()
        self.engine.dispose()
        self.env.stop()
        self.tmp.cleanup()

    def test_replacement_appends_and_archives_even_over_variant_limit(self):
        result = self.executor._handle_caption(self.session, self.task)
        caps = self.session.query(self.Caption).order_by(self.Caption.id).all()
        self.assertEqual(len(caps), 5)
        self.assertEqual([c.text for c in caps[:4]], [f'Old one-liner {i}.' for i in range(4)])
        self.assertTrue(all(c.superseded for c in caps[:4]))
        self.assertFalse(result.superseded)
        self.assertEqual(result.text, GOOD)
        from app.db import Asset
        self.assertEqual(self.session.get(Asset, self.aid).caption_variant_count, 1)

    def test_invalid_output_does_not_archive_any_history(self):
        self.provider.generate_caption.return_value = 'Only an English sentence.'
        with self.assertRaises(ValueError):
            self.executor._handle_caption(self.session, self.task)
        self.assertEqual(self.session.query(self.Caption).count(), 4)
        self.assertTrue(all(not c.superseded for c in self.session.query(self.Caption)))

    def test_wrong_provider_cannot_replace_history(self):
        self.provider.get_model_name.return_value = 'stub'
        with self.assertRaises(ValueError):
            self.executor._handle_caption(self.session, self.task)
        self.assertTrue(all(not c.superseded for c in self.session.query(self.Caption)))

    def test_existing_manual_caption_prevents_inference(self):
        cap = self.session.query(self.Caption).first()
        cap.user_edited = True
        self.session.commit()
        result = self.executor._handle_caption(self.session, self.task)
        self.assertTrue(result.user_edited)
        self.provider.generate_caption.assert_not_called()

    def test_edit_during_inference_is_preserved(self):
        def edit(*args, **kwargs):
            with self.sessions() as other:
                cap = other.query(self.Caption).first()
                cap.user_edited = True
                cap.text = 'New family correction.'
                other.commit()
            return GOOD
        self.provider.generate_caption.side_effect = edit
        result = self.executor._handle_caption(self.session, self.task)
        self.assertTrue(result.user_edited)
        self.assertEqual(result.text, 'New family correction.')
        self.assertEqual(self.session.query(self.Caption).count(), 4)

    def test_commit_failure_is_not_reported_as_success(self):
        with patch.object(self.session, 'commit', side_effect=RuntimeError('disk error')):
            with self.assertRaisesRegex(RuntimeError, 'disk error'):
                self.executor._handle_caption(self.session, self.task)
        self.assertEqual(self.session.query(self.Caption).count(), 4)
        self.assertTrue(all(not c.superseded for c in self.session.query(self.Caption)))

    def test_owner_reviewed_baby_care_caption_preserves_history(self):
        caption = 'EN: A baby wears a diaper on a blanket.\n\nZH-CN: 一个婴儿穿着尿布躺在毯子上。'
        self.provider.generate_caption.return_value = caption
        with patch.dict(os.environ, {'CAPTION_INFANT_CARE_ASSET_IDS': str(self.aid)}):
            result = self.executor._handle_caption(self.session, self.task)
        self.assertEqual(result.text, caption)
        self.assertEqual(result.model_version, 'bilingual-v1-infant-care-v1')
        caps = self.session.query(self.Caption).order_by(self.Caption.id).all()
        self.assertEqual([c.text for c in caps[:4]], [f'Old one-liner {i}.' for i in range(4)])
        self.assertTrue(all(c.superseded for c in caps[:4]))
        self.assertIn('Owner-reviewed baby-care exception', self.provider.generate_caption.call_args.kwargs['prompt'])

    def test_task_payload_cannot_enable_baby_care_exception(self):
        self.provider.generate_caption.return_value = 'EN: A baby wears a diaper.\n\nZH-CN: 一个婴儿穿着尿布。'
        self.task.payload_json = dict(self.task.payload_json, allow_infant_care=True)
        with self.assertRaisesRegex(ValueError, 'caption policy validation failed'):
            self.executor._handle_caption(self.session, self.task)
        self.assertTrue(all(not c.superseded for c in self.session.query(self.Caption)))

    def test_other_asset_allowlist_does_not_enable_baby_care_exception(self):
        self.provider.generate_caption.return_value = 'EN: A baby with no clothing lies on a blanket.\n\nZH-CN: 一个没穿衣服的婴儿躺在毯子上。'
        with patch.dict(os.environ, {'CAPTION_INFANT_CARE_ASSET_IDS': str(self.aid + 1)}):
            with self.assertRaisesRegex(ValueError, 'caption policy validation failed'):
                self.executor._handle_caption(self.session, self.task)
        self.assertTrue(all(not c.superseded for c in self.session.query(self.Caption)))

    def test_approved_absent_clothing_caption_is_saved(self):
        caption = 'EN: A baby with no clothing lies on a blanket.\n\nZH-CN: 一个没穿衣服的婴儿躺在毯子上。'
        self.provider.generate_caption.return_value = caption
        with patch.dict(os.environ, {'CAPTION_INFANT_CARE_ASSET_IDS': str(self.aid)}):
            result = self.executor._handle_caption(self.session, self.task)
        self.assertEqual(result.text, caption)
        self.assertFalse(result.superseded)


if __name__ == '__main__':
    unittest.main()
