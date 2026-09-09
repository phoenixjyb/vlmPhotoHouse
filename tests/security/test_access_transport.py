"""Real in-process account HTTP + SQLite tests. No app.main/runtime imports."""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend/app'))
from access.admission import Admission, AdmissionDenied, STATEMENTS, apply_schema
from access.bootstrap import bootstrap_owner
from access.credentials import session_digest
from access.service import AccessDenied, AccessService
from access.transport import AccessRuntime, COOKIE, csrf_token, router
from test_access_foundation import database, OWNER, MEMBER, NEW, PASSWORD, NOW

ORIGIN = 'https://photohouse.test'


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.db = database()
        self.addCleanup(self.db.close)
        self.db.execute('BEGIN')
        apply_schema(self.db.execute)
        self.db.commit()
        self.now = NOW
        self.service = AccessService(self.db, clock=lambda: self.now)
        self.admission = Admission(self.service)

    def attempt(self, phone=MEMBER, source='192.0.2.1', fail=False):
        with self.admission.attempt(source, phone):
            if fail:
                raise AccessDenied('Access denied')

    def test_account_budget_canonicalizes_and_counts_success_and_failure(self):
        with self.assertRaises(AccessDenied):
            self.attempt(fail=True)
        for i in range(5):
            self.attempt(phone='+1 (202) 555-0102', source=f'192.0.2.{i+2}')
        with self.assertRaises(AdmissionDenied):
            self.attempt(source='198.51.100.1')
        self.assertEqual(self.db.execute('SELECT count(*) FROM access_kdf_slot').fetchone()[0], 0)
        dump = '\n'.join(self.db.iterdump())
        self.assertNotIn('192.0.2.', dump)
        self.assertNotIn(MEMBER, dump)

    def test_source_limit_collapses_ipv4_mapped_ipv6(self):
        for i in range(20):
            self.attempt(phone=f'+1202555{i:04d}', source='::ffff:192.0.2.1')
        with self.assertRaises(AdmissionDenied):
            self.attempt(phone=NEW)

    def test_global_limit_bounds_random_key_growth(self):
        for i in range(60):
            self.attempt(phone=f'+1202555{i:04d}', source=f'192.0.2.{i+1}')
        for i in range(30):
            with self.assertRaises(AdmissionDenied):
                self.attempt(phone=f'+1202556{i:04d}', source=f'198.51.100.{i+1}')
        self.assertLessEqual(self.db.execute('SELECT count(*) FROM access_attempts').fetchone()[0], 121)

    def test_window_expiry_and_backward_clock(self):
        for _ in range(6):
            self.attempt()
        self.now -= 10
        with self.assertRaises(AdmissionDenied):
            self.attempt()
        self.now = NOW + 600
        self.attempt()
        self.assertEqual(self.db.execute('SELECT max(attempts) FROM access_attempts').fetchone()[0], 1)

    def test_concurrent_connections_cannot_overlap_slot_and_restart_cannot_clear_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.sqlite'
            seed = sqlite3.connect(path)
            self.db.backup(seed)
            seed.close()
            @contextmanager
            def connection():
                conn = sqlite3.connect(path)
                conn.execute('PRAGMA foreign_keys=ON')
                try:
                    yield conn
                finally:
                    conn.close()
            entered = threading.Event()
            release = threading.Event()
            outcomes = []
            def first():
                try:
                    with connection() as conn:
                        admission = Admission(AccessService(conn, clock=lambda: NOW))
                        with admission.attempt('192.0.2.1', MEMBER):
                            entered.set()
                            if not release.wait(10):
                                raise AssertionError('Test synchronization timed out')
                    outcomes.append('finished')
                except BaseException as exc:
                    outcomes.append(exc)
            worker = threading.Thread(target=first)
            worker.start()
            try:
                self.assertTrue(entered.wait(10))
                with connection() as conn:
                    other = Admission(AccessService(conn, clock=lambda: NOW + 9999))
                    with self.assertRaises(AdmissionDenied):
                        with other.attempt('192.0.2.2', NEW):
                            self.fail('Overlapping KDF slot')
            finally:
                release.set()
                worker.join(10)
            self.assertFalse(worker.is_alive())
            self.assertEqual(outcomes, ['finished'])
            with connection() as conn:
                with Admission(AccessService(conn, clock=lambda: NOW)).attempt('192.0.2.2', NEW):
                    pass
                conn.execute("INSERT INTO access_kdf_slot VALUES (1, 'synthetic-crashed-claim')")
                conn.commit()
            with connection() as conn:
                with self.assertRaises(AdmissionDenied):
                    with Admission(AccessService(conn, clock=lambda: NOW + 99999)).attempt('192.0.2.3', OWNER):
                        self.fail('Crash must leave admission closed')

    def test_missing_migration_fails_closed(self):
        self.db.execute('DROP TABLE access_admission_key')
        self.db.commit()
        with self.assertRaises(sqlite3.OperationalError):
            self.attempt()
        self.assertFalse(self.db.in_transaction)

    def test_migration_additive_and_failure_rolls_back(self):
        with database() as conn:
            before = conn.execute('SELECT * FROM assets ORDER BY id').fetchall()
            conn.execute('BEGIN')
            apply_schema(conn.execute)
            self.assertEqual(conn.execute('SELECT * FROM assets ORDER BY id').fetchall(), before)
            self.assertEqual(conn.execute('SELECT count(*) FROM access_accounts').fetchone()[0], 0)
            conn.rollback()
            self.assertEqual(conn.execute("SELECT count(*) FROM sqlite_master WHERE name='access_attempts'").fetchone()[0], 0)
            conn.execute('BEGIN')
            for statement in STATEMENTS[:2]:
                conn.execute(statement)
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute(STATEMENTS[0])
            conn.rollback()
            self.assertEqual(conn.execute("SELECT count(*) FROM sqlite_master WHERE name='access_admission_key'").fetchone()[0], 0)
        conn.close()

    def test_migration_wrapper_uses_real_sql_but_is_not_an_alembic_rehearsal(self):
        spec = importlib.util.spec_from_file_location('admission_migration', ROOT / 'backend/migrations/versions/f4c1a8d2e703_access_admission.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        conn = database()
        self.addCleanup(conn.close)
        bind = SimpleNamespace(dialect=SimpleNamespace(name='sqlite'),
                               connection=SimpleNamespace(driver_connection=conn), exec_driver_sql=conn.execute)
        with patch.dict(sys.modules, {'alembic': SimpleNamespace(op=SimpleNamespace(get_bind=lambda: bind)),
                                      'app.access.admission': sys.modules['access.admission']}):
            module.upgrade()
        self.assertTrue(conn.in_transaction)
        self.assertEqual(len(conn.execute('SELECT secret FROM access_admission_key').fetchone()[0]), 32)
        conn.rollback()
        self.assertEqual(module.down_revision, 'e3a9b1c7d402')
        with self.assertRaises(RuntimeError):
            module.downgrade()


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = database()
        cls.template.execute('BEGIN')
        apply_schema(cls.template.execute)
        cls.template.commit()
        cls.owner_id = bootstrap_owner(cls.template, phone=OWNER, password=PASSWORD, library_id='family-a')
        service = AccessService(cls.template, clock=lambda: NOW)
        cls.owner_token = service.login(OWNER, PASSWORD)
        cls.code = service.invite(cls.owner_token, 'family-a', MEMBER)
        cls.member_token = service.register(MEMBER, PASSWORD, cls.code)
        cls.member_id = service.profile(cls.member_token)['account_id']

    @classmethod
    def tearDownClass(cls):
        cls.template.close()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'synthetic.sqlite'
        seed = sqlite3.connect(self.path)
        self.template.backup(seed)
        seed.close()
        self.now = NOW
        self.runtime = AccessRuntime(self.connection, ORIGIN, clock=lambda: self.now)
        app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
        app.state.access_runtime = self.runtime
        app.include_router(router)
        self.app = app
        self.client = TestClient(app, base_url=ORIGIN, client=('192.0.2.10', 12345))
        self.client.headers['Sec-Fetch-Site'] = 'same-origin'
        self.addCleanup(self.client.close)
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start()
            self.addCleanup(guard.stop)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path)
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            yield conn
        finally:
            conn.close()

    def mutate(self, sql, args=()):
        with self.connection() as conn:
            conn.execute(sql, args)
            conn.commit()

    def bearer(self, token=None):
        return {'Authorization': 'Bearer ' + (token or self.member_token)}

    def login(self, mode='native', **kwargs):
        body = {'phone': MEMBER, 'password': PASSWORD, 'transport': mode}
        return self.client.post('/auth/login', json=body, **kwargs)

    def test_native_login_session_and_logout_use_real_session_rows(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('set-cookie', response.headers)
        token = response.json()['access_token']
        self.assertEqual(response.json()['token_type'], 'Bearer')
        self.assertNotEqual(token, self.member_token)
        response = self.client.get('/auth/session', headers=self.bearer(token))
        self.assertEqual(response.json()['account_id'], self.member_id)
        self.assertNotIn('csrf_token', response.json())
        with self.connection() as conn:
            dump = '\n'.join(conn.iterdump())
            self.assertIn(session_digest(token), dump)
            self.assertNotIn(token, dump)
            self.assertNotIn(PASSWORD, dump)
        self.assertEqual(self.client.post('/auth/logout', headers=self.bearer(token)).status_code, 200)
        self.assertEqual(self.client.get('/auth/session', headers=self.bearer(token)).status_code, 401)

    def test_web_cookie_csrf_logout_and_no_session_token_in_json(self):
        response = self.login('web', headers={'Origin': ORIGIN})
        self.assertEqual(response.status_code, 200)
        cookie = response.headers['set-cookie']
        for attribute in ('Secure', 'HttpOnly', 'SameSite=strict', 'Path=/', 'Max-Age=86400'):
            self.assertIn(attribute, cookie)
        self.assertNotIn('Domain=', cookie)
        token = self.client.cookies.get(COOKIE)
        self.assertNotIn(token, response.text)
        csrf = response.json()['csrf_token']
        self.assertEqual(csrf, csrf_token(token))
        self.assertEqual(self.client.get('/auth/session').json()['csrf_token'], csrf)
        for headers in ({}, {'Origin': ORIGIN}, {'X-CSRF-Token': csrf},
                        {'Origin': 'https://evil.test', 'X-CSRF-Token': csrf},
                        {'Origin': ORIGIN, 'X-CSRF-Token': 'bad'}):
            self.assertEqual(self.client.post('/auth/logout', headers=headers).status_code, 403)
        self.assertEqual(self.client.get('/auth/session').status_code, 200)
        response = self.client.post('/auth/logout', headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Max-Age=0', response.headers['set-cookie'])
        self.assertEqual(self.client.get('/auth/session').status_code, 401)

    def test_cookie_reads_need_positive_same_origin_signal_but_native_does_not(self):
        self.client.cookies.set(COOKIE, self.member_token)
        del self.client.headers['Sec-Fetch-Site']
        for headers in ({}, {'Sec-Fetch-Site':'none'}, {'Sec-Fetch-Site':'same-site'},
                        {'Referer':'https://sibling.photohouse.test/'}):
            self.assertEqual(self.client.get('/auth/session',headers=headers).status_code,403)
        self.assertEqual(self.client.get('/auth/session',headers={'Origin':ORIGIN}).status_code,200)
        self.assertEqual(self.client.get('/auth/session',headers={'Sec-Fetch-Site':'same-origin'}).status_code,200)
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/auth/session',headers=self.bearer()).status_code,200)

    def test_expired_web_session_clears_cookie_before_retrying_login(self):
        response = self.login('web', headers={'Origin': ORIGIN})
        self.assertEqual(response.status_code, 200)
        self.mutate('UPDATE access_sessions SET expires_at=0')
        response = self.client.get('/auth/session')
        self.assertEqual(response.status_code, 401)
        self.assertIn('Max-Age=0', response.headers['set-cookie'])
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertFalse(self.client.cookies)
        self.assertEqual(self.login('web', headers={'Origin': ORIGIN}).status_code, 200)

    def test_profile_available_uses_server_time_and_library_state(self):
        def available():
            return self.client.get('/auth/session', headers=self.bearer()).json()['memberships'][0]['available']
        self.assertTrue(available())
        self.mutate("UPDATE access_libraries SET state='closed'")
        self.assertFalse(available())
        self.mutate("UPDATE access_libraries SET state='active'")
        self.mutate('UPDATE access_memberships SET expires_at=? WHERE account_id=?', (NOW,self.member_id))
        self.assertFalse(available())
        self.mutate('UPDATE access_memberships SET expires_at=NULL WHERE account_id=?', (self.member_id,))
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (self.member_id,))
        self.assertFalse(available())

    def test_web_login_csrf_native_origin_and_session_overwrite_rejected(self):
        self.assertEqual(self.login('web').status_code, 403)
        self.assertEqual(self.login('native', headers={'Origin': ORIGIN}).status_code, 403)
        self.assertEqual(self.login('web', headers={'Origin': 'https://evil.test'}).status_code, 403)
        self.assertEqual(self.login(headers=self.bearer()).status_code, 401)
        self.client.cookies.set(COOKIE, self.member_token)
        self.assertEqual(self.login('web', headers={'Origin': ORIGIN}).status_code, 401)

    def test_registration_invitation_and_password_flow(self):
        invite = self.client.post('/libraries/family-a/invitations', headers=self.bearer(self.owner_token), json={'phone': NEW})
        self.assertEqual(invite.status_code, 201)
        code = invite.json()['code']
        body = {'phone': NEW, 'password': PASSWORD, 'code': code, 'transport': 'native'}
        response = self.client.post('/auth/register', json=body)
        self.assertEqual(response.status_code, 201)
        token = response.json()['access_token']
        profile = self.client.get('/auth/session', headers=self.bearer(token)).json()
        self.assertEqual(profile['memberships'][0]['status'], 'approved')
        self.assertEqual(profile['memberships'][0]['role'], 'viewer')
        self.assertEqual(profile['memberships'][0]['originals'], 0)
        self.assertEqual(self.client.post('/auth/register', json=body).status_code, 401)
        # Existing account cannot use registration to replace its password.
        body['password'] = 'Attacker selected passphrase'
        self.assertEqual(self.client.post('/auth/register', json=body).status_code, 401)
        signed_in = self.client.post('/auth/login', json={'phone': NEW, 'password': PASSWORD, 'transport': 'native'})
        self.assertEqual(signed_in.status_code, 200)

    def test_no_invitation_no_signup_and_weak_password_does_not_consume(self):
        body = {'phone': NEW, 'password': PASSWORD, 'code': 'a' * 32, 'transport': 'native'}
        self.assertEqual(self.client.post('/auth/register', json=body).status_code, 401)
        code = self.client.post('/libraries/family-a/invitations', headers=self.bearer(self.owner_token), json={'phone': NEW}).json()['code']
        body.update(code=code, password='short')
        self.assertEqual(self.client.post('/auth/register', json=body).status_code, 401)
        body['password'] = PASSWORD
        self.assertEqual(self.client.post('/auth/register', json=body).status_code, 201)

    def test_invites_require_owner_and_cancelled_codes_fail(self):
        for headers in ({}, self.bearer()):
            self.assertEqual(self.client.post('/libraries/family-a/invitations', headers=headers, json={'phone': NEW}).status_code, 401)
        self.assertEqual(self.client.post('/libraries/family-b/invitations', headers=self.bearer(self.owner_token), json={'phone': NEW}).status_code, 401)
        response = self.client.post('/libraries/family-a/invitations', headers=self.bearer(self.owner_token), json={'phone': NEW})
        code = response.json()['code']
        self.assertEqual(self.client.post('/libraries/family-a/invitations/cancel', headers=self.bearer(), json={'code': code}).status_code, 401)
        self.assertEqual(self.client.post('/libraries/family-a/invitations/cancel', headers=self.bearer(self.owner_token), json={'code': code}).status_code, 200)
        self.assertEqual(self.client.post('/auth/register', json={'phone': NEW, 'password': PASSWORD, 'code': code, 'transport': 'native'}).status_code, 401)

    def test_existing_member_accepts_fresh_invitation_only_after_login(self):
        self.mutate("UPDATE access_memberships SET status='revoked',revision=revision+1 WHERE account_id=?", (self.member_id,))
        code = self.client.post('/libraries/family-a/invitations', headers=self.bearer(self.owner_token), json={'phone': MEMBER}).json()['code']
        self.assertEqual(self.client.post('/auth/invitations/accept', json={'code': code}).status_code, 401)
        self.assertEqual(self.client.post('/auth/invitations/accept', headers=self.bearer(self.owner_token), json={'code': code}).status_code, 401)
        self.assertEqual(self.client.post('/auth/invitations/accept', headers=self.bearer(), json={'code': code}).status_code, 200)
        self.assertEqual(self.client.post('/auth/invitations/accept', headers=self.bearer(), json={'code': code}).status_code, 401)

    def test_session_disable_expiry_and_revoked_membership_readback(self):
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (self.member_id,))
        self.assertEqual(self.client.get('/auth/session', headers=self.bearer()).json()['memberships'][0]['status'], 'revoked')
        self.mutate("UPDATE access_accounts SET state='disabled' WHERE id=?", (self.member_id,))
        self.assertEqual(self.client.get('/auth/session', headers=self.bearer()).status_code, 401)
        self.mutate("UPDATE access_accounts SET state='active' WHERE id=?", (self.member_id,))
        self.now = NOW + 86400
        self.assertEqual(self.client.get('/auth/session', headers=self.bearer()).status_code, 401)

    def test_ambiguous_malformed_and_browser_bearer_credentials_rejected(self):
        for headers in ({'Authorization': 'Basic anything'}, {'Authorization': 'Bearer bad'},
                        {**self.bearer(), 'Cookie': f'{COOKIE}={self.member_token}'},
                        {'Cookie': f'{COOKIE}={self.member_token}; {COOKIE}={self.owner_token}'},
                        {**self.bearer(), 'Origin': ORIGIN},
                        [('Authorization', 'Bearer ' + self.member_token), ('Authorization', 'Bearer ' + self.owner_token)]):
            with self.subTest(headers=headers):
                self.assertIn(self.client.get('/auth/session', headers=headers).status_code, (400, 401))

    def test_limits_persist_across_requests_and_forwarded_header_changes_before_kdf(self):
        # Counters are real SQL. Prevent actual KDF here to prove admission order.
        with patch('access.service.verify_password', return_value=False) as kdf:
            for i in range(6):
                self.assertEqual(self.login(headers={'X-Forwarded-For': f'198.51.100.{i+1}'}).status_code, 401)
            self.assertEqual(kdf.call_count, 6)
            response = self.login(headers={'X-Forwarded-For': '203.0.113.20'})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(kdf.call_count, 6)
            self.app.state.access_runtime = AccessRuntime(self.connection, ORIGIN, clock=lambda: self.now)
            self.assertEqual(self.login().status_code, 429)
            # Registration shares the same account budget and must not reach hash.
            with patch('access.service.hash_password', side_effect=AssertionError('KDF bypass')):
                response = self.client.post('/auth/register', json={'phone': MEMBER, 'password': PASSWORD, 'code': 'a' * 32, 'transport': 'native'})
                self.assertEqual(response.status_code, 429)

    def test_busy_slot_denies_before_password_work_and_does_not_steal_claim(self):
        self.mutate("INSERT INTO access_kdf_slot VALUES (1,'synthetic-other-worker')")
        with patch('access.service.verify_password', side_effect=AssertionError('KDF bypass')):
            self.assertEqual(self.login().status_code, 429)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT claim FROM access_kdf_slot').fetchone()[0], 'synthetic-other-worker')

    def test_forwarded_headers_cannot_evade_source_budget_with_different_accounts(self):
        with patch('access.service.verify_password', return_value=False) as kdf:
            for i in range(21):
                response = self.client.post('/auth/login',
                    json={'phone': f'+1202555{i:04d}', 'password': PASSWORD, 'transport': 'native'},
                    headers={'X-Forwarded-For': f'198.51.100.{i+1}', 'Forwarded': f'for=198.51.100.{i+1}'})
                self.assertEqual(response.status_code, 401 if i < 20 else 429)
            self.assertEqual(kdf.call_count, 20)

    def test_cookie_invitation_writes_require_csrf_before_domain_changes(self):
        self.client.cookies.set(COOKIE, self.owner_token)
        with patch.object(AccessRuntime, 'call', side_effect=AssertionError('Domain call before CSRF')):
            for path, body in (('/libraries/family-a/invitations', {'phone': NEW}),
                               ('/libraries/family-a/invitations/cancel', {'code': self.code}),
                               ('/auth/invitations/accept', {'code': self.code})):
                self.assertEqual(self.client.post(path, json=body, headers={'Origin': ORIGIN}).status_code, 403)
        response = self.client.post('/libraries/family-a/invitations', json={'phone': NEW},
            headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf_token(self.owner_token)})
        self.assertEqual(response.status_code, 201)

    def test_unexpected_adapter_failure_does_not_echo_private_exception(self):
        with patch.object(AccessRuntime, 'call', side_effect=RuntimeError(PASSWORD)):
            response = self.login()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'detail': 'Access unavailable'})
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_uniform_login_denials(self):
        results = []
        for phone, password in ((MEMBER, 'Incorrect passphrase'), (NEW, PASSWORD), ('invalid', PASSWORD)):
            response = self.client.post('/auth/login', json={'phone': phone, 'password': password, 'transport': 'native'})
            results.append((response.status_code, response.json()))
        self.assertEqual(results, [(401, {'detail': 'Access denied'})] * 3)

    def test_size_type_duplicate_field_and_surrogate_input_denied_without_echo(self):
        bodies = ['x' * 2049, '{', '[]', '{"phone":"a","phone":"b"}',
                  '{"phone":"\\ud800","password":"p","transport":"native"}',
                  json.dumps({'phone': MEMBER, 'password': PASSWORD, 'transport': 'native', 'owner': True}),
                  json.dumps({'phone': MEMBER, 'password': [PASSWORD], 'transport': 'native'})]
        with patch('access.service.verify_password', side_effect=AssertionError('KDF bypass')):
            for body in bodies:
                response = self.client.post('/auth/login', content=body, headers={'Content-Type': 'application/json'})
                self.assertIn(response.status_code, (400, 413))
                self.assertNotIn(PASSWORD, response.text)
            response = self.client.post('/auth/login', content='{}', headers={'Content-Type': 'application/json', 'Content-Encoding': 'gzip'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.client.post('/auth/login', data={'phone': MEMBER}).status_code, 400)

    def test_stream_limit_applies_without_content_length(self):
        response = self.client.post('/auth/login', content=iter([b' ' * 1024, b'x' * 1025]), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 413)

    def test_origin_host_scheme_query_and_fetch_site_fail_closed(self):
        for path, headers in (('/auth/session?token=synthetic', self.bearer()),
                              ('/auth/session', {**self.bearer(), 'Host': 'evil.test'}),
                              ('http://photohouse.test/auth/session', self.bearer()),
                              ('/auth/session', {**self.bearer(), 'Sec-Fetch-Site': 'cross-site'})):
            self.assertIn(self.client.get(path, headers=headers).status_code, (400, 403))
        with self.assertRaises(ValueError):
            AccessRuntime(self.connection, 'http://photohouse.test')

    def test_missing_runtime_and_migration_deny_without_fallback(self):
        self.app.state.access_runtime = None
        self.assertEqual(self.login().status_code, 503)
        self.app.state.access_runtime = self.runtime
        self.mutate('DROP TABLE access_attempts')
        self.assertEqual(self.login().status_code, 503)
        with self.connection() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM sqlite_master WHERE name='access_attempts'").fetchone()[0], 0)

    def test_account_responses_never_cache_or_echo_credentials(self):
        responses = [self.client.get('/auth/session'), self.login(),
                     self.client.post('/auth/login', content='bad', headers={'Content-Type': 'application/json'}),
                     self.client.post('/libraries/family-b/invitations', headers=self.bearer(), json={'phone': NEW})]
        for response in responses:
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(response.headers['referrer-policy'], 'no-referrer')
            self.assertNotIn(PASSWORD, response.text)
            self.assertNotIn(self.member_token, response.text)
            self.assertNotIn('access-control-allow-origin', response.headers)

    def test_runtime_account_router_matches_inventory(self):
        inventory = json.loads((ROOT / 'docs/security/route_capabilities.json').read_text())
        expected = {(r['method'], r['path']) for r in inventory['routes'] if r['source'] == 'backend/app/access/transport.py'}
        actual = {(method, route.path) for route in self.app.routes for method in route.methods}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 7)


if __name__ == '__main__':
    unittest.main()
