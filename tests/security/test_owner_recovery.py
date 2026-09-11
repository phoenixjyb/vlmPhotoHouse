"""One-owner recovery, synthetic SQLite and in-process clients only."""
from contextlib import closing, redirect_stdout, redirect_stderr
from dataclasses import replace
import getpass
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import warnings

import test_library_reads as fixtures
from app.access import owner_recovery as implementation
from app.access.owner_recovery import OwnerRecoveryPlanner, review_owner_recovery_backup, recover_owner_library
from app.access.provisioning import PlanRejected, ProvisioningPlanner, LIFETIME
from app.access.provisioning_apply import plan_digest, apply_reviewed
from app.access.recovery import _quarantine_access_state
from app.access.runtime import ExistingDatabase, RuntimeConfiguration
from app.access.credentials import hash_password
from app.access.service import AccessService, AccessDenied
from test_access_foundation import OWNER, MEMBER, OTHER_OWNER, NEW, PASSWORD, NOW

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import provision_access as cli

NEW_PASSWORD = 'synthetic recovered passphrase 2026'


class OwnerRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.LibraryReadTests.setUpClass()
        cls.encoded = hash_password(NEW_PASSWORD)

    @classmethod
    def tearDownClass(cls):
        fixtures.LibraryReadTests.tearDownClass()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-owner-recovery-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.path = self.root/'candidate.sqlite'
        self.backup = self.root/'backup.sqlite'
        with closing(sqlite3.connect(self.path)) as db:
            fixtures.LibraryReadTests.template.backup(db)
            db.execute('PRAGMA foreign_keys=ON')
            service = AccessService(db, clock=lambda: NOW)
            self.invitation = service.invite(fixtures.LibraryReadTests.owner_token, 'family-a', NEW)
            db.execute('BEGIN IMMEDIATE'); _quarantine_access_state(db); db.commit()
            self.actor = db.execute("SELECT id FROM access_accounts WHERE phone_login=?", (OWNER,)).fetchone()[0]
        self.now = NOW
        for target in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def mutate(self, sql, params=()):
        with ExistingDatabase(self.path)() as db:
            db.execute(sql,params); db.commit()

    def query(self, sql, params=()):
        with ExistingDatabase(self.path, read_only=True)() as db:
            return db.execute(sql,params).fetchall()

    def plan(self, **changes):
        target = dict(operator_account_id=self.actor, library_id='family-a',
                      quiescence_reference='synthetic-stopped-workers', reconciliation_reference='synthetic-owner-history-review')
        target.update(changes)
        with ExistingDatabase(self.path, read_only=True)() as db:
            return OwnerRecoveryPlanner(db, clock=lambda:self.now).recover(**target)

    def review(self, plan):
        with ExistingDatabase(self.path, read_only=True)() as source, closing(sqlite3.connect(self.backup)) as backup:
            source.backup(backup)
        return review_owner_recovery_backup(database=self.path, backup=self.backup, envelope=plan,
            reviewed_plan_digest=plan_digest(plan), authority_reference='synthetic-authority',
            restore_reference='synthetic-recovery', clock=lambda:self.now)

    def apply(self, plan, review):
        with patch.object(implementation, '_replacement_password', return_value=self.encoded):
            return recover_owner_library(plan, review=review, clock=lambda:self.now)

    def test_read_only_plan_review_binds_full_state_and_emits_no_secrets(self):
        before = self.path.read_bytes()
        plan = self.plan(); review = self.review(plan)
        self.assertEqual(before, self.path.read_bytes())
        with ExistingDatabase(self.path, read_only=True)() as db:
            self.assertTrue(OwnerRecoveryPlanner(db, clock=lambda:self.now).validate(plan)['valid'])
        with ExistingDatabase(self.path)() as db:
            with self.assertRaises(PlanRejected): OwnerRecoveryPlanner(db)
        self.assertEqual(plan['plan']['expected']['accounts_to_enable'], 1)
        self.assertEqual(plan['plan']['expected']['memberships_to_revoke'], 2)
        for private in (PASSWORD, OWNER, str(self.path), 'private-synthetic', self.invitation):
            self.assertNotIn(private, json.dumps(plan))
        self.assertEqual(review.database, self.path)

    def test_only_selected_owner_library_open_and_every_other_membership_revoked(self):
        # Include a restored cross-library grant for this same owner.
        self.mutate("INSERT INTO access_memberships VALUES (?, 'family-b','approved','viewer',3,NULL,1,?)", (self.actor,self.actor))
        plan = self.plan(); review = self.review(plan)
        before = self.query('SELECT account_id,library_id,revision FROM access_memberships')
        mappings = self.query('SELECT * FROM access_asset_libraries')
        backup_bytes = self.backup.read_bytes()
        receipt = self.apply(plan, review)
        self.assertEqual(self.query("SELECT id FROM access_accounts WHERE state='active'"), [(self.actor,)])
        self.assertEqual(self.query("SELECT id FROM access_libraries WHERE state='active'"), [('family-a',)])
        self.assertEqual(self.query("SELECT account_id,library_id FROM access_memberships WHERE status!='revoked'"), [(self.actor,'family-a')])
        self.assertEqual(self.query('SELECT account_id,library_id,revision FROM access_memberships'), [(a,l,r+1) for a,l,r in before])
        self.assertEqual(self.query('SELECT count(*) FROM access_memberships WHERE originals!=0'), [(0,)])
        self.assertEqual(mappings, self.query('SELECT * FROM access_asset_libraries'))
        self.assertEqual(backup_bytes, self.backup.read_bytes())
        self.assertEqual(json.loads(self.query('SELECT receipt FROM access_provisioning_receipts')[0][0]), receipt)
        for private in (PASSWORD, NEW_PASSWORD, self.encoded, self.invitation, OWNER, str(self.path)):
            self.assertNotIn(private, json.dumps(receipt))
        self.assertFalse(receipt['originals_granted']); self.assertEqual(receipt['sessions_created'], 0)

    def test_old_credentials_denied_new_owner_login_and_new_phone_invitation_work(self):
        plan=self.plan(); self.apply(plan,self.review(plan))
        with ExistingDatabase(self.path)() as db:
            service=AccessService(db,clock=lambda:self.now)
            for phone,password in ((OWNER,PASSWORD),(MEMBER,PASSWORD),(OTHER_OWNER,PASSWORD)):
                with self.assertRaises(AccessDenied): service.login(phone,password)
            with self.assertRaises(AccessDenied): service.profile(fixtures.LibraryReadTests.owner_token)
            with self.assertRaises(AccessDenied): service.register(NEW,PASSWORD,self.invitation)
            owner=service.login(OWNER,NEW_PASSWORD)
            code=service.invite(owner,'family-a',NEW)
            viewer=service.register(NEW,PASSWORD,code)
            self.assertEqual(service.list_asset_ids(viewer,'family-a'), {'total':2,'asset_ids':[101,102]})
            with self.assertRaises(AccessDenied): service.list_asset_ids(owner,'family-b')
            with self.assertRaises(AccessDenied): service.register(NEW,PASSWORD,code)

    def test_real_app_new_owner_reads_but_old_tokens_originals_and_other_library_deny(self):
        from fastapi.testclient import TestClient
        plan=self.plan();self.apply(plan,self.review(plan))
        with ExistingDatabase(self.path)() as db:
            token=AccessService(db,clock=lambda:self.now).login(OWNER,NEW_PASSWORD)
        app=RuntimeConfiguration(self.path,'https://photohouse.test',(self.root/'unused-originals',),self.root/'unused-derived').build_app(clock=lambda:self.now)
        with TestClient(app,base_url='https://photohouse.test') as client:
            headers={'Authorization':'Bearer '+token}
            self.assertEqual(client.get('/assets?library=family-a',headers=headers).status_code,200)
            self.assertEqual(client.get('/assets/101/captions?library=family-a',headers=headers).status_code,200)
            self.assertEqual(client.get('/assets?library=family-b',headers=headers).status_code,401)
            with patch('app.access.media.os.open',side_effect=AssertionError('Media must not open')):
                self.assertEqual(client.get('/assets/101/media?library=family-a',headers=headers|{'Range':'bytes=0-5'}).status_code,401)
                self.assertEqual(client.get('/assets/101/thumbnail?library=family-a',headers={'Authorization':'Bearer '+fixtures.LibraryReadTests.owner_token}).status_code,401)

    def test_nonquarantined_state_wrong_owner_and_missing_reviews_refuse(self):
        for changes in ({'library_id':'family-b'}, {'operator_account_id':fixtures.LibraryReadTests.member_id},
                        {'quiescence_reference':''}, {'reconciliation_reference':''}):
            with self.assertRaises(PlanRejected):self.plan(**changes)
        self.mutate("UPDATE access_accounts SET state='active' WHERE id=?",(self.actor,))
        with self.assertRaises(PlanRejected):self.plan()

    def test_revoked_expiring_owner_and_revision_overflow_refuse(self):
        for sql in ("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                    'UPDATE access_memberships SET expires_at=9999999999 WHERE account_id=?',
                    'UPDATE access_memberships SET revision=9223372036854775807 WHERE account_id=?'):
            before=self.path.read_bytes()
            self.mutate(sql,(self.actor,))
            with self.assertRaises(PlanRejected): self.plan()
            self.path.write_bytes(before)

    def test_different_password_protected_confirmation_and_no_echo_fallback(self):
        plan=self.plan();review=self.review(plan);before=self.path.read_bytes()
        for inputs,error in (([PASSWORD,PASSWORD],PlanRejected),([NEW_PASSWORD,PASSWORD],PlanRejected),
                             (lambda _:warnings.warn('synthetic fallback',getpass.GetPassWarning),getpass.GetPassWarning)):
            with patch('app.access.owner_recovery.getpass.getpass',side_effect=inputs):
                with self.assertRaises(error):recover_owner_library(plan,review=review,clock=lambda:self.now)
            self.assertEqual(before,self.path.read_bytes())
        def prompt(_):
            with ExistingDatabase(self.path)() as db:db.execute('BEGIN IMMEDIATE');db.rollback()
            return NEW_PASSWORD
        with patch('app.access.owner_recovery.getpass.getpass',side_effect=prompt) as prompts:
            recover_owner_library(plan,review=review,clock=lambda:self.now)
        self.assertEqual(prompts.call_count,2)

    def test_expired_or_changed_state_after_password_work_refuses(self):
        plan=self.plan();review=self.review(plan);before=self.path.read_bytes()
        def late(_):self.now=NOW+LIFETIME;return self.encoded
        with patch.object(implementation,'_replacement_password',side_effect=late):
            with self.assertRaises(PlanRejected):recover_owner_library(plan,review=review,clock=lambda:self.now)
        self.assertEqual(before,self.path.read_bytes())
        self.now=NOW
        def changed(_):self.mutate('UPDATE assets SET width=42');return self.encoded
        with patch.object(implementation,'_replacement_password',side_effect=changed):
            with self.assertRaises(PlanRejected):recover_owner_library(plan,review=review,clock=lambda:self.now)
        self.assertEqual(self.query("SELECT count(*) FROM access_accounts WHERE state='active'"),[(0,)])

    def test_backup_digest_identity_and_cross_operation_review_refuse(self):
        plan=self.plan();review=self.review(plan);before=self.path.read_bytes()
        for wrong in (replace(review,plan_digest='0'*64),replace(review,database_identity=(0,0)),
                      replace(review,backup_identity=(0,0))):
            with self.assertRaises(PlanRejected):self.apply(plan,wrong)
        with self.assertRaises(PlanRejected):apply_reviewed(plan,review=review,clock=lambda:self.now)
        with ExistingDatabase(self.backup)() as db:db.execute('UPDATE assets SET width=42');db.commit()
        with self.assertRaises(PlanRejected):self.apply(plan,review)
        self.assertEqual(before,self.path.read_bytes())

    def test_receipt_audit_and_entropy_failure_rollback_password_and_access(self):
        plan=self.plan();review=self.review(plan);before=self.path.read_bytes()
        with patch('app.access.recovery.secrets.token_bytes',side_effect=RuntimeError('synthetic entropy')):
            with self.assertRaises(RuntimeError):self.apply(plan,review)
        with patch.object(AccessService,'_audit',side_effect=sqlite3.OperationalError('synthetic audit')):
            with self.assertRaises(PlanRejected):self.apply(plan,review)
        self.assertEqual(before,self.path.read_bytes())
        self.mutate("CREATE TRIGGER refuse_receipt BEFORE INSERT ON access_provisioning_receipts BEGIN SELECT RAISE(ABORT,'synthetic receipt'); END")
        plan=self.plan();review=self.review(plan);before=self.path.read_bytes()
        with self.assertRaises(PlanRejected):self.apply(plan,review)
        self.assertEqual(before,self.path.read_bytes())

    def test_replay_old_seals_and_expiry_after_audit_refuse(self):
        plan=self.plan();review=self.review(plan);before=self.path.read_bytes()
        original=AccessService._audit
        def late(service,*args):original(service,*args);self.now=NOW+LIFETIME
        with patch.object(AccessService,'_audit',late):
            with self.assertRaises(PlanRejected):self.apply(plan,review)
        self.assertEqual(before,self.path.read_bytes());self.now=NOW
        with ExistingDatabase(self.path,read_only=True)() as db:
            other=ProvisioningPlanner(db,clock=lambda:self.now).owner(phone=NEW,library_id='new-family')
        self.apply(plan,review)
        with self.assertRaises(PlanRejected):self.apply(plan,review)
        with ExistingDatabase(self.path,read_only=True)() as db:
            with self.assertRaises(PlanRejected):ProvisioningPlanner(db,clock=lambda:self.now).validate(other)

    def test_trigger_cannot_reactivate_an_unreviewed_account(self):
        self.mutate("CREATE TRIGGER reopen_all AFTER INSERT ON access_provisioning_receipts BEGIN UPDATE access_accounts SET state='active'; END")
        plan=self.plan();review=self.review(plan);before=self.path.read_bytes()
        with self.assertRaises(PlanRejected):self.apply(plan,review)
        self.assertEqual(before,self.path.read_bytes())

    def test_concurrent_recovery_commits_one_receipt_and_one_owner(self):
        plan=self.plan();review=self.review(plan)
        barrier=threading.Barrier(2);results=[]
        def password(_):barrier.wait(timeout=10);return self.encoded
        def run():
            try:
                recover_owner_library(plan,review=review,clock=lambda:self.now)
                results.append('applied')
            except PlanRejected:results.append('refused')
        with patch.object(implementation,'_replacement_password',side_effect=password):
            threads=[threading.Thread(target=run) for _ in range(2)]
            for thread in threads:thread.start()
            for thread in threads:thread.join(timeout=15)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sorted(results),['applied','refused'])
        self.assertEqual(self.query('SELECT count(*) FROM access_provisioning_receipts'),[(1,)])

    def test_failed_stdout_reports_durable_application_for_cli_receipt_lookup(self):
        plan=self.plan();review=self.review(plan)
        args=cli.parser().parse_args(['receipt','--database',str(self.path),
            '--plan-id',plan['plan']['plan_id'],'--reviewed-plan-digest',review.plan_digest])
        receipt=self.apply(plan,review)
        with patch.object(cli,'execute',return_value=cli.receipt_summary(receipt)), \
                patch('sys.stdout.write',side_effect=BrokenPipeError),redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['receipt','--database',str(self.path),'--plan-id',args.plan_id,
                '--reviewed-plan-digest',args.reviewed_plan_digest]),3)
        self.assertTrue(cli.execute(args)['receipt_found'])

    def call(self,*args):
        out,err=io.StringIO(),io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):code=cli.main(list(map(str,args)),clock=lambda:self.now)
        for private in (str(self.path),NEW_PASSWORD,PASSWORD,OWNER,self.invitation):self.assertNotIn(private,out.getvalue()+err.getvalue())
        return code,json.loads(out.getvalue()) if out.getvalue() else None

    def test_operator_plan_review_apply_and_durable_receipt(self):
        request=self.root/'request.json';planpath=self.root/'plan.json'
        request.write_text(json.dumps(dict(operator_account_id=self.actor,library_id='family-a',
            quiescence_reference='synthetic-stopped',reconciliation_reference='synthetic-owner-history')))
        code,planned=self.call('plan-recovery','--database',self.path,'--request',request,'--out',planpath)
        self.assertEqual(code,0)
        self.assertEqual(self.call('validate-recovery','--database',self.path,'--plan',planpath)[0],0)
        self.review(json.loads(planpath.read_text()))
        args=['--database',self.path,'--plan',planpath,'--backup',self.backup,
            '--reviewed-plan-digest',planned['plan_digest'],'--authority-reference','synthetic-authority','--restore-reference','synthetic-restore']
        code,reviewed=self.call('review-recovery',*args);self.assertEqual(code,0)
        with patch.object(implementation,'_replacement_password',return_value=self.encoded):
            self.assertEqual(self.call('apply-recovery',*args,'--review-digest','0'*64)[0],2)
            code,applied=self.call('apply-recovery',*args,'--review-digest',reviewed['review_digest'])
        self.assertEqual(code,0);self.assertTrue(applied['applied'])
        code,receipt=self.call('receipt','--database',self.path,'--plan-id',planned['plan_id'],
            '--reviewed-plan-digest',planned['plan_digest'])
        self.assertEqual(code,0);self.assertTrue(receipt['receipt_found'])
        self.assertEqual(self.call('apply-recovery',*args,'--review-digest',reviewed['review_digest'])[0],2)


if __name__=='__main__':unittest.main()
