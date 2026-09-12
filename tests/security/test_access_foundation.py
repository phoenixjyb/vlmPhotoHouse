"""Real synthetic SQLite tests; no app imports, runtime config, media or providers."""
import concurrent.futures
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend/app'))
from access.bootstrap import bootstrap_owner
from access.credentials import (DUMMY_HASH, hash_password, invitation_digest, phone_login,
                                session_digest, verify_password)
from access.schema import apply_schema
from access.service import AccessDenied, AccessService, Conflict

# Reserved fictional NANP numbers: no actual recipient, OTP, SMS or network use.
OWNER = '+12025550100'
OTHER_OWNER = '+12025550101'
MEMBER = '+12025550102'
NEW = '+12025550103'
PASSWORD = 'Synthetic family passphrase!'
NOW = 2_000_000_000


def database():
    db = sqlite3.connect(':memory:')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('CREATE TABLE assets(id INTEGER PRIMARY KEY, path TEXT NOT NULL, status TEXT)')
    db.executemany('INSERT INTO assets VALUES (?,?,?)',
                   [(101, 'synthetic/a.jpg', 'active'), (102, 'synthetic/deleted.jpg', 'deleted'),
                    (201, 'synthetic/b.jpg', 'active'), (999, 'synthetic/unassigned.jpg', None)])
    db.commit()
    db.execute('BEGIN')
    apply_schema(db.execute)
    db.commit()
    return db


class AccessFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = database()
        cls.owner_id = bootstrap_owner(cls.template, phone=OWNER, password=PASSWORD, library_id='family-a')
        cls.other_id = bootstrap_owner(cls.template, phone=OTHER_OWNER, password=PASSWORD, library_id='family-b')
        service = AccessService(cls.template, clock=lambda: NOW)
        cls.owner_token = service.login(OWNER, PASSWORD)
        cls.other_token = service.login(OTHER_OWNER, PASSWORD)
        cls.member_code = service.invite(cls.owner_token, 'family-a', MEMBER)
        cls.member_token = service.register(MEMBER, PASSWORD, cls.member_code)
        cls.member_id = service.profile(cls.member_token)['account_id']
        cls.template.executemany('INSERT INTO access_asset_libraries VALUES (?,?)',
                                [(101, 'family-a'), (102, 'family-a'), (201, 'family-b')])
        cls.template.commit()

    @classmethod
    def tearDownClass(cls):
        cls.template.close()

    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.template.backup(self.db)
        self.addCleanup(self.db.close)
        self.now = NOW
        self.service = AccessService(self.db, clock=lambda: self.now)
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start()
            self.addCleanup(guard.stop)

    def deny(self, action):
        with self.assertRaisesRegex(AccessDenied, '^Access denied$'):
            action()

    def update(self, sql, args=()):
        self.db.execute(sql, args)
        self.db.commit()

    def decision(self, status, **kwargs):
        revision = self.service.profile(self.member_token)['memberships'][0]['revision']
        self.service.decide_membership(self.owner_token, 'family-a', self.member_id,
                                       expected_revision=revision, status=status, **kwargs)

    def test_registration_requires_correct_phone_and_owner_code(self):
        count = self.db.execute('SELECT COUNT(*) FROM access_accounts').fetchone()[0]
        self.deny(lambda: self.service.register(NEW, PASSWORD, 'not-a-code'))
        self.deny(lambda: self.service.register(NEW, PASSWORD, 'a' * 32))
        code = self.service.invite(self.owner_token, 'family-a', NEW)
        self.deny(lambda: self.service.register('+12025550109', PASSWORD, code))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM access_accounts').fetchone()[0], count)
        token = self.service.register('+1 (202) 555-0103', PASSWORD, code.upper())
        self.assertEqual(self.service.profile(token)['phone_login'], NEW)
        self.assertEqual(self.service.require(token, 'family-a', 'library.read'), 1)
        self.deny(lambda: self.service.require(token, 'family-b', 'library.read'))
        self.deny(lambda: self.service.require(token, 'family-a', 'media.original.read'))
        self.deny(lambda: self.service.require_operator(token))
        self.deny(lambda: self.service.register(NEW, PASSWORD, code))

    def test_no_account_or_owner_created_without_invite_even_when_empty(self):
        empty = database()
        self.addCleanup(empty.close)
        service = AccessService(empty, clock=lambda: NOW)
        self.deny(lambda: service.register(NEW, PASSWORD, 'a' * 32))
        self.assertEqual(empty.execute('SELECT COUNT(*) FROM access_accounts').fetchone()[0], 0)
        self.assertEqual(empty.execute('SELECT COUNT(*) FROM access_libraries').fetchone()[0], 0)

    def test_login_requires_password_and_does_not_reuse_invitation_as_credential(self):
        self.deny(lambda: self.service.login(MEMBER, 'Incorrect passphrase'))
        self.deny(lambda: self.service.login(NEW, PASSWORD))
        self.deny(lambda: self.service.login(MEMBER, self.member_code))
        token = self.service.login('+1 (202) 555-0102', PASSWORD)
        self.assertNotEqual(token, self.member_token)
        self.assertEqual(self.service.profile(token)['account_id'], self.member_id)
        self.assertEqual(self.service.list_asset_ids(token, 'family-a'), {'total': 1, 'asset_ids': [101]})

    def test_expired_cancelled_and_replaced_codes_fail(self):
        expired = self.service.invite(self.owner_token, 'family-a', NEW, lifetime=1)
        self.now += 1
        self.deny(lambda: self.service.register(NEW, PASSWORD, expired))
        cancelled = self.service.invite(self.owner_token, 'family-a', NEW)
        self.service.cancel_invitation(self.owner_token, 'family-a', cancelled)
        self.deny(lambda: self.service.register(NEW, PASSWORD, cancelled))
        old = self.service.invite(self.owner_token, 'family-a', NEW)
        replacement = self.service.invite(self.owner_token, 'family-a', NEW)
        self.deny(lambda: self.service.register(NEW, PASSWORD, old))
        self.assertNotEqual(invitation_digest(old), invitation_digest(replacement))

    def test_inviter_revocation_expiry_or_library_closure_invalidates_code(self):
        code = self.service.invite(self.owner_token, 'family-a', NEW)
        for sql, undo in [
            ("UPDATE access_accounts SET state='disabled' WHERE id=?", "UPDATE access_accounts SET state='active' WHERE id=?"),
            ("UPDATE access_memberships SET status='revoked' WHERE account_id=?", "UPDATE access_memberships SET status='approved' WHERE account_id=?"),
            (f"UPDATE access_memberships SET expires_at={NOW} WHERE account_id=?", "UPDATE access_memberships SET expires_at=NULL WHERE account_id=?"),
        ]:
            self.update(sql, (self.owner_id,))
            self.deny(lambda: self.service.register(NEW, PASSWORD, code))
            self.update(undo, (self.owner_id,))
        self.update("UPDATE access_libraries SET state='closed' WHERE id='family-a'")
        self.deny(lambda: self.service.register(NEW, PASSWORD, code))

    def test_existing_account_accepts_invite_without_password_reset(self):
        code = self.service.invite(self.other_token, 'family-b', MEMBER)
        self.deny(lambda: self.service.register(MEMBER, 'Attacker chosen passphrase!', code))
        self.deny(lambda: self.service.accept_invitation(self.owner_token, code))
        self.service.accept_invitation(self.member_token, code)
        self.assertEqual(self.service.list_asset_ids(self.member_token, 'family-b')['asset_ids'], [201])
        self.deny(lambda: self.service.accept_invitation(self.member_token, code))
        self.assertEqual(self.service.profile(self.service.login(MEMBER, PASSWORD))['account_id'], self.member_id)

    def test_revoked_member_needs_a_new_owner_decision(self):
        self.decision('revoked')
        self.deny(lambda: self.service.require(self.member_token, 'family-a', 'library.read'))
        self.deny(lambda: self.service.accept_invitation(self.member_token, self.member_code))
        code = self.service.invite(self.owner_token, 'family-a', MEMBER)
        self.service.accept_invitation(self.member_token, code)
        self.assertEqual(self.service.require(self.member_token, 'family-a', 'library.read'), 3)

    def test_stale_invite_cannot_override_a_later_membership_decision(self):
        self.decision('revoked')
        code = self.service.invite(self.owner_token, 'family-a', MEMBER)
        self.decision('rejected')
        self.deny(lambda: self.service.accept_invitation(self.member_token, code))

    def test_membership_and_session_denials_are_real_database_checks(self):
        for state in ('requested', 'rejected', 'revoked'):
            self.update('UPDATE access_memberships SET status=? WHERE account_id=?', (state, self.member_id))
            self.deny(lambda: self.service.asset_metadata(self.member_token, 'family-a', 101))
        self.update("UPDATE access_memberships SET status='approved', expires_at=? WHERE account_id=?", (NOW, self.member_id))
        self.deny(lambda: self.service.require(self.member_token, 'family-a', 'library.read'))
        self.update('UPDATE access_memberships SET expires_at=NULL WHERE account_id=?', (self.member_id,))
        self.service.logout(self.member_token)
        self.service.logout(self.member_token)
        self.deny(lambda: self.service.profile(self.member_token))
        self.deny(lambda: self.service.require('unknown', 'family-a', 'library.read'))
        self.deny(lambda: self.service.require(None, 'family-a', 'library.read'))

    def test_account_disable_and_session_expiry(self):
        self.update("UPDATE access_accounts SET state='disabled' WHERE id=?", (self.member_id,))
        self.deny(lambda: self.service.profile(self.member_token))
        self.deny(lambda: self.service.login(MEMBER, PASSWORD))
        self.update("UPDATE access_accounts SET state='active' WHERE id=?", (self.member_id,))
        self.now += self.service.SESSION_SECONDS
        self.deny(lambda: self.service.profile(self.member_token))

    def test_original_permission_is_separate_and_revision_rechecked(self):
        self.deny(lambda: self.service.asset_metadata(self.member_token, 'family-a', 101, original=True))
        self.deny(lambda: self.service.asset_metadata(self.owner_token, 'family-a', 101, original=True))
        old_revision = self.service.require(self.member_token, 'family-a', 'library.read')
        self.decision('approved', originals=True)
        self.assertEqual(self.service.asset_metadata(self.member_token, 'family-a', 101, original=True)['id'], 101)
        self.deny(lambda: self.service.asset_metadata(self.member_token, 'family-a', 101, expected_revision=old_revision))
        self.decision('approved', originals=False)
        self.deny(lambda: self.service.asset_metadata(self.member_token, 'family-a', 101, original=True))

    def test_unknown_capabilities_writes_and_operator_privilege_are_denied(self):
        for capability in ('library.destroy', 'library.curate', 'library.upload', 'voice.read', '*', 'system.jobs'):
            self.deny(lambda: self.service.require(self.member_token, 'family-a', capability))
        self.deny(lambda: self.service.invite(self.member_token, 'family-a', NEW))
        self.deny(lambda: self.service.invite(self.other_token, 'family-a', NEW))
        self.service.require_operator(self.owner_token)
        self.deny(lambda: self.service.require(self.owner_token, 'family-b', 'library.read'))
        self.update('DELETE FROM access_operators WHERE account_id=?', (self.owner_id,))
        self.assertEqual(self.service.require(self.owner_token, 'family-a', 'library.members.manage'), 1)
        self.deny(lambda: self.service.require_operator(self.owner_token))

    def test_cross_library_deleted_unassigned_ids_and_counts(self):
        for asset_id in (201, 102, 999, 987654):
            self.deny(lambda: self.service.asset_metadata(self.member_token, 'family-a', asset_id))
        self.assertEqual(self.service.list_asset_ids(self.member_token, 'family-a', offset=1),
                         {'total': 1, 'asset_ids': []})
        self.deny(lambda: self.service.list_asset_ids(self.member_token, 'family-b'))

    def test_stale_owner_decision_and_owner_removal_rejected(self):
        self.decision('approved', originals=True)
        with self.assertRaises(Conflict):
            self.service.decide_membership(self.owner_token, 'family-a', self.member_id,
                                           expected_revision=1, status='revoked')
        self.deny(lambda: self.service.decide_membership(self.owner_token, 'family-a', self.owner_id,
                                                        expected_revision=1, status='revoked'))

    def test_codes_sessions_and_passwords_are_not_stored_in_plaintext(self):
        code = self.service.invite(self.owner_token, 'family-a', NEW)
        dump = '\n'.join(self.db.iterdump())
        for secret in (PASSWORD, code, code.replace('-', ''), self.owner_token, self.member_token):
            self.assertNotIn(secret, dump)
        self.assertIn(invitation_digest(code), dump)
        self.assertIn(session_digest(self.owner_token), dump)
        self.assertNotIn('phone_verified', dump)

    def test_audit_failure_rolls_back_registration_and_code_consumption(self):
        code = self.service.invite(self.owner_token, 'family-a', NEW)
        with patch.object(self.service, '_audit', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                self.service.register(NEW, PASSWORD, code)
        self.assertIsNone(self.db.execute('SELECT id FROM access_accounts WHERE phone_login=?', (NEW,)).fetchone())
        self.assertEqual(self.db.execute('SELECT consumed FROM access_invitations WHERE digest=?',
                                        (invitation_digest(code),)).fetchone()[0], 0)

    def test_concurrent_redemption_exactly_one_account_and_membership(self):
        code = self.service.invite(self.owner_token, 'family-a', NEW)
        with tempfile.TemporaryDirectory(prefix='photohouse-synthetic-access-') as directory:
            path = Path(directory) / 'synthetic.sqlite'
            target = sqlite3.connect(path)
            self.db.backup(target)
            target.close()
            barrier = threading.Barrier(2)
            def redeem():
                conn = sqlite3.connect(path, timeout=10)
                conn.execute('PRAGMA foreign_keys=ON')
                service = AccessService(conn, clock=lambda: NOW)
                barrier.wait()
                try:
                    service.register(NEW, PASSWORD, code)
                    return 'accepted'
                except AccessDenied:
                    return 'denied'
                finally:
                    conn.close()
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: redeem(), range(2)))
            self.assertCountEqual(results, ['accepted', 'denied'])
            conn = sqlite3.connect(path)
            try:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM access_accounts WHERE phone_login=?', (NEW,)).fetchone()[0], 1)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM access_memberships WHERE account_id IN '
                                              '(SELECT id FROM access_accounts WHERE phone_login=?)', (NEW,)).fetchone()[0], 1)
            finally:
                conn.close()  # Close before TemporaryDirectory cleanup, including on Windows.

    def test_weak_password_does_not_consume_invitation(self):
        code = self.service.invite(self.owner_token, 'family-a', NEW)
        with self.assertRaises(ValueError):
            self.service.register(NEW, 'short', code)
        self.assertEqual(self.db.execute('SELECT consumed FROM access_invitations WHERE digest=?',
                                        (invitation_digest(code),)).fetchone()[0], 0)


class CredentialTests(unittest.TestCase):
    def test_real_scrypt_roundtrip_and_unique_salt(self):
        first, second = hash_password(PASSWORD), hash_password(PASSWORD)
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password(PASSWORD, first))
        self.assertFalse(verify_password('wrong passphrase', first))
        self.assertFalse(verify_password(PASSWORD, DUMMY_HASH))
        self.assertFalse(verify_password(PASSWORD, first.replace('131072', '999999999')))
        self.assertFalse(verify_password(PASSWORD, 'corrupt'))
        self.assertFalse(verify_password('\ud800', first))

    def test_canonical_phone_login_and_invalid_inputs(self):
        self.assertEqual(phone_login('+1 (202) 555-0100'), OWNER)
        for invalid in ('12025550100', '2025550100', '+１２３４５６７８９', '+0123456789', '+1;DROP', None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                phone_login(invalid)


class MigrationTests(unittest.TestCase):
    def test_additive_schema_preserves_legacy_ids_paths_and_has_no_auto_grants(self):
        db = database()
        self.addCleanup(db.close)
        self.assertEqual(db.execute('SELECT id,path FROM assets ORDER BY id').fetchall(),
                         [(101,'synthetic/a.jpg'),(102,'synthetic/deleted.jpg'),(201,'synthetic/b.jpg'),(999,'synthetic/unassigned.jpg')])
        for table in ('access_accounts', 'access_memberships', 'access_asset_libraries'):
            self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO access_asset_libraries VALUES (987654,'missing')")
        db.rollback()

    def test_schema_ddl_failure_rolls_back(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.execute('BEGIN')
        counter = 0
        def execute(statement):
            nonlocal counter
            counter += 1
            if counter == 4:
                raise RuntimeError('synthetic migration failure')
            db.execute(statement)
        with self.assertRaises(RuntimeError):
            apply_schema(execute)
        db.rollback()
        self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [])

    def test_alembic_wrapper_sql_and_refusal_of_unsafe_downgrade(self):
        path = ROOT / 'backend/migrations/versions/e3a9b1c7d402_access_foundation.py'
        spec = importlib.util.spec_from_file_location('synthetic_access_revision', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        self.assertEqual(migration.down_revision, 'd2b7e4f6a901')
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('CREATE TABLE assets(id INTEGER PRIMARY KEY)')
        bind = SimpleNamespace(dialect=SimpleNamespace(name='sqlite'), exec_driver_sql=db.execute,
                               connection=SimpleNamespace(driver_connection=db))
        # Exercise actual migration wrapper/SQL with a minimal Alembic binding double.
        # This is not a claim that installed Alembic/SQLAlchemy migration execution passed.
        import access.schema
        modules = {'alembic': SimpleNamespace(op=SimpleNamespace(get_bind=lambda: bind)),
                   'app': SimpleNamespace(), 'app.access': SimpleNamespace(), 'app.access.schema': access.schema}
        with patch.dict(sys.modules, modules):
            migration.upgrade()
            self.assertTrue(db.in_transaction)
            db.commit()
            self.assertEqual(db.execute('SELECT COUNT(*) FROM access_accounts').fetchone()[0], 0)
            bind.dialect.name = 'postgresql'
            with self.assertRaises(RuntimeError):
                migration.upgrade()
        with self.assertRaises(RuntimeError):
            migration.downgrade()

    def test_store_refuses_missing_foreign_keys_and_pending_transactions(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        with self.assertRaises(ValueError):
            AccessService(db)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN')
        with self.assertRaises(ValueError):
            AccessService(db)


if __name__ == '__main__':
    unittest.main()
