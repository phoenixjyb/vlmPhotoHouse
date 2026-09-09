"""Read-only provisioning artifacts against synthetic migrated SQLite."""
from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import test_library_reads as library_fixture
from app.access.runtime import ExistingDatabase
from app.access.provisioning import ProvisioningPlanner, PlanRejected, LIFETIME
from app.access.bootstrap import bootstrap_owner
from test_access_foundation import NOW, NEW, PASSWORD


class ProvisioningPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):library_fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):library_fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        directory=tempfile.TemporaryDirectory(prefix='photohouse-provision-plan-');self.addCleanup(directory.cleanup)
        self.path=Path(directory.name).resolve()/'synthetic.sqlite'
        with closing(sqlite3.connect(self.path)) as db:
            library_fixture.LibraryReadTests.template.backup(db)
            self.owner_id=db.execute("SELECT account_id FROM access_memberships WHERE library_id='family-a' AND role='owner'").fetchone()[0]
        self.now=NOW
        for target in ('socket.socket.connect','socket.socket.bind','subprocess.Popen','os.system'):
            guard=patch(target,side_effect=AssertionError('External I/O forbidden'));guard.start();self.addCleanup(guard.stop)

    def planner(self, connection):return ProvisioningPlanner(connection,clock=lambda:self.now)
    def reader(self):return ExistingDatabase(self.path,read_only=True)
    def mutate(self,sql,args=()):
        with ExistingDatabase(self.path)() as db:db.execute(sql,args);db.commit()
    def asset_plan(self,planner,**kwargs):
        return planner.assets(library_id='family-a',operator_account_id=self.owner_id,asset_ids=kwargs.pop('asset_ids',[999]),**kwargs)

    def test_owner_plan_is_explicit_sealed_read_only_and_contains_no_password(self):
        before=self.path.read_bytes()
        with self.reader()() as db:
            planner=self.planner(db);plan=planner.owner(phone=NEW,library_id='new-family')
            self.assertEqual(planner.validate(json.loads(json.dumps(plan)))['applied'],False)
            self.assertEqual(plan['plan']['expected'],{'new_owner':True,'new_operator':True,'new_library':True,'originals_granted':False,'legacy_assets_assigned':0})
            self.assertEqual(db.total_changes,0)
            for sql in ('CREATE TABLE forbidden(id INTEGER)',"UPDATE access_libraries SET state='closed'"):
                with self.assertRaises(sqlite3.OperationalError):db.execute(sql)
            db.execute('PRAGMA query_only=OFF')
            with self.assertRaises(sqlite3.OperationalError):db.execute("UPDATE access_libraries SET state='closed'")
        self.assertEqual(self.path.read_bytes(),before)
        self.assertNotIn('password',json.dumps(plan));self.assertNotIn(str(self.path),json.dumps(plan))

    def test_planner_refuses_writable_connection_and_existing_bootstrap_targets(self):
        with ExistingDatabase(self.path)() as db:
            with self.assertRaises(PlanRejected):self.planner(db)
        with self.reader()() as db:
            planner=self.planner(db)
            for phone,library in [('+12025550100','new-family'),(NEW,'family-a')]:
                with self.assertRaises(PlanRejected):planner.owner(phone=phone,library_id=library)

    def test_assignment_plan_selects_only_unmapped_active_ids_and_no_private_paths(self):
        with self.reader()() as db:
            planner=self.planner(db);plan=self.asset_plan(planner)
            self.assertEqual(plan['plan']['target']['asset_ids'],['999'])
            self.assertEqual(plan['plan']['expected']['count'],1)
            self.assertFalse(plan['plan']['expected']['originals_granted'])
            self.assertFalse(plan['plan']['expected']['moves_or_media_writes'])
            self.assertTrue(planner.validate(plan)['valid'])
            self.assertIsNone(db.execute('SELECT library_id FROM access_asset_libraries WHERE asset_id=999').fetchone())
            secret=db.execute('SELECT secret FROM access_admission_key').fetchone()[0]
            for forbidden in ('private-synthetic','private-hash',secret.hex()):self.assertNotIn(forbidden,json.dumps(plan))

    def test_mapped_foreign_deleted_missing_duplicates_and_bad_ids_are_refused(self):
        self.mutate('DELETE FROM access_asset_libraries WHERE asset_id=103')
        with self.reader()() as db:
            planner=self.planner(db)
            for ids in ([101],[201],[103],[888],[],[999,999],[True],['999'],[0],[-1],[2**63],list(range(1,10002))):
                with self.subTest(ids=ids),self.assertRaises(PlanRejected):self.asset_plan(planner,asset_ids=ids)

    def test_selected_actor_must_be_current_operator_and_owner(self):
        with self.reader()() as db:
            planner=self.planner(db)
            with self.assertRaises(PlanRejected):planner.assets(library_id='family-a',operator_account_id=library_fixture.LibraryReadTests.member_id,asset_ids=[999])
        self.mutate('DELETE FROM access_operators WHERE account_id=?',(self.owner_id,))
        with self.reader()() as db:
            with self.assertRaises(PlanRejected):self.asset_plan(self.planner(db))

    def test_tampering_expiry_and_other_database_key_invalidate_review(self):
        with self.reader()() as db:plan=self.asset_plan(self.planner(db))
        for field,value in [('target',{'library_id':'family-b','operator_account_id':self.owner_id,'asset_ids':['999']}),('expected',{}),('expires_at',NOW+9999)]:
            bad=copy.deepcopy(plan);bad['plan'][field]=value
            with self.reader()() as db:
                with self.assertRaises(PlanRejected):self.planner(db).validate(bad)
        self.now=NOW+LIFETIME
        with self.reader()() as db:
            with self.assertRaises(PlanRejected):self.planner(db).validate(plan)
        self.now=NOW
        self.mutate('UPDATE access_admission_key SET secret=randomblob(32)')  # Synthetic wrong-DB identity only.
        with self.reader()() as db:
            with self.assertRaises(PlanRejected):self.planner(db).validate(plan)

    def test_asset_path_hash_status_mapping_and_owner_revision_changes_invalidate(self):
        changes=[("UPDATE assets SET path='synthetic/changed.jpg' WHERE id=999",()),
                 ("UPDATE assets SET hash_sha256='changed' WHERE id=999",()),
                 ("UPDATE assets SET status='deleted' WHERE id=999",()),
                 ("INSERT INTO access_asset_libraries VALUES (999,'family-a')",()),
                 ('UPDATE access_memberships SET revision=revision+1 WHERE account_id=?',(self.owner_id,))]
        for sql,args in changes:
            self.mutate("DELETE FROM access_asset_libraries WHERE asset_id=999")
            self.mutate("UPDATE assets SET status='active' WHERE id=999")
            with self.reader()() as db:plan=self.asset_plan(self.planner(db))
            self.mutate(sql,args)
            with self.reader()() as db:
                with self.assertRaises(PlanRejected):self.planner(db).validate(plan)

    def test_assignment_review_reports_existing_original_audience_without_new_grants(self):
        self.mutate('UPDATE access_memberships SET originals=1 WHERE account_id=?',(library_fixture.LibraryReadTests.member_id,))
        with self.reader()() as db:
            plan=self.asset_plan(self.planner(db))
            self.assertEqual(plan['plan']['expected']['current_readers'],2)
            self.assertEqual(plan['plan']['expected']['current_original_readers'],1)
            self.assertFalse(plan['plan']['expected']['originals_granted'])

    def test_audience_and_original_permission_changes_invalidate_mapping_review(self):
        with self.reader()() as db:plan=self.asset_plan(self.planner(db))
        self.mutate('UPDATE access_memberships SET originals=1 WHERE account_id=?',(library_fixture.LibraryReadTests.member_id,))
        with self.reader()() as db:
            with self.assertRaises(PlanRejected):self.planner(db).validate(plan)
        with self.reader()() as db:plan=self.asset_plan(self.planner(db))
        self.mutate("UPDATE access_memberships SET status='revoked',revision=revision+1 WHERE account_id=?",(library_fixture.LibraryReadTests.member_id,))
        with self.reader()() as db:
            with self.assertRaises(PlanRejected):self.planner(db).validate(plan)

    def test_owner_plan_becomes_stale_if_account_or_library_is_created(self):
        with self.reader()() as db:plan=self.planner(db).owner(phone=NEW,library_id='new-family')
        with ExistingDatabase(self.path)() as db:bootstrap_owner(db,phone=NEW,password=PASSWORD,library_id='new-family')
        with self.reader()() as db:
            with self.assertRaises(PlanRejected):self.planner(db).validate(plan)

    def test_portable_library_ids_and_malformed_envelopes_fail_closed(self):
        with self.reader()() as db:
            planner=self.planner(db)
            for library in ('','..','a/b','Uppercase','a'*65,'private phone'):
                with self.assertRaises(PlanRejected):planner.owner(phone=NEW,library_id=library)
            for envelope in (None,[],{}, {'plan':{},'seal':'x'}, {'plan':{},'seal':'a'*64,'apply':True}):
                with self.assertRaises(PlanRejected):planner.validate(envelope)


if __name__=='__main__':unittest.main()
