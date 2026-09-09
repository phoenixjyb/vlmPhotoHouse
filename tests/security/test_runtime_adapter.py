"""Explicit adapter exercised only with temporary synthetic files and real ASGI."""
from contextlib import closing
import importlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import test_library_reads as library_fixture
from app.access.runtime import ExistingDatabase, RuntimeConfiguration, RuntimeUnavailable, REQUIRED_REVISION
from app.main import create_app
from fastapi.testclient import TestClient
from alembic.script import ScriptDirectory
from test_orm_migrations import config
from test_access_foundation import MEMBER, PASSWORD, NOW


class RuntimeAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library_fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        library_fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        directory=tempfile.TemporaryDirectory(prefix='photohouse-runtime-adapter-')
        self.addCleanup(directory.cleanup)
        self.root=Path(directory.name).resolve()
        self.path=self.root/'synthetic # database.sqlite'
        with closing(sqlite3.connect(self.path)) as db:
            library_fixture.LibraryReadTests.template.backup(db)
        self.originals,self.derived=self.root/'originals',self.root/'derived'
        self.originals.mkdir();self.derived.mkdir()
        self.settings=RuntimeConfiguration(self.path,'https://photohouse.test',(self.originals,),self.derived)
        self.app=self.settings.build_app(clock=lambda:NOW)
        self.client=TestClient(self.app,base_url='https://photohouse.test',client=('192.0.2.40',23456))
        self.addCleanup(self.client.close)
        for target in ('socket.socket.connect','socket.socket.bind','subprocess.Popen','os.system'):
            guard=patch(target,side_effect=AssertionError('External I/O forbidden'))
            guard.start();self.addCleanup(guard.stop)

    def headers(self):
        return {'Authorization':'Bearer '+library_fixture.LibraryReadTests.member_token}

    def mutate(self,sql,args=()):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(sql,args);db.commit()

    def test_real_adapter_login_and_scoped_reads_use_existing_migrated_database(self):
        response=self.client.post('/auth/login',json={'phone':MEMBER,'password':PASSWORD,'transport':'native'})
        self.assertEqual(response.status_code,200)
        headers={'Authorization':'Bearer '+response.json()['access_token']}
        response=self.client.get('/assets?library=family-a',headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['total'],2)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertNotIn(str(self.path),response.text)

    def test_import_and_construction_open_no_storage_or_runtime_configuration(self):
        with patch('sqlite3.connect',side_effect=AssertionError('Connection during build')), \
             patch('pathlib.Path.lstat',side_effect=AssertionError('Filesystem during build')), \
             patch.dict('os.environ',{'DATABASE_URL':'sqlite:///must-never-be-opened.sqlite'}):
            import app.access.runtime as runtime
            importlib.reload(runtime)
            self.settings.build_app()
            self.assertIsNone(create_app().state.access_runtime)

    def test_missing_database_never_creates_file_or_schema(self):
        self.path.unlink()
        response=self.client.get('/assets?library=family-a',headers=self.headers())
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json(),{'detail':'Access unavailable'})
        self.assertFalse(self.path.exists())
        self.assertEqual(self.client.get('/ui').status_code,200)

    def test_old_or_multiple_revision_and_missing_access_table_fail_closed(self):
        self.mutate("UPDATE alembic_version SET version_num='f4c1a8d2e703'")
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        self.mutate('UPDATE alembic_version SET version_num=?',(REQUIRED_REVISION,))
        self.mutate("INSERT INTO alembic_version VALUES ('synthetic-other-head')")
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        self.mutate("DELETE FROM alembic_version WHERE version_num='synthetic-other-head'")
        self.mutate('DROP TABLE access_audit')
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertNotIn('access_audit',{r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")})

    def test_invalid_admission_key_is_not_regenerated(self):
        self.mutate('DELETE FROM access_admission_key')
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_admission_key').fetchone()[0],0)

    def test_wrong_type_admission_key_is_refused_without_rotation(self):
        self.mutate('UPDATE access_admission_key SET secret=?', ('x'*32,))
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT secret FROM access_admission_key').fetchone()[0],'x'*32)

    def test_symlink_directory_and_corrupt_database_are_refused_without_disclosure(self):
        moved=self.root/'actual.sqlite';self.path.rename(moved);self.path.symlink_to(moved)
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        self.path.unlink();self.path.mkdir()
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        self.path.rmdir();self.path.write_bytes(b'synthetic-not-a-database')
        response=self.client.get('/auth/session',headers=self.headers())
        self.assertEqual(response.status_code,503)
        self.assertNotIn('database.sqlite',response.text)
        self.assertEqual(self.path.read_bytes(),b'synthetic-not-a-database')

    def test_connections_are_fresh_enforce_foreign_keys_and_rollback_uncommitted_work(self):
        factory=ExistingDatabase(self.path)
        with factory() as first:
            self.assertEqual(first.execute('PRAGMA foreign_keys').fetchone()[0],1)
            self.assertEqual(first.execute('PRAGMA trusted_schema').fetchone()[0],0)
            first.execute("UPDATE access_libraries SET state='closed'")
        with self.assertRaises(sqlite3.ProgrammingError):first.execute('SELECT 1')
        with factory() as second:
            self.assertIsNot(first,second)
            self.assertEqual(second.execute('SELECT DISTINCT state FROM access_libraries').fetchall(),[('active',)])
            with self.assertRaises(sqlite3.IntegrityError):
                second.execute("INSERT INTO access_asset_libraries VALUES (123456,'family-a')")

    def test_failed_domain_call_closes_and_rolls_back_connection(self):
        factory=ExistingDatabase(self.path)
        with self.assertRaisesRegex(RuntimeError,'synthetic'):
            with factory() as db:
                db.execute("UPDATE access_libraries SET state='closed'")
                raise RuntimeError('synthetic')
        with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
        self.assertEqual(self.client.get('/assets?library=family-a',headers=self.headers()).status_code,200)

    def test_adapter_revision_pin_matches_actual_migration_head(self):
        self.assertEqual(ScriptDirectory.from_config(config()).get_heads(),[REQUIRED_REVISION])
        for invalid in (Path('relative.sqlite'),':memory:'):
            with self.assertRaises(ValueError):ExistingDatabase(invalid)
        for timeout in (0,-1,11,float('nan'),True):
            with self.assertRaises(ValueError):ExistingDatabase(self.path,timeout=timeout)

    def test_http_and_host_headers_cannot_supply_configuration_or_proxy_trust(self):
        with TestClient(self.app,base_url='http://photohouse.test') as client:
            response=client.get('/assets?library=family-a',headers={**self.headers(),'X-Forwarded-Proto':'https'})
            self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get('/assets?library=family-a',headers={**self.headers(),'Host':'evil.test'}).status_code,400)


if __name__=='__main__':unittest.main()
