"""Focused regression coverage for staged native-upload publication.

This composes the existing UploadTests fixture instead of subclassing it, so discovery does not
rerun the broad upload suite. All files and databases are temporary synthetic state.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import hashlib
import sqlite3
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.service import AccessDenied, AccessService
import test_upload as base
import test_promotion as promotion_base


class UploadRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.UploadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        base.UploadTests.tearDownClass()

    def setUp(self):
        self.fixture = base.UploadTests('test_retry_of_the_same_bytes_does_not_create_a_second_asset')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def rows(self, sql, args=()):
        return self.fixture.rows(sql, args)

    def connection(self):
        return self.fixture.connection()

    def upload(self, data, *, batch, token=None):
        return self.fixture.upload(data, token=token, batch=batch)

    def canonical_path(self, result):
        return Path(self.rows('SELECT path FROM assets WHERE id=?', (int(result['asset_id']),))[0][0])

    def test_upload_initializes_required_legacy_job_fields(self):
        # Existing ORM-created Windows tables have client-side defaults only.
        # Fresh migration fixtures supply server defaults and masked this failure.
        with closing(self.connection()) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)
            db.execute('DROP TABLE tasks')
            db.execute("""CREATE TABLE tasks (
                id INTEGER PRIMARY KEY NOT NULL,
                type VARCHAR(32) NOT NULL, payload_json JSON NOT NULL,
                state VARCHAR(16) NOT NULL, priority INTEGER NOT NULL,
                retry_count INTEGER NOT NULL, cancel_requested BOOLEAN NOT NULL,
                last_error TEXT, progress_current INTEGER, progress_total INTEGER,
                scheduled_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME, started_at DATETIME, finished_at DATETIME)""")
            db.commit()
        data = base.png(64, 64)
        first = self.upload(data, batch='8' * 32)
        retry = self.upload(data, batch='9' * 32)
        self.assertEqual(retry, {**first, 'tasks_enqueued': 0})
        jobs = self.rows('SELECT type,state,retry_count,cancel_requested FROM tasks ORDER BY type')
        self.assertEqual([tuple(row) for row in jobs],
                         [(kind, 'awaiting_review', 0, 0)
                          for kind in ('caption', 'embed', 'face', 'phash', 'thumb')])
        self.assertEqual(self.rows('SELECT count(*) FROM access_uploads')[0][0], 1)
        self.assertEqual(len([p for p in self.fixture.incoming.rglob('*') if p.is_file()]), 1)

    def test_different_batch_concurrent_retries_publish_one_canonical_file(self):
        data = base.png(640, 480)
        batches = [format(i, '032x') for i in range(1, 3)]
        barrier = threading.Barrier(2)
        import app.access.upload as implementation
        real_stage = implementation._stage_candidate
        def stage(root, payload):
            temporary = real_stage(root, payload)
            barrier.wait(timeout=5)
            return temporary
        with patch('app.access.upload._stage_candidate', side_effect=stage):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda batch: self.upload(data, batch=batch), batches))
        self.assertEqual({result['asset_id'] for result in results}, {results[0]['asset_id']})
        self.assertEqual(len(self.rows('SELECT id FROM assets WHERE hash_sha256=?',
                                       (results[0]['sha256'],))), 1)
        self.assertEqual(len(self.rows('SELECT asset_id FROM access_uploads WHERE sha256=?',
                                       (results[0]['sha256'],))), 1)
        files = [p for p in self.fixture.incoming.rglob('*') if p.is_file()]
        self.assertEqual(len(files), 1)
        canonical = next(result for result in results if result['tasks_enqueued'] == 5)
        self.assertEqual({result['batch'] for result in results}, {canonical['batch']})

    def test_same_batch_concurrent_retries_do_not_remove_canonical_file(self):
        data = base.png(640, 480)
        batch = 'c' * 32
        barrier = threading.Barrier(2)
        import app.access.upload as implementation
        real_stage = implementation._stage_candidate
        def stage(root, payload):
            temporary = real_stage(root, payload)
            barrier.wait(timeout=5)
            return temporary
        with patch('app.access.upload._stage_candidate', side_effect=stage):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: self.upload(data, batch=batch), range(2)))
        self.assertEqual({result['asset_id'] for result in results}, {results[0]['asset_id']})
        path = self.canonical_path(results[0])
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_bytes(), data)
        self.assertEqual(len([p for p in self.fixture.incoming.rglob('*') if p.is_file()]), 1)

    def test_duplicate_receipt_keeps_stored_provenance_after_account_rename(self):
        data = base.png(640, 480)
        first = self.upload(data, batch='d' * 32)
        with closing(self.connection()) as db:
            db.execute("UPDATE access_accounts SET display_name=? WHERE id=(SELECT account_id FROM access_uploads WHERE asset_id=?)",
                       ('Renamed Member', int(first['asset_id'])))
            db.commit()
        second = self.upload(data, batch='e' * 32)
        self.assertEqual(second['asset_id'], first['asset_id'])
        self.assertEqual(second['batch'], first['batch'])
        self.assertEqual(second['incoming'], first['incoming'])
        self.assertEqual(len([p for p in self.fixture.incoming.rglob('*') if p.is_file()]), 1)

    def test_missing_canonical_is_restored_without_a_second_file(self):
        data = base.png(640, 480)
        first = self.upload(data, batch='f' * 32)
        path = self.canonical_path(first)
        path.unlink()
        second = self.upload(data, batch='1' * 32)
        self.assertEqual(second['asset_id'], first['asset_id'])
        self.assertEqual(second['batch'], first['batch'])
        self.assertEqual(path.read_bytes(), data)
        self.assertEqual(len([p for p in self.fixture.incoming.rglob('*') if p.is_file()]), 1)

    def test_corrupt_canonical_is_retained_and_no_pending_temp_survives(self):
        data = base.png(640, 480)
        first = self.upload(data, batch='2' * 32)
        path = self.canonical_path(first)
        path.write_bytes(b'corrupt')
        with self.assertRaises(OSError):
            self.upload(data, batch='3' * 32)
        self.assertEqual(path.read_bytes(), b'corrupt')
        self.assertEqual(self.rows('SELECT count(*) AS n FROM access_uploads')[0]['n'], 1)
        self.assertEqual(list(self.fixture.incoming.rglob('.upload-*.pending')), [])

    def test_matching_orphan_is_adopted(self):
        data = base.png(640, 480)
        digest = hashlib.sha256(data).hexdigest()
        batch = '4' * 32
        # The fixture's stable label is obtained through the same service boundary as UploadRuntime.
        with self.fixture.access.connection_factory() as connection:
            stored_label = AccessService(connection, clock=lambda: base.NOW).uploader(self.fixture.member_token)[1]
        orphan = self.fixture.incoming / stored_label / batch / (digest + '.png')
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(data)
        result = self.upload(data, batch=batch)
        self.assertTrue(orphan.is_file())
        self.assertEqual(self.canonical_path(result), orphan)
        self.assertEqual(len([p for p in self.fixture.incoming.rglob('*') if p.is_file()]), 1)

    def test_mismatched_orphan_is_rejected_and_retained(self):
        data = base.png(640, 480)
        digest = hashlib.sha256(data).hexdigest()
        batch = '5' * 32
        with self.fixture.access.connection_factory() as connection:
            stored_label = AccessService(connection, clock=lambda: base.NOW).uploader(self.fixture.member_token)[1]
        orphan = self.fixture.incoming / stored_label / batch / (digest + '.png')
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b'wrong')
        with self.assertRaises(OSError):
            self.upload(data, batch=batch)
        self.assertEqual(orphan.read_bytes(), b'wrong')
        self.assertEqual(self.rows('SELECT count(*) AS n FROM access_uploads')[0]['n'], 0)
        self.assertEqual(list(self.fixture.incoming.rglob('.upload-*.pending')), [])

    def test_database_failure_after_publication_leaves_final_orphan(self):
        data = base.png(640, 480)
        digest = hashlib.sha256(data).hexdigest()
        batch = '6' * 32
        with patch.object(AccessService, '_record_upload_in_transaction', side_effect=RuntimeError('synthetic database failure')):
            with self.assertRaises(RuntimeError):
                self.upload(data, batch=batch)
        with self.fixture.access.connection_factory() as connection:
            stored_label = AccessService(connection, clock=lambda: base.NOW).uploader(self.fixture.member_token)[1]
        final = self.fixture.incoming / stored_label / batch / (digest + '.png')
        self.assertEqual(final.read_bytes(), data)
        self.assertEqual(self.rows('SELECT count(*) AS n FROM access_uploads')[0]['n'], 0)
        self.assertEqual(list(self.fixture.incoming.rglob('.upload-*.pending')), [])

    def test_revocation_after_staging_publishes_nothing(self):
        data = base.png(640, 480)
        original_stage = __import__('app.access.upload', fromlist=['_stage_candidate'])._stage_candidate

        def stage_then_revoke(root, payload):
            temporary = original_stage(root, payload)
            with closing(self.connection()) as db:
                db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (self.fixture.member_id,))
                db.commit()
            return temporary

        with patch('app.access.upload._stage_candidate', side_effect=stage_then_revoke):
            with self.assertRaises(AccessDenied):
                self.upload(data, batch='7' * 32)
        self.assertEqual(self.rows('SELECT count(*) AS n FROM access_uploads')[0]['n'], 0)
        self.assertEqual([p for p in self.fixture.incoming.rglob('*') if p.is_file()], [])
        self.assertEqual(list(self.fixture.incoming.rglob('.upload-*.pending')), [])

    def test_symlinked_new_batch_parent_is_refused(self):
        data = base.png(640, 480)
        with self.fixture.access.connection_factory() as connection:
            label = AccessService(connection, clock=lambda: base.NOW).uploader(self.fixture.member_token)[1]
        outside = self.fixture.root / 'outside'
        outside.mkdir()
        parent = self.fixture.incoming / label
        parent.mkdir(parents=True)
        (parent / ('8' * 32)).symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.upload(data, batch='8' * 32)
        self.assertEqual(list(outside.rglob('*')), [])
        self.assertEqual(self.rows('SELECT count(*) AS n FROM access_uploads')[0]['n'], 0)

    def test_symlinked_final_path_is_refused(self):
        data = base.png(640, 480)
        digest = hashlib.sha256(data).hexdigest()
        batch = '9' * 32
        with self.fixture.access.connection_factory() as connection:
            label = AccessService(connection, clock=lambda: base.NOW).uploader(self.fixture.member_token)[1]
        parent = self.fixture.incoming / label / batch
        parent.mkdir(parents=True)
        outside = self.fixture.root / 'outside-file'
        outside.write_bytes(b'untouched')
        (parent / (digest + '.png')).symlink_to(outside)
        with self.assertRaises(OSError):
            self.upload(data, batch=batch)
        self.assertEqual(outside.read_bytes(), b'untouched')
        self.assertEqual(self.rows('SELECT count(*) AS n FROM access_uploads')[0]['n'], 0)


class PromotionRaceTests(unittest.TestCase):
    """Promotion uses the same synthetic fixture and writer-lock boundary as uploads."""

    @classmethod
    def setUpClass(cls):
        promotion_base.PromotionTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        promotion_base.PromotionTests.tearDownClass()

    def setUp(self):
        self.fixture = promotion_base.PromotionTests('test_promotion_moves_the_file_and_makes_the_photo_visible')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def rows(self, sql, args=()):
        return self.fixture.rows(sql, args)

    def test_upload_waits_for_promotion_commit_then_sees_assigned_state(self):
        uploaded = self.fixture.upload()
        asset_id = int(uploaded['asset_id'])
        envelope = self.fixture.planned('promote', library_id='family-a',
                                        operator_account_id=self.fixture.owner_id, asset_ids=[asset_id])
        moved = threading.Event(); release = threading.Event(); staged = threading.Event()
        from app.access import promotion as implementation
        from app.access import upload as upload_implementation
        real_record = implementation._record
        real_stage = upload_implementation._stage_candidate
        def paused_record(state, plan, receipt):
            moved.set()
            self.assertTrue(release.wait(5))
            return real_record(state, plan, receipt)
        def observed_stage(root, payload):
            temporary = real_stage(root, payload)
            staged.set()
            return temporary
        review = self.fixture.review(envelope)
        with patch('app.access.promotion._record', side_effect=paused_record), \
             patch('app.access.upload._stage_candidate', side_effect=observed_stage):
            with ThreadPoolExecutor(max_workers=2) as pool:
                promotion = pool.submit(implementation.promote_and_assign, envelope,
                                        review=review, clock=lambda: promotion_base.NOW)
                try:
                    self.assertTrue(moved.wait(5))
                    upload = pool.submit(self.fixture.uploads.store, self.fixture.member_token,
                                         promotion_base.png(640, 480), 'photo.png', 'c' * 32)
                    self.assertTrue(staged.wait(5))
                    self.assertFalse(upload.done())
                finally:
                    release.set()
                promotion.result(timeout=5)
                retried = upload.result(timeout=5)
                self.assertNotEqual(retried['asset_id'], uploaded['asset_id'])
        self.assertEqual(self.rows('SELECT state FROM access_uploads WHERE asset_id=?', (asset_id,))[0][0], 'assigned')
        self.assertEqual(self.rows('SELECT count(*) AS n FROM assets WHERE hash_sha256=?',
                                   (uploaded['sha256'],))[0]['n'], 2)

    def test_promotion_rollback_holds_writer_lock_during_file_compensation(self):
        uploaded = self.fixture.upload()
        asset_id = int(uploaded['asset_id'])
        envelope = self.fixture.planned('promote', library_id='family-a',
                                        operator_account_id=self.fixture.owner_id, asset_ids=[asset_id])
        from app.access import promotion as implementation
        locked = []
        def fail_record(*_args):
            raise RuntimeError('synthetic receipt failure')
        real_restore = implementation._restore_moves
        def observe_restore(moved):
            probe = sqlite3.connect(self.fixture.path, timeout=0, isolation_level=None)
            try:
                try:
                    probe.execute('BEGIN IMMEDIATE')
                    locked.append(False)
                except sqlite3.OperationalError:
                    locked.append(True)
            finally:
                probe.rollback()
                probe.close()
            return real_restore(moved)
        with patch('app.access.promotion._record', side_effect=fail_record), \
             patch('app.access.promotion._restore_moves', side_effect=observe_restore):
            with self.assertRaises(RuntimeError):
                implementation.promote_and_assign(envelope, review=self.fixture.review(envelope), clock=lambda: promotion_base.NOW)
        self.assertEqual(locked, [True])
        stored = Path(self.rows('SELECT path FROM assets WHERE id=?', (asset_id,))[0][0])
        self.assertTrue(stored.exists())
        self.assertEqual(self.rows('SELECT state FROM access_uploads WHERE asset_id=?', (asset_id,))[0][0], 'incoming')


if __name__ == '__main__':
    unittest.main()
