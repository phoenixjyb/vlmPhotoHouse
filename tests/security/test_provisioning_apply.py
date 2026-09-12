"""Offline apply against disposable migrated databases; no hosts/media/credentials."""
from contextlib import closing
from dataclasses import replace
import getpass
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import warnings

import test_library_reads as fixtures
from app.access.provisioning import ProvisioningPlanner, PlanRejected, LIFETIME
from app.access.provisioning_apply import apply_reviewed, review_backup, plan_digest
from app.access.runtime import ExistingDatabase
from app.access.service import AccessService
import app.access.provisioning_apply as implementation
from test_access_foundation import NOW, NEW, PASSWORD


class ProvisioningApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixtures.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls): fixtures.LibraryReadTests.tearDownClass()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-offline-apply-')
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name).resolve() / 'synthetic.sqlite'
        self.backup = self.path.with_name('synthetic-backup.sqlite')
        with closing(sqlite3.connect(self.path)) as db:
            fixtures.LibraryReadTests.template.backup(db)
            self.owner = db.execute("SELECT account_id FROM access_memberships WHERE library_id='family-a' AND role='owner'").fetchone()[0]
        self.now = NOW
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def mutate(self, sql, args=()):
        with ExistingDatabase(self.path)() as db:
            db.execute(sql, args); db.commit()

    def query(self, sql):
        with ExistingDatabase(self.path, read_only=True)() as db:
            return db.execute(sql).fetchall()

    def plan(self, owner=False, ids=None):
        with ExistingDatabase(self.path, read_only=True)() as db:
            planner = ProvisioningPlanner(db, clock=lambda: self.now)
            if owner:
                return planner.owner(phone=NEW, library_id='new-family')
            return planner.assets(library_id='family-a', operator_account_id=self.owner, asset_ids=ids or [999])

    def review(self, plan):
        with ExistingDatabase(self.path, read_only=True)() as source, closing(sqlite3.connect(self.backup)) as backup:
            source.backup(backup)
        return review_backup(database=self.path, backup=self.backup, envelope=plan,
            reviewed_plan_digest=plan_digest(plan), authority_reference='synthetic-authority',
            restore_reference='synthetic-restore', clock=lambda: self.now)

    def apply(self, plan, review):
        return apply_reviewed(plan, review=review, clock=lambda: self.now)

    def assert_unmapped(self):
        self.assertEqual(self.query('SELECT * FROM access_asset_libraries WHERE asset_id=999'), [])
        self.assertEqual(self.query('SELECT * FROM access_provisioning_receipts'), [])

    def test_mapping_receipt_and_audit_without_new_grants_or_private_data(self):
        before = self.query('SELECT * FROM access_memberships')
        plan = self.plan(); review = self.review(plan)
        backup_bytes = self.backup.read_bytes()
        receipt = self.apply(plan, review)
        self.assertEqual(receipt['asset_ids'], ['999'])
        self.assertEqual(self.query('SELECT * FROM access_asset_libraries WHERE asset_id=999'), [(999, 'family-a')])
        self.assertEqual(self.query('SELECT * FROM access_memberships'), before)
        self.assertEqual(json.loads(self.query('SELECT receipt FROM access_provisioning_receipts')[0][0]), receipt)
        self.assertEqual(self.query("SELECT count(*) FROM access_audit WHERE action='offline.assign_unmapped_assets'"), [(1,)])
        for private in ('private-synthetic', 'private-hash', PASSWORD, str(self.path), '+1202'):
            self.assertNotIn(private, json.dumps(receipt))
        self.assertEqual(self.backup.read_bytes(), backup_bytes)
        with self.assertRaises(PlanRejected): self.apply(plan, review)

    def test_review_does_not_write_target_or_backup(self):
        plan = self.plan(); self.review(plan)
        before = (self.path.read_bytes(), self.backup.read_bytes())
        review_backup(database=self.path, backup=self.backup, envelope=plan,
                      reviewed_plan_digest=plan_digest(plan), authority_reference='synthetic-authority',
                      restore_reference='synthetic-restore', clock=lambda: self.now)
        self.assertEqual(before, (self.path.read_bytes(), self.backup.read_bytes()))

    def test_bootstrap_prompts_hashes_outside_lock_and_creates_no_session_or_mapping(self):
        plan = self.plan(owner=True); review = self.review(plan)
        before = self.query('SELECT * FROM access_asset_libraries')
        sessions = self.query('SELECT * FROM access_sessions')
        def prompt(_):
            # A second writer can reserve while the protected prompt runs.
            with ExistingDatabase(self.path)() as db:
                db.execute('BEGIN IMMEDIATE'); db.rollback()
            return PASSWORD
        with patch('app.access.provisioning_apply.getpass.getpass', side_effect=prompt) as prompts:
            original_hash = implementation.hash_password
            def hash_without_lock(password):
                with ExistingDatabase(self.path)() as db:
                    db.execute('BEGIN IMMEDIATE'); db.rollback()
                return original_hash(password)
            with patch('app.access.provisioning_apply.hash_password', side_effect=hash_without_lock):
                receipt = self.apply(plan, review)
        self.assertEqual(prompts.call_count, 2)
        with ExistingDatabase(self.path)() as db:
            service = AccessService(db, clock=lambda: self.now)
            token = service.login(NEW, PASSWORD)
            self.assertEqual(service.profile(token)['account_id'], receipt['actor_account_id'])
        self.assertEqual(self.query('SELECT * FROM access_asset_libraries'), before)
        self.assertEqual(self.query("SELECT role,originals FROM access_memberships WHERE library_id='new-family'"), [('owner', 0)])
        self.assertEqual(len(self.query('SELECT * FROM access_sessions')), len(sessions) + 1) # Only explicit test login.

    def test_password_fallback_and_confirmation_failure_do_not_write(self):
        plan = self.plan(owner=True); review = self.review(plan)
        before = self.path.read_bytes()
        for effect, error in [([PASSWORD, PASSWORD + 'x'], PlanRejected),
                              (lambda _: warnings.warn('synthetic fallback', getpass.GetPassWarning), getpass.GetPassWarning)]:
            with patch('app.access.provisioning_apply.getpass.getpass', side_effect=effect):
                with self.assertRaises(error): self.apply(plan, review)
            self.assertEqual(before, self.path.read_bytes())

    def test_bootstrap_revalidates_after_password_hashing(self):
        plan = self.plan(owner=True); review = self.review(plan)
        def prompt(_):
            self.now = NOW + LIFETIME
            return PASSWORD
        with patch('app.access.provisioning_apply.getpass.getpass', side_effect=prompt):
            with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assertEqual(self.query("SELECT id FROM access_libraries WHERE id='new-family'"), [])
        self.assert_unmapped()

    def test_exact_digest_distinct_backup_and_external_review_references_required(self):
        plan = self.plan(); self.review(plan)
        common = dict(database=self.path, backup=self.backup, envelope=plan,
                      reviewed_plan_digest=plan_digest(plan), authority_reference='synthetic-authority',
                      restore_reference='synthetic-restore', clock=lambda: self.now)
        for change in ({'backup': self.path}, {'reviewed_plan_digest': '0'*64},
                       {'authority_reference': ''}, {'restore_reference': ''}):
            with self.assertRaises(PlanRejected): review_backup(**(common | change))
        self.assert_unmapped()

    def test_backup_mismatch_or_post_review_change_refused(self):
        plan = self.plan(); review = self.review(plan)
        with ExistingDatabase(self.backup)() as db:
            db.execute("UPDATE assets SET width=123 WHERE id=999"); db.commit()
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        with self.assertRaises(PlanRejected):
            review_backup(database=self.path, backup=self.backup, envelope=plan,
                          reviewed_plan_digest=plan_digest(plan), authority_reference='synthetic-authority',
                          restore_reference='synthetic-restore', clock=lambda: self.now)
        self.assert_unmapped()

    def test_same_content_replaced_target_or_backup_is_refused(self):
        plan = self.plan(); review = self.review(plan)
        clone = self.path.with_name('clone.sqlite')
        shutil.copyfile(self.path, clone)
        with self.assertRaises(PlanRejected): self.apply(plan, replace(review, database=clone))
        clone.replace(self.path)
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assert_unmapped()

    def test_unrelated_write_stales_backup_even_if_plan_remains_valid(self):
        plan = self.plan(); review = self.review(plan)
        self.mutate('UPDATE assets SET width=123 WHERE id=101')
        with self.assertRaisesRegex(PlanRejected, 'fresh backup'): self.apply(plan, review)
        self.assert_unmapped()

    def test_expiry_during_backup_scan_is_rechecked_before_effects(self):
        plan = self.plan(); review = self.review(plan)
        snapshot = implementation._snapshot
        def slow_scan(db):
            result = snapshot(db)
            self.now = NOW + LIFETIME
            return result
        with patch('app.access.provisioning_apply._snapshot', side_effect=slow_scan):
            with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assert_unmapped()

    def test_audience_or_asset_changed_after_review_refused(self):
        for sql in ("UPDATE access_memberships SET originals=1 WHERE role='viewer'",
                    "UPDATE assets SET status='deleted' WHERE id=999"):
            plan = self.plan(); review = self.review(plan)
            self.mutate(sql)
            with self.assertRaises(PlanRejected): self.apply(plan, review)
            self.assert_unmapped()
            self.mutate("UPDATE assets SET status='active' WHERE id=999")

    def test_receipt_failure_rolls_back_mapping_and_audit(self):
        self.mutate("""CREATE TRIGGER synthetic_receipt_failure BEFORE INSERT ON access_provisioning_receipts
            BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
        plan = self.plan(); review = self.review(plan)
        before = self.query('SELECT * FROM access_audit')
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assert_unmapped()
        self.assertEqual(self.query('SELECT * FROM access_audit'), before)

    def test_audit_failure_rolls_back_owner_grants_and_receipt(self):
        self.mutate("""CREATE TRIGGER synthetic_audit_failure BEFORE INSERT ON access_audit
            WHEN NEW.action='offline.bootstrap_owner' BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
        plan = self.plan(owner=True); review = self.review(plan)
        tables = ('access_accounts', 'access_operators', 'access_libraries', 'access_memberships', 'access_audit')
        before = {table: self.query('SELECT * FROM ' + table) for table in tables}
        with patch('app.access.provisioning_apply.getpass.getpass', return_value=PASSWORD):
            with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assertEqual({table: self.query('SELECT * FROM ' + table) for table in tables}, before)
        self.assert_unmapped()

    def test_write_reservation_prevents_concurrent_audience_change_including_wal(self):
        for journal in ('DELETE', 'WAL'):
            with self.subTest(journal=journal):
                with ExistingDatabase(self.path)() as db:
                    self.assertEqual(db.execute('PRAGMA journal_mode=' + journal).fetchone()[0].upper(), journal)
                plan = self.plan(); review = self.review(plan)
                snapshot = implementation._snapshot
                checked = []
                def check_reservation(db):
                    if db.execute('PRAGMA query_only').fetchone()[0] == 0:
                        with ExistingDatabase(self.path, timeout=0.02)() as competing:
                            with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                                competing.execute("UPDATE access_memberships SET status='revoked' WHERE role='viewer'")
                        checked.append(True)
                    return snapshot(db)
                with patch('app.access.provisioning_apply._snapshot', side_effect=check_reservation):
                    self.apply(plan, review)
                self.assertEqual(checked, [True])
                self.mutate('DELETE FROM access_asset_libraries WHERE asset_id=999')

    def test_partial_batch_failure_rolls_back_all_selected_ids(self):
        self.mutate("INSERT INTO assets(id,path,hash_sha256,status) VALUES (998,'synthetic-second.jpg','synthetic-hash-998','active')")
        self.mutate("""CREATE TRIGGER synthetic_mapping_failure BEFORE INSERT ON access_asset_libraries
            WHEN NEW.asset_id=999 BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
        plan = self.plan(ids=[998, 999]); review = self.review(plan)
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assert_unmapped()
        self.assertEqual(self.query('SELECT * FROM access_asset_libraries WHERE asset_id=998'), [])

    def test_concurrent_apply_commits_only_once(self):
        plan = self.plan(); review = self.review(plan)
        barrier = threading.Barrier(2); outcomes = []
        def worker():
            barrier.wait(timeout=5)
            try: outcomes.append(self.apply(plan, review))
            except PlanRejected: outcomes.append('refused')
        workers = [threading.Thread(target=worker) for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(timeout=10); self.assertFalse(worker.is_alive())
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        self.assertEqual(outcomes.count('refused'), 1)
        self.assertEqual(self.query('SELECT count(*) FROM access_provisioning_receipts'), [(1,)])

    def test_receipt_blocks_replay_even_if_mapping_removed_and_new_backup_reviewed(self):
        plan = self.plan(); self.apply(plan, self.review(plan))
        self.mutate('DELETE FROM access_asset_libraries WHERE asset_id=999')
        review = self.review(plan)
        with self.assertRaisesRegex(PlanRejected, 'already applied'): self.apply(plan, review)
        self.assertEqual(self.query('SELECT * FROM access_asset_libraries WHERE asset_id=999'), [])

    def test_restore_to_separate_synthetic_file_restores_preapply_state(self):
        plan = self.plan(); review = self.review(plan)
        self.apply(plan, review)
        restored_path = self.path.with_name('restored-synthetic.sqlite')
        with ExistingDatabase(self.backup, read_only=True)() as backup, closing(sqlite3.connect(restored_path)) as restored:
            backup.backup(restored)
        with ExistingDatabase(restored_path, read_only=True)() as restored:
            self.assertEqual(restored.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
            self.assertEqual(restored.execute('SELECT * FROM access_provisioning_receipts').fetchall(), [])
            self.assertEqual(restored.execute('SELECT * FROM access_asset_libraries WHERE asset_id=999').fetchall(), [])
        # Restoring also rolls back replay receipts; physical review must be renewed.
        with self.assertRaises(PlanRejected): self.apply(plan, replace(review, database=restored_path))


if __name__ == '__main__': unittest.main()
