import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import unittest
import sys

spec = importlib.util.spec_from_file_location('intake', Path(__file__).with_name('intake_incremental.py'))
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / 'incoming'
        self.root.mkdir()
        self.database = self.base / 'library.sqlite'
        with closing(sqlite3.connect(self.database)) as con:
            con.execute('create table assets(id integer primary key,path text,hash_sha256 text,file_size integer,status text)')
            con.commit()

    def media(self, name, data=b'photo contents'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def register(self, path, status='active', sha=None):
        with closing(sqlite3.connect(self.database)) as con:
            con.execute('insert into assets(path,hash_sha256,file_size,status) values(?,?,?,?)',
                        (str(path), sha or hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size, status))
            con.commit()

    def audit(self):
        return intake.audit(self.root, self.database, settle_seconds=0)

    def move(self, plan, destination=None):
        with (self.base / 'receipt.jsonl').open('w') as log:
            return intake.quarantine(plan, destination or self.base / 'repeative ones', log)

    def test_keep_registered_original_and_recoverable_copy(self):
        original = self.media('original.jpg')
        self.register(original)
        duplicate = self.media('new/copy.jpg')
        distinct = self.media('new/edit.jpg', b'other contents')
        plan = self.audit()
        self.assertEqual(plan['summary']['duplicates'], 1)
        self.assertEqual([i['path'] for i in plan['unique']], [str(distinct)])
        self.assertEqual(self.move(plan), 1)
        self.assertTrue(original.exists())
        self.assertFalse(duplicate.exists())
        self.assertEqual((self.base / 'repeative ones/new/copy.jpg').read_bytes(), original.read_bytes())
        events = [json.loads(line) for line in (self.base / 'receipt.jsonl').read_text().splitlines()]
        self.assertEqual([e['event'] for e in events], ['move-intent', 'moved'])

    def test_new_duplicates_keep_one_and_similar_size_is_not_duplicate(self):
        self.media('a.mp4', b'videoA')
        self.media('b.mp4', b'videoA')
        self.media('c.mp4', b'videoB')
        plan = self.audit()
        self.assertEqual(plan['summary']['unique'], 2)
        self.assertEqual(plan['summary']['duplicates'], 1)
        self.move(plan)
        self.assertTrue((self.root / 'a.mp4').exists())
        self.assertTrue((self.root / 'c.mp4').exists())

    def test_recent_files_deferred(self):
        self.media('copy.jpg')
        plan = intake.audit(self.root, self.database, settle_seconds=600)
        self.assertEqual(plan['summary']['deferred'], 1)

    def test_changed_source_or_keeper_cannot_move(self):
        original = self.media('a.jpg')
        self.register(original)
        self.media('b.jpg')
        plan = self.audit()
        original.write_bytes(b'changed original')
        with self.assertRaises(ValueError):
            self.move(plan)
        self.assertTrue((self.root / 'b.jpg').exists())

    def test_newly_registered_copy_is_protected(self):
        self.media('a.jpg')
        copy = self.media('b.jpg')
        plan = self.audit()
        self.register(copy)
        with self.assertRaises(ValueError):
            self.move(plan)
        self.assertTrue(copy.exists())

    def test_stale_database_hash_not_trusted(self):
        original = self.media('a.jpg', b'older')
        self.register(original, sha=hashlib.sha256(b'newer').hexdigest())
        self.media('b.jpg', b'newer')
        self.assertEqual(self.audit()['summary']['duplicates'], 0)

    def test_missing_or_deleted_keeper_does_not_discard_new_copy(self):
        original = self.media('a.jpg')
        self.register(original, status='deleted')
        self.media('b.jpg')
        self.assertEqual(self.audit()['summary']['duplicates'], 0)
        original.unlink()
        self.assertEqual(self.audit()['summary']['duplicates'], 0)

    def test_destination_inside_scan_or_existing_file_is_refused(self):
        self.media('a.jpg')
        self.media('b.jpg')
        plan = self.audit()
        with self.assertRaises(ValueError):
            self.move(plan, self.root / 'repeative ones')
        destination = self.base / 'repeative ones'
        destination.mkdir()
        (destination / 'b.jpg').write_bytes(b'do not overwrite')
        with self.assertRaises(ValueError):
            self.move(plan, destination)
        self.assertEqual((destination / 'b.jpg').read_bytes(), b'do not overwrite')

    def test_symlinks_are_not_scanned_or_moved(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'photo.jpg').write_bytes(b'outside')
        try:
            (self.root / 'link').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Host does not grant symlink creation')
        self.assertEqual(self.audit()['summary']['unique'], 0)

    @unittest.skipUnless(importlib.util.find_spec('sqlalchemy'), 'Requires PhotoHouse runtime dependencies')
    def test_project_importer_accepts_explicit_files_and_is_idempotent(self):
        from PIL import Image
        from sqlalchemy import create_engine, select, func
        from sqlalchemy.orm import Session
        from unittest.mock import patch
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
        from app.db import Base, Asset, Task
        from app.config import get_settings
        from app.ingest import ingest_paths
        database = self.base / 'isolated.sqlite'
        image = self.root / 'fresh.jpg'
        Image.new('RGB', (8, 8), (10, 20, 30)).save(image)
        video = self.media('sample.mp4', b'fixture-only-not-a-real-video')
        with patch.dict(os.environ, {'VIDEO_ENABLED': 'true', 'IMAGE_TAG_AUTO_ENQUEUE': 'false'}):
            get_settings.cache_clear()
            engine = create_engine('sqlite:///' + database.as_posix())
            try:
                Base.metadata.create_all(engine)
                with Session(engine) as session:
                    result = ingest_paths(session, [str(image), str(video)])
                    self.assertEqual(result['new_assets'], 2)
                    self.assertEqual(session.scalar(select(func.count()).select_from(Task)), 8)
                    again = ingest_paths(session, [str(image), str(video)])
                    self.assertEqual(again['new_assets'], 0)
                    self.assertEqual(again['skipped'], 2)
                    self.assertEqual(session.scalar(select(func.count()).select_from(Asset)), 2)
                    deferred_image = self.root / 'deferred.jpg'
                    Image.new('RGB', (8, 8), (50, 20, 30)).save(deferred_image)
                    deferred_video = self.media('deferred.mp4', b'other video fixture')
                    deferred = ingest_paths(session, [str(deferred_image), str(deferred_video)], enqueue_embeddings=False)
                    self.assertEqual(deferred['new_assets'], 2)
                    self.assertEqual(session.scalar(select(func.count()).select_from(Task)), 14)
                    queued_types = set(session.scalars(select(Task.type).where(Task.id > 8)).all())
                    self.assertNotIn('embed', queued_types)
                    self.assertNotIn('video_embed', queued_types)
                    self.assertIn('caption', queued_types)
                    self.assertIn('face', queued_types)
            finally:
                engine.dispose()
                get_settings.cache_clear()


if __name__ == '__main__':
    unittest.main()
