"""Synthetic coverage for reviewed repair of suppressed-person ownership."""
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).parent))
import test_library_reads as fixtures
from app.access.provisioning import PlanRejected, ProvisioningPlanner, LIFETIME
from app.access.provisioning_apply import apply_reviewed, plan_digest, review_backup
from app.access.runtime import ExistingDatabase, RuntimeUnavailable
from test_access_foundation import NOW


class SuppressedOwnershipRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.LibraryReadTests.tearDownClass()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-suppressed-repair-')
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name).resolve() / 'synthetic.sqlite'
        self.backup = Path(directory.name).resolve() / 'synthetic-backup.sqlite'
        with closing(sqlite3.connect(self.path)) as db:
            fixtures.LibraryReadTests.template.backup(db)
            self.owner = db.execute(
                "SELECT account_id FROM access_memberships WHERE library_id='family-a' AND role='owner'"
            ).fetchone()[0]
            db.executemany("INSERT INTO assets(id,path,hash_sha256,status) VALUES (?,?,?,?)", [
                (1003, 'synthetic/suppressed-target.jpg', 'synthetic-hash-1003', 'suppressed'),
                (1004, 'synthetic/unassigned-collateral.jpg', 'synthetic-hash-1004', 'active'),
            ])
            db.executemany("INSERT INTO persons(id,display_name,face_count) VALUES (?,?,?)", [
                (301, 'Synthetic Target', 2), (302, 'Synthetic Collateral', 2),
            ])
            db.executemany(
                "INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id,label_source) "
                "VALUES (?,?,?,?,?,?,?,?)", [
                    (3011, 101, 0, 0, 1, 1, 301, 'manual'),
                    (3012, 1003, 0, 0, 1, 1, 301, 'manual'),
                    (3021, 1003, 0, 0, 1, 1, 302, 'manual'),
                    (3022, 1004, 0, 0, 1, 1, 302, 'manual'),
                ])
            db.commit()
        self.now = NOW
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def mutate(self, sql, args=(), *, foreign_keys=True):
        # foreign_keys=False simulates legacy or externally corrupted rows that a
        # foreign-key-enforced connection cannot create, such as a face pointing
        # at a missing asset. The reviewed planner must still refuse them.
        with ExistingDatabase(self.path)() as db:
            if not foreign_keys:
                db.execute('PRAGMA foreign_keys=OFF')
            db.execute(sql, args); db.commit()

    def rows(self, sql, args=()):
        with ExistingDatabase(self.path, read_only=True)() as db:
            return db.execute(sql, args).fetchall()

    def plan(self, **kwargs):
        values = dict(library_id='family-a', operator_account_id=self.owner, person_id=301,
                      asset_ids=[1003], quiescence_reference='synthetic-stopped',
                      provenance_reference='synthetic-provenance')
        values.update(kwargs)
        with ExistingDatabase(self.path, read_only=True)() as db:
            return ProvisioningPlanner(db, clock=lambda: self.now).repair_person(**values)

    def review(self, plan):
        with ExistingDatabase(self.path, read_only=True)() as source, closing(sqlite3.connect(self.backup)) as target:
            source.backup(target)
        return review_backup(database=self.path, backup=self.backup, envelope=plan,
            reviewed_plan_digest=plan_digest(plan), authority_reference='synthetic-authority',
            restore_reference='synthetic-restore', clock=lambda: self.now)

    def apply(self, plan, review, stopped=True):
        return apply_reviewed(plan, review=review, clock=lambda: self.now,
                              all_writers_stopped=stopped)

    def assert_unapplied(self):
        self.assertEqual(self.rows("SELECT * FROM access_person_libraries WHERE person_id=301"), [])
        self.assertEqual(self.rows("SELECT * FROM access_asset_libraries WHERE asset_id=1003"), [])
        self.assertEqual(self.rows("SELECT * FROM access_provisioning_receipts"), [])

    def test_plan_review_apply_grants_target_only_and_preserves_legacy_state(self):
        before = {table: self.rows('SELECT * FROM ' + table) for table in
                  ('assets', 'persons', 'face_detections', 'access_memberships', 'tasks')}
        before_assets = self.rows('SELECT * FROM access_asset_libraries')
        plan = self.plan(); review = self.review(plan)
        result = self.apply(plan, review)
        self.assertEqual(result['operation'], 'repair_suppressed_person_ownership')
        self.assertEqual(self.rows('SELECT person_id,library_id,creator_id,revision FROM access_person_libraries'),
                         [(301, 'family-a', self.owner, 1)])
        self.assertEqual(self.rows('SELECT asset_id,library_id FROM access_asset_libraries WHERE asset_id=1003'),
                         [(1003, 'family-a')])
        self.assertEqual(self.rows('SELECT * FROM access_asset_libraries WHERE asset_id<>1003'),
                         [row for row in before_assets if row[0] != 1003])
        for table, expected in before.items():
            self.assertEqual(self.rows('SELECT * FROM ' + table), expected)
        self.assertEqual(self.rows("SELECT action FROM access_audit WHERE action LIKE 'offline.%'"),
                         [('offline.repair_suppressed_person_ownership',)])
        self.assertEqual(self.rows('SELECT count(*) FROM access_provisioning_receipts'), [(1,)])

    def test_requires_all_writers_stopped_and_replay_is_denied(self):
        plan = self.plan(); review = self.review(plan)
        with self.assertRaises(PlanRejected): self.apply(plan, review, stopped=False)
        self.assert_unapplied()
        self.apply(plan, review)
        # Replay is refused by the reviewed pre-state check, as for the existing
        # offline management import; it must not commit a second receipt.
        with self.assertRaisesRegex(PlanRejected, 'already assigned'):
            self.apply(plan, review)
        self.assertEqual(self.rows('SELECT count(*) FROM access_provisioning_receipts'), [(1,)])
        self.assertEqual(self.rows('SELECT count(*) FROM access_asset_libraries WHERE asset_id=1003'), [(1,)])

    def test_collateral_person_remains_restricted_and_exact_set_is_required(self):
        with self.assertRaises(PlanRejected): self.plan(asset_ids=[1003, 1004])
        plan = self.plan(); review = self.review(plan); self.apply(plan, review)
        self.assertEqual(self.rows("SELECT * FROM access_person_libraries WHERE person_id=302"), [])
        self.assertEqual(self.rows("SELECT * FROM access_person_libraries WHERE person_id=301"),
                         [(301, 'family-a', self.owner, 1)])

    def test_repair_refuses_to_unlock_a_collateral_identity(self):
        # If this mapping were also the last unmapped reference of a second
        # person, that identity would become exclusive and worker-eligible.
        # The reviewed plan must refuse and require separate review instead.
        self.mutate("INSERT INTO access_asset_libraries VALUES (1004,'family-a')")
        with self.assertRaisesRegex(PlanRejected, 'unlock another identity'): self.plan()
        self.assert_unapplied()

    def test_repair_denies_trigger_side_effects_outside_reviewed_inserts(self):
        # Suppression must not be lifted by a trigger that piggybacks on the
        # reviewed inserts, and the failed apply must not commit anything.
        self.mutate("""CREATE TRIGGER synthetic_repair_side_effect AFTER INSERT ON access_asset_libraries
            BEGIN UPDATE assets SET status='active' WHERE id=NEW.asset_id; END""")
        plan = self.plan(); review = self.review(plan)
        with self.assertRaisesRegex(PlanRejected, 'no partial operation committed'):
            self.apply(plan, review)
        self.assert_unapplied()
        self.assertEqual(self.rows('SELECT status FROM assets WHERE id=1003'), [('suppressed',)])

    def test_refuses_target_or_collateral_ownership_and_foreign_or_missing_refs(self):
        self.mutate("INSERT INTO access_person_libraries VALUES (301,'family-a',?,1)", (self.owner,))
        with self.assertRaises(PlanRejected): self.plan()
        self.mutate("DELETE FROM access_person_libraries WHERE person_id=301")
        self.mutate("INSERT INTO access_person_libraries VALUES (302,'family-b',?,1)", (self.owner,))
        with self.assertRaises(PlanRejected): self.plan()
        self.mutate("DELETE FROM access_person_libraries WHERE person_id=302")
        self.mutate("UPDATE face_detections SET asset_id=201 WHERE id=3012")
        with self.assertRaises(PlanRejected): self.plan()
        self.mutate("UPDATE face_detections SET asset_id=1003 WHERE id=3012")
        self.mutate("UPDATE face_detections SET asset_id=9999 WHERE id=3012", foreign_keys=False)
        with self.assertRaises(PlanRejected): self.plan()

    def test_new_unassigned_face_on_candidate_asset_stales_plan(self):
        plan = self.plan(); review = self.review(plan)
        self.mutate("INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id) "
                    "VALUES (3099,1003,0,0,1,1,NULL)")
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assert_unapplied()

    def test_requires_no_running_or_pending_face_work_and_preserves_caption_queue(self):
        for state in ('running', 'pending'):
            self.mutate("INSERT INTO tasks(type,payload_json,state,priority,retry_count) "
                        "VALUES ('face','{}',?,1,0)", (state,))
            with self.assertRaises(PlanRejected): self.plan()
            self.mutate('DELETE FROM tasks')
        self.mutate("INSERT INTO tasks(type,payload_json,state,priority,retry_count) "
                    "VALUES ('caption','{}','pending',1,0)")
        before = self.rows('SELECT * FROM tasks')
        plan = self.plan(); review = self.review(plan); self.apply(plan, review)
        self.assertEqual(self.rows('SELECT * FROM tasks'), before)

    def test_target_must_have_active_mapped_face_and_all_target_refs_in_library(self):
        self.mutate('DELETE FROM face_detections WHERE id=3011')
        with self.assertRaises(PlanRejected): self.plan()
        self.mutate("INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id) "
                    "VALUES (3011,101,0,0,1,1,301)")
        self.mutate('DELETE FROM access_asset_libraries WHERE asset_id=101')
        with self.assertRaises(PlanRejected): self.plan()

    def test_stale_audience_backup_expiry_and_schema_are_refused(self):
        plan = self.plan(); review = self.review(plan)
        self.mutate("UPDATE access_memberships SET revision=revision+1 WHERE account_id=?", (self.owner,))
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.mutate("UPDATE access_memberships SET revision=revision-1 WHERE account_id=?", (self.owner,))
        plan = self.plan(); review = self.review(plan); self.now = NOW + LIFETIME
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assert_unapplied()
        self.now = NOW
        self.mutate("UPDATE alembic_version SET version_num='c7f4a9e2b610'")
        # The storage adapter refuses an unreviewed schema before planning is
        # possible; the planner's own REQUIRED_REVISION check is a second,
        # defence-in-depth layer behind it.
        with self.assertRaises(RuntimeUnavailable): self.plan()

    def test_trigger_failure_rolls_back_mapping_receipt_and_audit(self):
        self.mutate("""CREATE TRIGGER synthetic_repair_failure BEFORE INSERT ON access_person_libraries
            BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
        plan = self.plan(); review = self.review(plan)
        before = self.rows('SELECT * FROM access_audit')
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assert_unapplied(); self.assertEqual(self.rows('SELECT * FROM access_audit'), before)

    def test_partial_mapping_failure_rolls_back_everything(self):
        self.mutate("INSERT INTO assets(id,path,hash_sha256,status) VALUES "
                    "(1005,'synthetic/suppressed-target-2.jpg','synthetic-hash-1005','suppressed')")
        self.mutate("INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id) "
                    "VALUES (3013,1005,0,0,1,1,301)")
        self.mutate("""CREATE TRIGGER synthetic_repair_failure BEFORE INSERT ON access_person_libraries
            WHEN NEW.person_id=301 BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
        plan = self.plan(asset_ids=[1003, 1005]); review = self.review(plan)
        with self.assertRaises(PlanRejected): self.apply(plan, review)
        self.assert_unapplied()

    def test_concurrent_apply_commits_once(self):
        plan = self.plan(); review = self.review(plan); barrier = threading.Barrier(2); outcomes = []
        def worker():
            barrier.wait(timeout=5)
            try: outcomes.append(self.apply(plan, review))
            except PlanRejected: outcomes.append('refused')
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10); self.assertFalse(thread.is_alive())
        self.assertEqual(sum(isinstance(value, dict) for value in outcomes), 1)
        self.assertEqual(outcomes.count('refused'), 1)
        self.assertEqual(self.rows('SELECT count(*) FROM access_provisioning_receipts'), [(1,)])


if __name__ == '__main__':
    unittest.main()
