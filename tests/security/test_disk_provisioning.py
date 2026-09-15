"""All existing apply invariants, plus fresh disk restore refusal cases."""
from contextlib import closing
from dataclasses import asdict
import sqlite3
import uuid
from unittest.mock import patch
import unittest

import test_provisioning_apply as baseline
from app.access.provisioning_apply import review_backup, plan_digest
from app.access.runtime import ExistingDatabase
from app.access.provisioning import PlanRejected


class DiskProvisioningTests(baseline.ProvisioningApplyTests):
    def test_write_reservation_prevents_concurrent_audience_change_including_wal(self):
        # The baseline suite tests WAL writes. The disk review mode deliberately
        # refuses WAL before producing a review; it is an offline operator path.
        plan = self.plan()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            with self.assertRaises(PlanRejected): self.review(plan)

    def review(self, plan):
        with ExistingDatabase(self.path, read_only=True)() as source, closing(sqlite3.connect(self.backup)) as backup:
            source.backup(backup)
        self.restore_out = self.path.with_name('restore-' + str(uuid.uuid4()) + '.sqlite')
        return self.disk_review(plan, self.restore_out)

    def disk_review(self, plan, output):
        return review_backup(database=self.path, backup=self.backup, envelope=plan,
            reviewed_plan_digest=plan_digest(plan), authority_reference='synthetic-authority',
            restore_reference='synthetic-restore', clock=lambda: self.now, restore_out=output)

    def test_disk_proof_retained_and_review_digest_ignores_scratch_location(self):
        plan = self.plan(); first = self.review(plan)
        self.assertTrue(self.restore_out.is_file())
        other = self.path.with_name('second-restore.sqlite')
        second = self.disk_review(plan, other)
        self.assertEqual(asdict(first), asdict(second))
        self.assertTrue(other.is_file())

    def test_existing_restore_cannot_be_overwritten(self):
        plan = self.plan(); self.review(plan)
        before = self.restore_out.read_bytes()
        with self.assertRaises(FileExistsError): self.disk_review(plan, self.restore_out)
        self.assertEqual(before, self.restore_out.read_bytes())

    def test_source_and_backup_aliases_refused_as_restore_output(self):
        plan = self.plan(); self.review(plan)
        for output in (self.path, self.backup):
            before = output.read_bytes()
            with self.assertRaises(FileExistsError): self.disk_review(plan, output)
            self.assertEqual(before, output.read_bytes())

    def test_disk_restore_is_not_a_memory_database(self):
        plan = self.plan()
        real_connect = sqlite3.connect
        def connect(database, *args, **kwargs):
            self.assertNotEqual(database, ':memory:')
            return real_connect(database, *args, **kwargs)
        with patch('sqlite3.connect', side_effect=connect): self.review(plan)

    def test_disk_mode_refuses_wal_inputs(self):
        plan = self.plan(); self.review(plan)
        with closing(sqlite3.connect(self.backup)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            with self.assertRaises(PlanRejected):
                self.disk_review(plan, self.path.with_name('new-restore.sqlite'))

    def test_disk_mode_refuses_low_space(self):
        plan = self.plan(); self.review(plan)
        from app.access import provisioning_apply
        with patch.object(provisioning_apply.shutil, 'disk_usage', return_value=type('Usage', (), {'free': 1})()):
            with self.assertRaises(PlanRejected):
                self.disk_review(plan, self.path.with_name('new-restore.sqlite'))


if __name__ == '__main__': unittest.main()
