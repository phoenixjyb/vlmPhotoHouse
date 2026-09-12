"""New-file migration/recovery candidates; disposable snapshots, no external I/O."""
from contextlib import closing, redirect_stdout, redirect_stderr
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_access_database as cli
import test_library_reads as fixtures
from app.access.runtime import ExistingDatabase, REQUIRED_REVISION
from app.access.recovery import _quarantine_access_state
from app.access.service import AccessService, AccessDenied
from app.access.provisioning import ProvisioningPlanner, PlanRejected
from test_access_foundation import OWNER, NEW, PASSWORD, NOW


class MigrationCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.LibraryReadTests.tearDownClass()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-candidate-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.source = self.root / 'synthetic.sqlite'
        self.backup = self.root / 'backup.sqlite'
        self.output = self.root / 'candidate.sqlite'
        with closing(sqlite3.connect(self.source)) as db:
            fixtures.LibraryReadTests.template.backup(db)
            cli.configure(db)
            service = AccessService(db, clock=lambda: NOW)
            self.invitation = service.invite(fixtures.LibraryReadTests.owner_token, 'family-a', NEW)
            db.execute("INSERT INTO access_attempts VALUES ('private-bucket',?,6)", (NOW+600,))
            db.execute("INSERT INTO access_kdf_slot VALUES (1,'private-claim')")
            db.commit()
        self.make_backup()
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def make_backup(self):
        with closing(sqlite3.connect(self.source)) as source, closing(sqlite3.connect(self.backup)) as backup:
            source.backup(backup)
            self.digest = cli.snapshot_digest(source)

    def call(self, **overrides):
        args = {'database': self.source, 'backup': self.backup, 'out': self.output,
                'reviewed-snapshot-digest': self.digest, 'authority-reference': 'synthetic-authority',
                'quiescence-reference': 'synthetic-stopped-workers'}
        args.update(overrides)
        argv = ['migrate-candidate']
        for key, value in args.items():
            if value is not None:
                argv.extend(['--'+key, str(value)])
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = cli.main(argv)
        for private in (str(self.root), 'private-', PASSWORD, self.invitation, OWNER):
            self.assertNotIn(private, stdout.getvalue()+stderr.getvalue())
        return status, json.loads(stdout.getvalue()) if stdout.getvalue() else None

    def test_candidate_closes_access_preserves_inputs_and_records_unsigned_receipt(self):
        before = self.source.read_bytes(), self.backup.read_bytes()
        code, result = self.call()
        self.assertEqual(code, 0)
        self.assertTrue(result['candidate_quarantined'] and result['backup_verified'])
        self.assertFalse(result['access_reopened'] or result['existing_database_modified'])
        self.assertEqual(result['output_sha256'], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertEqual(before, (self.source.read_bytes(), self.backup.read_bytes()))
        with ExistingDatabase(self.source, read_only=True)() as source, ExistingDatabase(self.output)() as db:
            for table in ('assets','captions','access_memberships','access_asset_libraries','access_audit','access_operators'):
                self.assertEqual(source.execute('SELECT * FROM '+table).fetchall(), db.execute('SELECT * FROM '+table).fetchall())
            self.assertEqual(source.execute('SELECT id,phone_login,password_hash FROM access_accounts').fetchall(),
                             db.execute('SELECT id,phone_login,password_hash FROM access_accounts').fetchall())
            self.assertNotEqual(source.execute('SELECT secret FROM access_admission_key').fetchall(),
                                db.execute('SELECT secret FROM access_admission_key').fetchall())
            receipt = json.loads(db.execute('SELECT receipt FROM access_provisioning_receipts WHERE plan_id=?', (result['receipt_id'],)).fetchone()[0])
            self.assertEqual(receipt['receipt_kind'], 'unsigned_local_preparation')
            self.assertEqual(receipt['source_snapshot_digest'], self.digest)
            service = AccessService(db, clock=lambda: NOW)
            with self.assertRaises(AccessDenied): service.login(OWNER, PASSWORD)
            with self.assertRaises(AccessDenied): service.profile(fixtures.LibraryReadTests.owner_token)
            with self.assertRaises(AccessDenied): service.register(NEW, PASSWORD, self.invitation)
            self.assertEqual(db.execute("SELECT count(*) FROM access_libraries WHERE state!='closed'").fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_attempts').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_kdf_slot').fetchone()[0], 0)
        if os.name != 'nt':
            self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_pre_access_database_migrates_without_inventing_accounts_or_grants(self):
        from alembic import command
        from sqlalchemy import create_engine
        self.source = self.root / 'legacy.sqlite'
        engine = create_engine('sqlite:///'+str(self.source))
        try:
            with engine.connect() as connection:
                config = cli.migration_config(); config.attributes['connection'] = connection
                command.upgrade(config, 'd2b7e4f6a901')
                connection.exec_driver_sql("INSERT INTO assets(id,path,hash_sha256,status) VALUES (7,'private-legacy','private-hash','active')")
                connection.commit()
        finally:
            engine.dispose()
        self.make_backup()
        before = self.source.read_bytes(), self.backup.read_bytes()
        code, result = self.call()
        self.assertEqual(code, 0)
        self.assertEqual(result['source_revision'], 'd2b7e4f6a901')
        self.assertEqual(result['revision'], REQUIRED_REVISION)
        with ExistingDatabase(self.output, read_only=True)() as db:
            self.assertEqual(db.execute('SELECT id,path FROM assets').fetchall(), [(7,'private-legacy')])
            for table in ('access_accounts','access_sessions','access_libraries','access_memberships','access_asset_libraries'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0], 0)
            plan = ProvisioningPlanner(db, clock=lambda: NOW).owner(phone=OWNER, library_id='synthetic-family')
            self.assertIsInstance(plan, dict)
        self.assertEqual(before, (self.source.read_bytes(), self.backup.read_bytes()))

    def test_stale_review_or_changed_backup_refuses_before_output(self):
        self.assertEqual(self.call(**{'reviewed-snapshot-digest': '0'*64})[0], 2)
        with closing(sqlite3.connect(self.backup)) as db:
            db.execute('UPDATE assets SET width=42'); db.commit()
        self.assertEqual(self.call()[0], 2)
        self.make_backup()
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('UPDATE assets SET width=43'); db.commit()
        self.assertEqual(self.call()[0], 2)
        self.assertFalse(self.output.exists())

    def test_required_review_fields_and_invalid_inputs_refuse(self):
        for key in ('backup','reviewed-snapshot-digest','authority-reference','quiescence-reference'):
            self.assertEqual(self.call(**{key: None})[0], 2)
        for key, value in (('reviewed-snapshot-digest','G'*64),('authority-reference','a/b'),
                           ('quiescence-reference',''),('database', self.root/'missing.sqlite')):
            self.assertEqual(self.call(**{key: value})[0], 2)
        self.assertFalse(self.output.exists())

    def test_same_file_hardlink_backup_and_existing_output_refuse_without_overwrite(self):
        alias = self.root/'hardlink.sqlite'; os.link(self.source, alias)
        before = self.source.read_bytes(), self.backup.read_bytes()
        for backup in (self.source, alias):
            self.assertEqual(self.call(backup=backup)[0], 2)
        for out in (self.source, self.backup, alias):
            self.assertEqual(self.call(out=out)[0], 2)
        self.assertEqual(before, (self.source.read_bytes(), self.backup.read_bytes()))
        self.assertFalse(self.output.exists())

    def test_wal_symlink_and_sidecar_backup_refuse(self):
        alias = self.root/'alias.sqlite'; alias.symlink_to(self.backup)
        self.assertEqual(self.call(backup=alias)[0], 2)
        sidecar = Path(str(self.backup)+'-journal'); sidecar.write_bytes(b'private-sidecar')
        self.assertEqual(self.call()[0], 2)
        sidecar.unlink()
        with closing(sqlite3.connect(self.backup)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            self.assertEqual(self.call()[0], 2)
        self.assertFalse(self.output.exists())

    def test_migration_entropy_and_receipt_failures_leave_inputs_and_no_output(self):
        before = self.source.read_bytes(), self.backup.read_bytes()
        with patch('alembic.command.upgrade', side_effect=RuntimeError('private-failure')):
            self.assertEqual(self.call()[0], 2)
        with patch('app.access.recovery.secrets.token_bytes', side_effect=RuntimeError('private-entropy')):
            self.assertEqual(self.call()[0], 2)
        self.assertEqual(before, (self.source.read_bytes(), self.backup.read_bytes()))
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("CREATE TRIGGER refuse_receipt BEFORE INSERT ON access_provisioning_receipts BEGIN SELECT RAISE(ABORT,'private-receipt'); END")
            db.commit()
        self.make_backup()
        before = self.source.read_bytes(), self.backup.read_bytes()
        self.assertEqual(self.call()[0], 2)
        self.assertEqual(before, (self.source.read_bytes(), self.backup.read_bytes()))
        self.assertFalse(self.output.exists())

    def test_receipt_trigger_cannot_reopen_candidate_access(self):
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("CREATE TRIGGER reopen AFTER INSERT ON access_provisioning_receipts BEGIN UPDATE access_accounts SET state='active'; END")
            db.commit()
        self.make_backup()
        self.assertEqual(self.call()[0], 2)
        self.assertFalse(self.output.exists())

    def test_each_candidate_has_fresh_key_and_refuses_overwrite(self):
        self.assertEqual(self.call()[0], 0)
        other = self.root/'second.sqlite'
        self.assertEqual(self.call(out=other)[0], 0)
        before = self.output.read_bytes()
        self.assertEqual(self.call()[0], 2)
        self.assertEqual(before, self.output.read_bytes())
        with ExistingDatabase(self.output, read_only=True)() as one, ExistingDatabase(other, read_only=True)() as two:
            self.assertNotEqual(one.execute('SELECT secret FROM access_admission_key').fetchall(), two.execute('SELECT secret FROM access_admission_key').fetchall())

    def test_existing_reviewed_plan_seal_is_invalidated(self):
        with ExistingDatabase(self.source, read_only=True)() as db:
            actor = db.execute("SELECT account_id FROM access_memberships WHERE library_id='family-a' AND role='owner'").fetchone()[0]
            plan = ProvisioningPlanner(db, clock=lambda: NOW).assets(library_id='family-a', operator_account_id=actor, asset_ids=[999])
        self.assertEqual(self.call()[0], 0)
        with ExistingDatabase(self.output, read_only=True)() as db:
            with self.assertRaises(PlanRejected): ProvisioningPlanner(db, clock=lambda: NOW).validate(plan)

    def test_in_memory_mutation_requires_transaction_and_rolls_back(self):
        with closing(sqlite3.connect(':memory:')) as db, closing(sqlite3.connect(self.source)) as source:
            source.backup(db)
            before = cli.snapshot_digest(db)
            with self.assertRaises(PlanRejected): _quarantine_access_state(db)
            db.execute('BEGIN IMMEDIATE')
            _quarantine_access_state(db)
            db.rollback()
            self.assertEqual(before, cli.snapshot_digest(db))

    def test_candidate_asgi_rejects_old_cookie_bearer_and_range_before_media_open(self):
        from fastapi.testclient import TestClient
        from app.access.runtime import RuntimeConfiguration
        self.assertEqual(self.call()[0], 0)
        app = RuntimeConfiguration(self.output, 'https://photohouse.test',
            (self.root/'unused-originals',), self.root/'unused-derived').build_app(clock=lambda: NOW)
        with TestClient(app, base_url='https://photohouse.test') as client:
            token = fixtures.LibraryReadTests.owner_token
            for credential in ({'Authorization': 'Bearer '+token},
                               {'Cookie': '__Host-ph_session='+token, 'Sec-Fetch-Site': 'same-origin'}):
                for path in ('/auth/session','/assets?library=family-a','/assets/101/media?library=family-a',
                             '/assets/101/thumbnail?library=family-a','/faces/1/crop?library=family-a'):
                    with patch('app.access.media.os.open', side_effect=AssertionError('Media must not open')):
                        response = client.get(path, headers=credential | {'Range': 'bytes=0-5'})
                    self.assertEqual(response.status_code, 401)
                    self.assertNotIn('content-range', response.headers)
                client.cookies.clear()

    def test_receipt_trigger_cannot_restore_old_plan_key(self):
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('CREATE TABLE synthetic_old_key AS SELECT secret FROM access_admission_key')
            db.execute("CREATE TRIGGER restore_key AFTER INSERT ON access_provisioning_receipts BEGIN UPDATE access_admission_key SET secret=(SELECT secret FROM synthetic_old_key); END")
            db.commit()
        self.make_backup()
        self.assertEqual(self.call()[0], 2)
        self.assertFalse(self.output.exists())

    def test_both_inputs_stay_read_locked_until_output_verification(self):
        real = cli.write_new
        checked = []
        def inspect(snapshot, output):
            for path in (self.source, self.backup):
                with closing(sqlite3.connect(path, timeout=0.01)) as writer:
                    writer.execute('UPDATE assets SET width=42')
                    with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                        writer.commit()
                    writer.rollback()
                checked.append(path)
            return real(snapshot, output)
        before = self.source.read_bytes(), self.backup.read_bytes()
        with patch.object(cli, 'write_new', side_effect=inspect):
            self.assertEqual(self.call()[0], 0)
        self.assertEqual(checked, [self.source, self.backup])
        self.assertEqual(before, (self.source.read_bytes(), self.backup.read_bytes()))

    def test_copy_failure_retains_only_incomplete_private_output(self):
        real = cli.copy_database
        def fail_output(source, destination):
            if destination.execute('PRAGMA database_list').fetchone()[2]:
                raise sqlite3.OperationalError('private-copy')
            return real(source, destination)
        before = self.source.read_bytes(), self.backup.read_bytes()
        with patch.object(cli, 'copy_database', side_effect=fail_output):
            self.assertEqual(self.call()[0], 2)
        self.assertTrue(self.output.exists())
        self.assertEqual(before, (self.source.read_bytes(), self.backup.read_bytes()))


if __name__ == '__main__':
    unittest.main()
