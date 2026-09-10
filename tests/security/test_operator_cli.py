"""Actual CLI dispatch and reviewed services, using disposable synthetic SQLite."""
from contextlib import closing, redirect_stdout, redirect_stderr
import getpass
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings

import test_library_reads as fixtures
from app.access.runtime import ExistingDatabase
from test_access_foundation import NOW, NEW, PASSWORD

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import provision_access as cli


class OperatorCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixtures.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls): fixtures.LibraryReadTests.tearDownClass()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-operator-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.db = self.root/'synthetic.sqlite'
        self.backup = self.root/'backup.sqlite'
        self.request = self.root/'request.json'
        self.plan = self.root/'plan.json'
        with closing(sqlite3.connect(self.db)) as db:
            fixtures.LibraryReadTests.template.backup(db)
            self.owner = db.execute("SELECT account_id FROM access_memberships WHERE library_id='family-a' AND role='owner'").fetchone()[0]
        self.now = NOW
        for target in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def call(self, command, *args):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = cli.main([command,'--database',str(self.db),*map(str,args)], clock=lambda:self.now)
        for private in (NEW, PASSWORD, str(self.db), 'private-synthetic', 'private-hash'):
            self.assertNotIn(private, output.getvalue()+error.getvalue())
        return code, json.loads(output.getvalue()) if output.getvalue() else None, error.getvalue()

    def query(self, sql):
        with ExistingDatabase(self.db, read_only=True)() as db: return db.execute(sql).fetchall()

    def mutate(self, sql):
        with ExistingDatabase(self.db)() as db: db.execute(sql); db.commit()

    def make_plan(self, owner=False):
        self.request.write_text(json.dumps({'phone_login':NEW,'library_id':'new-family'} if owner else
            {'library_id':'family-a','operator_account_id':self.owner,'asset_ids':[999]}))
        code, result, error = self.call('plan-owner' if owner else 'plan-assets',
            '--request',self.request,'--out',self.plan)
        self.assertEqual((code,error),(0,''))
        self.assertFalse(result['applied'])
        self.plan_digest = result['plan_digest']
        self.plan_id = result['plan_id']
        return result

    def copy_backup(self):
        with ExistingDatabase(self.db, read_only=True)() as source, closing(sqlite3.connect(self.backup)) as backup:
            source.backup(backup)

    def review_args(self):
        return ['--plan',self.plan,'--backup',self.backup,'--reviewed-plan-digest',self.plan_digest,
            '--authority-reference','synthetic-authority','--restore-reference','synthetic-restore']

    def review(self):
        self.copy_backup()
        code, result, error = self.call('review',*self.review_args())
        self.assertEqual((code,error),(0,''))
        self.assertFalse(result['applied'])
        self.review_hash = result['review_digest']
        return result

    def apply(self, digest=None):
        return self.call('apply',*self.review_args(),'--review-digest',digest or self.review_hash)

    def test_owner_plan_validate_and_review_are_read_only_with_private_output(self):
        before = self.db.read_bytes()
        self.make_plan(owner=True)
        self.assertEqual(self.call('validate','--plan',self.plan)[0],0)
        self.review()
        self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual(self.query('SELECT * FROM access_provisioning_receipts'),[])
        self.assertIn(NEW,self.plan.read_text())  # Phone appears only in the private plan.
        if os.name != 'nt': self.assertEqual(self.plan.stat().st_mode & 0o777,0o600)

    def test_owner_apply_uses_protected_prompts_and_receipt_without_session_or_assets(self):
        sessions = self.query('SELECT * FROM access_sessions')
        mappings = self.query('SELECT * FROM access_asset_libraries')
        self.make_plan(owner=True); self.review()
        with patch('app.access.provisioning_apply.getpass.getpass', return_value=PASSWORD) as prompt:
            code,result,error = self.apply()
        self.assertEqual((code,error),(0,'')); self.assertTrue(result['applied'])
        self.assertEqual(prompt.call_count,2)
        self.assertEqual(self.query('SELECT * FROM access_sessions'),sessions)
        self.assertEqual(self.query('SELECT * FROM access_asset_libraries'),mappings)
        self.assertEqual(self.query("SELECT role,status,originals FROM access_memberships WHERE library_id='new-family'"),[('owner','approved',0)])
        self.assertEqual(self.query("SELECT bootstrap_operator FROM access_libraries WHERE id='new-family'"),[(result['actor_account_id'],)])
        code,receipt,error = self.call('receipt','--plan-id',self.plan_id,'--reviewed-plan-digest',self.plan_digest)
        self.assertEqual((code,error),(0,'')); self.assertTrue(receipt['receipt_found'])

    def test_asset_apply_maps_only_selected_id_and_preserves_existing_audience(self):
        self.mutate("UPDATE access_memberships SET originals=1 WHERE role='viewer'")
        before = self.query('SELECT * FROM access_memberships')
        self.make_plan(); review = self.review()
        self.assertEqual(review['reviewed_effects']['current_original_readers'],1)
        self.assertFalse(review['reviewed_effects']['originals_granted'])
        code,result,error = self.apply()
        self.assertEqual((code,error),(0,'')); self.assertTrue(result['applied'])
        self.assertEqual(self.query('SELECT library_id FROM access_asset_libraries WHERE asset_id=999'),[('family-a',)])
        self.assertEqual(self.query('SELECT * FROM access_memberships'),before)
        self.assertEqual(self.apply()[0],2)  # No replay through a new CLI process.

    def test_apply_requires_exact_review_acknowledgement_and_backup(self):
        self.make_plan(); self.review()
        self.assertEqual(self.call('apply',*self.review_args())[0],2)
        self.assertEqual(self.apply('0'*64)[0],2)
        self.plan_digest = '0'*64
        self.assertEqual(self.apply()[0],2)
        self.assertEqual(self.query('SELECT * FROM access_provisioning_receipts'),[])

    def test_refreshed_backup_cannot_hide_changes_since_separate_review(self):
        self.make_plan(); self.review()
        self.mutate('UPDATE assets SET width=321 WHERE id=101')  # Unrelated to selected 999.
        self.copy_backup()
        self.assertEqual(self.apply()[0],2)
        self.assertEqual(self.query('SELECT * FROM access_provisioning_receipts'),[])
        # A deliberate new review acknowledges the new whole-database snapshot.
        previous = self.review_hash; self.review()
        self.assertNotEqual(self.review_hash,previous)
        self.assertEqual(self.apply()[0],0)

    def test_same_content_replacement_invalidates_cross_command_review(self):
        self.make_plan(); self.review()
        replacement = self.root/'replacement.sqlite'
        shutil.copyfile(self.backup,replacement); replacement.replace(self.backup)
        self.assertEqual(self.apply()[0],2)
        self.assertEqual(self.query('SELECT * FROM access_provisioning_receipts'),[])

    def test_expiry_and_audience_changes_refuse_before_password_or_effects(self):
        self.make_plan(owner=True); self.review(); self.now = NOW+900
        with patch('app.access.provisioning_apply.getpass.getpass') as prompt:
            self.assertEqual(self.apply()[0],2); prompt.assert_not_called()
        self.assertEqual(self.query("SELECT id FROM access_libraries WHERE id='new-family'"),[])
        self.now=NOW; self.plan.unlink(); self.make_plan(); self.review()
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE role='viewer'")
        self.copy_backup()
        self.assertEqual(self.apply()[0],2)

    def test_echo_fallback_or_password_mismatch_leaves_target_unchanged(self):
        self.make_plan(owner=True); self.review(); before=self.db.read_bytes()
        for effect in ([PASSWORD,PASSWORD+'x'], lambda _: warnings.warn('private fallback',getpass.GetPassWarning)):
            with patch('app.access.provisioning_apply.getpass.getpass',side_effect=effect):
                self.assertEqual(self.apply()[0],2)
            self.assertEqual(self.db.read_bytes(),before)

    def test_unknown_password_arguments_and_malformed_input_never_echo_secrets(self):
        code,result,error=self.call('plan-owner','--password',PASSWORD)
        self.assertEqual(code,2)
        for data in ('{"phone_login":"'+NEW+'","phone_login":"duplicate"}',
                     '{"bad":NaN}', '['*2000+']'*2000, '[]', 'x'*(cli.MAX_JSON+1)):
            self.request.write_text(data)
            self.assertEqual(self.call('plan-owner','--request',self.request,'--out',self.plan)[0],2)
        self.assertFalse(self.plan.exists())

    def test_output_files_and_symlinks_are_never_overwritten(self):
        self.make_plan(); before=self.plan.read_bytes()
        self.assertEqual(self.call('plan-assets','--request',self.request,'--out',self.plan)[0],2)
        self.assertEqual(self.plan.read_bytes(),before)
        alias=self.root/'alias.json'; alias.symlink_to(self.plan)
        self.assertEqual(self.call('validate','--plan',alias)[0],2)
        self.assertEqual(self.call('plan-assets','--request',self.request,'--out',alias)[0],2)
        self.assertEqual(self.plan.read_bytes(),before)

    def test_tampered_plan_and_wrong_or_missing_database_refused(self):
        self.make_plan(); self.review()
        value=json.loads(self.plan.read_text()); value['plan']['target']['library_id']='family-b'
        self.plan.write_text(json.dumps(value))
        self.assertEqual(self.apply()[0],2)
        self.assertEqual(self.query('SELECT * FROM access_provisioning_receipts'),[])
        self.db=self.root/'missing.sqlite'
        self.assertEqual(self.call('validate','--plan',self.plan)[0],2)
        self.assertFalse(self.db.exists())

    def test_receipt_query_recovers_committed_result_after_stdout_failure(self):
        self.make_plan(); self.review()
        arguments=['apply','--database',str(self.db),*map(str,self.review_args()),'--review-digest',self.review_hash]
        error=io.StringIO()
        with patch('sys.stdout.write',side_effect=BrokenPipeError),redirect_stderr(error):
            self.assertEqual(cli.main(arguments,clock=lambda:self.now),3)
        self.assertIn('after application',error.getvalue())
        code,result,_=self.call('receipt','--plan-id',self.plan_id,'--reviewed-plan-digest',self.plan_digest)
        self.assertEqual(code,0); self.assertTrue(result['applied'])
        self.assertEqual(self.query('SELECT count(*) FROM access_provisioning_receipts'),[(1,)])


if __name__ == '__main__': unittest.main()
