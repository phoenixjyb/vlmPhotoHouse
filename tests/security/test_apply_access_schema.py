"""Offline application on disposable synthetic catalogs, never runtime files."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import apply_access_schema as migration
full = migration.full


class MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqlalchemy import create_engine
        from alembic import command
        cls.template = sqlite3.connect(':memory:')
        engine = create_engine('sqlite://')
        with engine.connect() as connection:
            config = full.small.migration_config(); config.attributes['connection'] = connection
            command.upgrade(config, migration.FROM_REVISION)
            connection.connection.driver_connection.backup(cls.template)
        engine.dispose()

    @classmethod
    def tearDownClass(cls):
        cls.template.close()

    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.db, self.backup = self.root/'catalog.sqlite', self.root/'backup.sqlite'
        with closing(sqlite3.connect(self.db)) as db:
            self.template.backup(db)
            db.execute("INSERT INTO assets(id,path,hash_sha256,status) VALUES(1,'synthetic.jpg','synthetic-hash','active')")
            db.commit()
        self.digest = full.snapshot(self.db, self.backup, self.budget())['snapshot_digest']

    def budget(self):
        return full.Budget(128*1024**2, 120)

    def apply(self, **options):
        return migration.apply(self.db, self.backup, self.digest, self.budget(), **options)

    def test_review_does_not_modify_files(self):
        before = self.db.read_bytes(), self.backup.read_bytes()
        self.assertFalse(self.apply()['applied'])
        self.assertEqual(before, (self.db.read_bytes(), self.backup.read_bytes()))

    def test_apply_preserves_rows_and_creates_no_owner(self):
        saved = self.backup.read_bytes()
        with patch.dict('os.environ', {'DATABASE_URL':'sqlite:////never-use-this.sqlite'}):
            self.assertTrue(self.apply(execute=True, all_writers_stopped=True)['applied'])
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('select version_num from alembic_version').fetchone()[0], migration.TO_REVISION)
            self.assertEqual(db.execute('select path from assets').fetchone()[0], 'synthetic.jpg')
            self.assertEqual(db.execute('select count(*) from access_accounts').fetchone()[0], 0)
            self.assertEqual(db.execute('pragma foreign_key_check').fetchall(), [])
        self.assertEqual(saved, self.backup.read_bytes())

    def test_execution_needs_shutdown_assertion(self):
        with self.assertRaises(full.small.Refused): self.apply(execute=True)

    def test_stale_source_and_backup_refused(self):
        for path in (self.db, self.backup):
            with self.subTest(path=path):
                with closing(sqlite3.connect(path)) as db:
                    db.execute("update assets set path='changed.jpg'"); db.commit()
                with self.assertRaises(full.small.Refused): self.apply(execute=True, all_writers_stopped=True)
                with closing(sqlite3.connect(path)) as db:
                    db.execute("update assets set path='synthetic.jpg'"); db.commit()

    def test_wal_refused(self):
        with closing(sqlite3.connect(self.db)) as db: db.execute('pragma journal_mode=WAL')
        with self.assertRaises(full.small.Refused): self.apply(execute=True, all_writers_stopped=True)

    def test_same_backup_refused(self):
        with self.assertRaises(full.small.Refused):
            migration.apply(self.db,self.db,self.digest,self.budget(),execute=True,all_writers_stopped=True)

    def test_ddl_failure_rolls_back_revision_and_rows(self):
        from alembic import command
        original = command.upgrade
        def fail(config, target):
            original(config, target)
            config.attributes['connection'].exec_driver_sql("UPDATE assets SET path='must-rollback'")
            raise RuntimeError('synthetic fault after DDL')
        with patch.object(command, 'upgrade', side_effect=fail):
            with self.assertRaises(RuntimeError): self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('select version_num from alembic_version').fetchone()[0],migration.FROM_REVISION)
            self.assertEqual(db.execute('select path from assets').fetchone()[0],'synthetic.jpg')
            self.assertEqual(db.execute("select count(*) from sqlite_master where name='access_accounts'").fetchone()[0],0)

    def test_exclusive_lock_rejects_competing_writer(self):
        from alembic import command
        original = command.upgrade
        def check(config, target):
            with closing(sqlite3.connect(self.db,timeout=0)) as other:
                with self.assertRaises(sqlite3.OperationalError): other.execute("UPDATE assets SET path='race'")
            original(config,target)
        with patch.object(command, 'upgrade', side_effect=check):
            self.assertTrue(self.apply(execute=True,all_writers_stopped=True)['applied'])

    def test_preservation_failure_rolls_back(self):
        from alembic import command
        original = command.upgrade
        def change(config, target):
            original(config,target)
            config.attributes['connection'].exec_driver_sql("UPDATE assets SET path='corrupt'")
        with patch.object(command,'upgrade',side_effect=change):
            with self.assertRaises(full.small.Refused): self.apply(execute=True,all_writers_stopped=True)
        self.assertFalse(self.apply()['applied'])

    def test_repeat_application_refused(self):
        self.apply(execute=True,all_writers_stopped=True)
        with self.assertRaises(full.small.Refused): self.apply(execute=True,all_writers_stopped=True)

    def test_running_task_refused_even_with_shutdown_assertion(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO tasks(type,state,priority,payload_json) VALUES('caption','running',0,'{}')")
            db.commit()
        with self.assertRaises(full.small.Refused): self.apply(execute=True,all_writers_stopped=True)

    def test_change_between_review_and_lock_refused(self):
        original = migration.review
        def changed(*args):
            result = original(*args)
            with closing(sqlite3.connect(self.db)) as db:
                db.execute("UPDATE assets SET path='concurrent.jpg'"); db.commit()
            return result
        with patch.object(migration,'review',side_effect=changed):
            with self.assertRaises(full.small.Refused): self.apply(execute=True,all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('select version_num from alembic_version').fetchone()[0],migration.FROM_REVISION)
            self.assertEqual(db.execute('select path from assets').fetchone()[0],'concurrent.jpg')

    def test_timeout_after_ddl_rolls_back(self):
        from alembic import command
        original = command.upgrade
        budget = self.budget()
        def expire(config,target):
            original(config,target)
            budget.deadline = 0
        with patch.object(command,'upgrade',side_effect=expire):
            with self.assertRaises(full.small.Refused):
                migration.apply(self.db,self.backup,self.digest,budget,execute=True,all_writers_stopped=True)
        self.assertFalse(self.apply()['applied'])

    def test_cli_review_and_sanitized_refusal(self):
        from contextlib import redirect_stdout, redirect_stderr
        import io,json
        args=['--database',str(self.db),'--backup',str(self.backup),'--reviewed-backup-digest',self.digest,
              '--max-bytes',str(128*1024**2),'--timeout-seconds','120']
        out,err=io.StringIO(),io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):self.assertEqual(migration.main(args),0)
        self.assertFalse(json.loads(out.getvalue())['applied'])
        out,err=io.StringIO(),io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):
            self.assertEqual(migration.main(args+['--accidental-secret','must-not-echo']),2)
        self.assertNotIn('must-not-echo',out.getvalue()+err.getvalue())


if __name__ == '__main__': unittest.main()
