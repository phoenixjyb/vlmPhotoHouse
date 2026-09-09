"""Restore invalidation and quarantine with disposable migrated SQLite only."""
from contextlib import closing
from dataclasses import replace
import copy
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

import test_library_reads as fixtures
import app.access.recovery as implementation
from app.access.recovery import RecoveryPlanner, review_recovery_backup, quarantine_restored_access
from app.access.provisioning import ProvisioningPlanner, PlanRejected, LIFETIME
from app.access.provisioning_apply import apply_reviewed, plan_digest
from app.access.runtime import ExistingDatabase, RuntimeConfiguration
from app.access.service import AccessService, AccessDenied
from test_access_foundation import NOW, NEW, OWNER, PASSWORD


class OfflineRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixtures.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls): fixtures.LibraryReadTests.tearDownClass()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-recovery-')
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name).resolve() / 'restored-synthetic.sqlite'
        self.backup = self.path.with_name('separate-synthetic-backup.sqlite')
        with closing(sqlite3.connect(self.path)) as db:
            fixtures.LibraryReadTests.template.backup(db)
            self.actor = db.execute("SELECT account_id FROM access_memberships WHERE library_id='family-a' AND role='owner'").fetchone()[0]
        self.now = NOW
        with ExistingDatabase(self.path)() as db:
            service = AccessService(db, clock=lambda: self.now)
            self.code = service.invite(fixtures.LibraryReadTests.owner_token, 'family-a', NEW)
            db.execute("INSERT INTO access_attempts VALUES ('synthetic-bucket',?,6)", (NOW + 600,))
            db.execute("INSERT INTO access_kdf_slot VALUES (1,'synthetic-stranded-claim')")
            db.commit()
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def query(self, sql):
        with ExistingDatabase(self.path, read_only=True)() as db:
            return db.execute(sql).fetchall()

    def mutate(self, sql, args=()):
        with ExistingDatabase(self.path)() as db:
            db.execute(sql, args); db.commit()

    def plan(self):
        with ExistingDatabase(self.path, read_only=True)() as db:
            return RecoveryPlanner(db, clock=lambda: self.now).quarantine(
                operator_account_id=self.actor, quiescence_reference='synthetic-stopped-workers')

    def review(self, plan):
        with ExistingDatabase(self.path, read_only=True)() as source, closing(sqlite3.connect(self.backup)) as backup:
            source.backup(backup)
        return review_recovery_backup(database=self.path, backup=self.backup, envelope=plan,
            reviewed_plan_digest=plan_digest(plan), authority_reference='synthetic-authority',
            restore_reference='synthetic-restore', clock=lambda: self.now)

    def apply(self, plan, review):
        return quarantine_restored_access(plan, review=review, clock=lambda: self.now)

    def state(self):
        tables = ('access_accounts', 'access_libraries', 'access_sessions', 'access_invitations',
                  'access_memberships', 'access_asset_libraries', 'access_admission_key',
                  'access_attempts', 'access_kdf_slot', 'access_audit', 'access_provisioning_receipts')
        return {table: self.query('SELECT * FROM ' + table) for table in tables}

    def test_read_only_explicit_plan_and_backup_review_have_no_effects(self):
        before = self.path.read_bytes()
        plan = self.plan(); review = self.review(plan)
        self.assertEqual(before, self.path.read_bytes())
        with ExistingDatabase(self.path, read_only=True)() as db:
            self.assertFalse(RecoveryPlanner(db, clock=lambda: self.now).validate(plan)['applied'])
        with ExistingDatabase(self.path)() as db:
            with self.assertRaises(PlanRejected): RecoveryPlanner(db)
        self.assertEqual(plan['plan']['expected']['kdf_claims_to_clear'], 1)
        self.assertFalse(plan['plan']['expected']['access_reopened'])
        self.assertEqual(review.database, self.path)
        for private in (PASSWORD, self.code, str(self.path), 'private-synthetic', 'synthetic-stranded-claim'):
            self.assertNotIn(private, json.dumps(plan))

    def test_atomic_invalidation_keeps_passwords_memberships_and_mappings_but_closes_access(self):
        before = self.state(); plan = self.plan(); review = self.review(plan)
        backup_bytes = self.backup.read_bytes()
        receipt = self.apply(plan, review)
        after = self.state()
        self.assertEqual([r[:3] for r in before['access_accounts']], [r[:3] for r in after['access_accounts']])
        self.assertTrue(all(r[3] == 'disabled' for r in after['access_accounts']))
        self.assertTrue(all(r[1] == 'closed' for r in after['access_libraries']))
        self.assertTrue(all(r[3] == 1 for r in after['access_sessions']))
        self.assertEqual(self.query('SELECT count(*) FROM access_invitations WHERE consumed=0 AND cancelled=0'), [(0,)])
        for table in ('access_memberships', 'access_asset_libraries'):
            self.assertEqual(before[table], after[table])
        self.assertNotEqual(before['access_admission_key'], after['access_admission_key'])
        self.assertEqual(after['access_attempts'], []); self.assertEqual(after['access_kdf_slot'], [])
        self.assertEqual(json.loads(after['access_provisioning_receipts'][0][2]), receipt)
        self.assertEqual(len(after['access_audit']), len(before['access_audit']) + 1)
        self.assertEqual(backup_bytes, self.backup.read_bytes())
        self.assertFalse(receipt['access_reopened'])
        for private in (PASSWORD, self.code, str(self.path), before['access_admission_key'][0][1].hex(), after['access_admission_key'][0][1].hex()):
            self.assertNotIn(private, json.dumps(receipt))

    def test_old_password_sessions_and_unused_invitation_cannot_restore_access(self):
        plan = self.plan(); self.apply(plan, self.review(plan))
        with ExistingDatabase(self.path)() as db:
            service = AccessService(db, clock=lambda: self.now)
            with self.assertRaises(AccessDenied): service.login(OWNER, PASSWORD)
            with self.assertRaises(AccessDenied): service.profile(fixtures.LibraryReadTests.owner_token)
            with self.assertRaises(AccessDenied): service.list_asset_ids(fixtures.LibraryReadTests.member_token, 'family-a')
            with self.assertRaises(AccessDenied): service.register(NEW, PASSWORD, self.code)

    def test_real_asgi_rejects_restored_cookie_bearer_and_range_without_opening_media(self):
        plan = self.plan(); self.apply(plan, self.review(plan))
        app = RuntimeConfiguration(database=self.path, web_origin='https://photohouse.test',
            original_roots=(self.path.parent / 'unused-originals',),
            derived_root=self.path.parent / 'unused-derived').build_app(clock=lambda: self.now)
        with TestClient(app, base_url='https://photohouse.test') as client:
            token = fixtures.LibraryReadTests.owner_token
            for credential in ({'Authorization': 'Bearer ' + token},
                               {'Cookie': '__Host-ph_session=' + token, 'Sec-Fetch-Site': 'same-origin'}):
                for path in ('/auth/session', '/assets?library=family-a', '/assets/101/media?library=family-a',
                             '/assets/101/thumbnail?library=family-a', '/faces/1/crop?library=family-a'):
                    with self.subTest(path=path), patch('app.access.media.os.open', side_effect=AssertionError('Media must not open')):
                        response = client.get(path, headers=credential | {'Range': 'bytes=0-5'})
                    self.assertEqual(response.status_code, 401)
                    self.assertNotIn('content-range', response.headers)
                    self.assertEqual(response.headers['cache-control'], 'no-store')
                client.cookies.clear()

    def test_closed_libraries_deny_even_if_account_is_separately_enabled(self):
        plan = self.plan(); self.apply(plan, self.review(plan))
        # Synthetic bad partial reopen: proving the independent library barrier.
        self.mutate("UPDATE access_accounts SET state='active' WHERE id=?", (self.actor,))
        with ExistingDatabase(self.path)() as db:
            service = AccessService(db, clock=lambda: self.now)
            token = service.login(OWNER, PASSWORD)
            with self.assertRaises(AccessDenied): service.list_asset_ids(token, 'family-a')
            with self.assertRaises(AccessDenied): service.invite(token, 'family-a', NEW)

    def test_old_owner_asset_and_recovery_plan_seals_are_invalidated(self):
        with ExistingDatabase(self.path, read_only=True)() as db:
            planner = ProvisioningPlanner(db, clock=lambda: self.now)
            owner_plan = planner.owner(phone=NEW, library_id='new-family')
            asset_plan = planner.assets(library_id='family-a', operator_account_id=self.actor, asset_ids=[999])
        recovery_plan = self.plan(); self.apply(recovery_plan, self.review(recovery_plan))
        with ExistingDatabase(self.path, read_only=True)() as db:
            for old in (owner_plan, asset_plan):
                with self.assertRaisesRegex(PlanRejected, 'Invalid or expired'):
                    ProvisioningPlanner(db, clock=lambda: self.now).validate(old)
            with self.assertRaises(PlanRejected): RecoveryPlanner(db, clock=lambda: self.now).validate(recovery_plan)
            # A newly reviewed, explicitly different owner/library is still an offline operation.
            fresh = ProvisioningPlanner(db, clock=lambda: self.now).owner(phone=NEW, library_id='new-family')
            self.assertTrue(ProvisioningPlanner(db, clock=lambda: self.now).validate(fresh)['valid'])

    def test_operator_and_quiescence_record_required_and_bound_to_seal(self):
        with ExistingDatabase(self.path, read_only=True)() as db:
            planner = RecoveryPlanner(db, clock=lambda: self.now)
            for actor, ref in ((self.actor, ''), (fixtures.LibraryReadTests.member_id, 'synthetic-stopped'), ('unknown', 'synthetic-stopped')):
                with self.assertRaises(PlanRejected): planner.quarantine(operator_account_id=actor, quiescence_reference=ref)
        plan = self.plan(); changed = copy.deepcopy(plan)
        changed['plan']['target']['quiescence_reference'] = 'another-review'
        with self.assertRaises(PlanRejected): self.review(changed)
        self.assertEqual(self.query('SELECT count(*) FROM access_kdf_slot'), [(1,)])

    def test_wrong_digest_missing_review_reference_and_same_backup_refused(self):
        plan = self.plan(); self.review(plan)
        kwargs = dict(database=self.path, backup=self.backup, envelope=plan,
            reviewed_plan_digest=plan_digest(plan), authority_reference='synthetic-authority',
            restore_reference='synthetic-restore', clock=lambda: self.now)
        for change in ({'reviewed_plan_digest': '0'*64}, {'authority_reference': ''}, {'restore_reference': ''}, {'backup': self.path}):
            with self.assertRaises(PlanRejected): review_recovery_backup(**(kwargs | change))

    def test_changed_database_or_backup_refuses_all_effects(self):
        plan = self.plan(); review = self.review(plan)
        self.mutate("UPDATE access_kdf_slot SET claim='different-synthetic-claim'")
        before = self.state()
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assertEqual(before, self.state())
        plan = self.plan(); review = self.review(plan)
        with ExistingDatabase(self.backup)() as db:
            db.execute('DELETE FROM access_kdf_slot'); db.commit()
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assertEqual(before, self.state())

    def test_replaced_file_and_expired_review_refused(self):
        plan = self.plan(); review = self.review(plan)
        clone = self.path.with_name('another-copy.sqlite'); shutil.copyfile(self.path, clone)
        with self.assertRaises(PlanRejected): self.apply(plan, replace(review, database=clone))
        self.now = NOW + LIFETIME
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assertEqual(self.query('SELECT count(*) FROM access_kdf_slot'), [(1,)])

    def test_receipt_or_audit_failure_rolls_back_every_invalidation_including_key(self):
        for table in ('access_provisioning_receipts', 'access_audit'):
            self.mutate(f"CREATE TRIGGER synthetic_recovery_failure BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
            plan = self.plan(); review = self.review(plan); before = self.state()
            with self.assertRaises(PlanRejected): self.apply(plan, review)
            self.assertEqual(before, self.state())
            self.mutate('DROP TRIGGER synthetic_recovery_failure')

    def test_random_key_failure_or_repeated_key_commits_nothing(self):
        plan = self.plan(); review = self.review(plan); before = self.state()
        old_key = before['access_admission_key'][0][1]
        with patch('app.access.recovery.secrets.token_bytes', return_value=old_key):
            with self.assertRaises(PlanRejected): self.apply(plan, review)
        with patch('app.access.recovery.secrets.token_bytes', side_effect=RuntimeError('synthetic entropy failure')):
            with self.assertRaises(RuntimeError): self.apply(plan, review)
        self.assertEqual(before, self.state())

    def test_concurrent_and_replayed_recovery_commit_only_once(self):
        plan = self.plan(); review = self.review(plan)
        barrier = threading.Barrier(2); results = []
        def worker():
            barrier.wait(timeout=5)
            try: results.append(self.apply(plan, review))
            except PlanRejected: results.append('refused')
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10); self.assertFalse(thread.is_alive())
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(results.count('refused'), 1)
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assertEqual(self.query('SELECT count(*) FROM access_provisioning_receipts'), [(1,)])

    def test_generic_provisioning_apply_cannot_execute_recovery_plan(self):
        plan = self.plan(); review = self.review(plan); before = self.state()
        with self.assertRaises(PlanRejected): apply_reviewed(plan, review=review, clock=lambda: self.now)
        self.assertEqual(before, self.state())

    def test_expiry_during_snapshot_scan_refuses_without_changes(self):
        plan = self.plan(); review = self.review(plan); before = self.state()
        snapshot = implementation._snapshot
        def slow(db):
            value = snapshot(db); self.now = NOW + LIFETIME; return value
        with patch('app.access.recovery._snapshot', side_effect=slow):
            with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assertEqual(before, self.state())

    def test_expiry_after_audit_rolls_back_key_and_all_effects(self):
        plan = self.plan(); review = self.review(plan); before = self.state()
        audit = AccessService._audit
        def slow(service, *args):
            audit(service, *args); self.now = NOW + LIFETIME
        with patch.object(AccessService, '_audit', slow):
            with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assertEqual(before, self.state())

    def test_write_reservation_blocks_new_kdf_claim_in_rollback_and_wal(self):
        for journal in ('DELETE', 'WAL'):
            with self.subTest(journal=journal):
                with ExistingDatabase(self.path)() as db:
                    self.assertEqual(db.execute('PRAGMA journal_mode=' + journal).fetchone()[0].upper(), journal)
                plan = self.plan(); review = self.review(plan)
                snapshot = implementation._snapshot; checked = []
                def reserved(db):
                    with ExistingDatabase(self.path, timeout=0.02)() as competing:
                        with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                            competing.execute("INSERT OR REPLACE INTO access_kdf_slot VALUES (1,'synthetic-competing-claim')")
                    checked.append(True)
                    return snapshot(db)
                with patch('app.access.recovery._snapshot', side_effect=reserved):
                    self.apply(plan, review)
                self.assertTrue(checked)
                self.assertEqual(self.query('SELECT * FROM access_kdf_slot'), [])

    def test_each_repeated_restore_requires_new_quarantine_and_fresh_random_key(self):
        # Preserve an old backup, then reproduce its dangerous rollback twice.
        plan = self.plan(); self.review(plan)
        archive = self.path.with_name('synthetic-old-archive.sqlite'); shutil.copyfile(self.backup, archive)
        keys = []
        for _ in range(2):
            with ExistingDatabase(archive, read_only=True)() as source, closing(sqlite3.connect(self.path)) as restored:
                source.backup(restored)
            # This is why restoring alone is insufficient: old sessions are valid again.
            with ExistingDatabase(self.path)() as db:
                self.assertEqual(AccessService(db, clock=lambda: self.now).profile(fixtures.LibraryReadTests.owner_token)['account_id'], self.actor)
            fresh = self.plan(); self.apply(fresh, self.review(fresh))
            keys.append(self.query('SELECT secret FROM access_admission_key')[0][0])
            with ExistingDatabase(self.path)() as db:
                with self.assertRaises(AccessDenied): AccessService(db, clock=lambda: self.now).profile(fixtures.LibraryReadTests.owner_token)
        self.assertNotEqual(keys[0], keys[1])


if __name__ == '__main__': unittest.main()
