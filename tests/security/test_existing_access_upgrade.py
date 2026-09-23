"""Offline existing-account upgrades on synthetic catalogs only."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import apply_access_schema as migration


class ExistingAccessUpgradeTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine
        from alembic import command
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.db, self.backup = self.root / 'catalog.sqlite', self.root / 'backup.sqlite'
        engine = create_engine('sqlite:///' + str(self.db))
        try:
            with engine.connect() as connection:
                config = migration.full.small.migration_config()
                config.attributes['connection'] = connection
                command.upgrade(config, migration.EXISTING_ACCESS_REVISION)
        finally:
            engine.dispose()
        with closing(sqlite3.connect(self.db)) as db:
            # Reproduce the actual previous schema, before display_name existed.
            db.execute('ALTER TABLE access_accounts DROP COLUMN display_name')
            db.execute("INSERT INTO assets(id,path,hash_sha256) VALUES(1,'synthetic.jpg','hash')")
            db.execute("INSERT INTO access_accounts VALUES('owner','+12025550199','synthetic','active')")
            db.execute("INSERT INTO access_operators VALUES('owner')")
            db.execute("INSERT INTO access_libraries VALUES('family','active','owner')")
            db.execute("INSERT INTO access_memberships VALUES('owner','family','approved','owner',2,NULL,1,'owner')")
            db.execute("INSERT INTO access_sessions VALUES('synthetic-session','owner',9999999999,0)")
            db.execute("INSERT INTO access_asset_libraries VALUES(1,'family')")
            db.commit()
        self.digest = migration.full.snapshot(self.db, self.backup, self.budget())['snapshot_digest']

    def budget(self):
        return migration.full.Budget(128 * 1024**2, 120)

    def apply(self, **kwargs):
        return migration.apply(self.db, self.backup, self.digest, self.budget(),
                               from_revision=migration.EXISTING_ACCESS_REVISION, **kwargs)

    def test_review_is_read_only_and_legacy_default_refuses_existing_accounts(self):
        before = self.db.read_bytes(), self.backup.read_bytes()
        self.assertFalse(self.apply()['applied'])
        with self.assertRaises(migration.full.small.Refused):
            migration.apply(self.db, self.backup, self.digest, self.budget())
        self.assertEqual(before, (self.db.read_bytes(), self.backup.read_bytes()))

    def test_upgrade_preserves_credentials_sessions_grants_and_old_columns(self):
        backup_bytes = self.backup.read_bytes()
        with patch.dict('os.environ', {'DATABASE_URL': 'sqlite:////never-open.sqlite'}):
            self.assertTrue(self.apply(execute=True, all_writers_stopped=True)['applied'])
        with closing(sqlite3.connect(self.db)) as db, closing(sqlite3.connect(self.backup)) as saved:
            old_tables = migration.full.schema(saved)
            preserved = {name: cols for name, cols in old_tables.items() if name != 'alembic_version'}
            self.assertEqual(migration.full.fingerprint(db, preserved, self.budget()),
                             migration.full.fingerprint(saved, preserved, self.budget()))
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone(),
                             (migration.TO_REVISION,))
            self.assertEqual(db.execute('SELECT display_name FROM access_accounts').fetchall(), [(None,)])
            self.assertEqual(db.execute('SELECT count(*) FROM access_uploads').fetchone(), (0,))
            self.assertEqual(db.execute('SELECT count(*) FROM access_upload_transfers').fetchone(), (0,))
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.backup.read_bytes(), backup_bytes)

    def test_wrong_revision_stale_backup_and_missing_shutdown_refuse(self):
        with self.assertRaises(migration.full.small.Refused):
            self.apply(execute=True)
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE access_sessions SET revoked=1")
            db.commit()
        with self.assertRaises(migration.full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)

    def test_account_change_during_migration_rolls_back_everything(self):
        from alembic import command
        original = command.upgrade
        def corrupt(config, target):
            original(config, target)
            config.attributes['connection'].exec_driver_sql("UPDATE access_accounts SET state='disabled'")
        with patch.object(command, 'upgrade', side_effect=corrupt):
            with self.assertRaises(migration.full.small.Refused):
                self.apply(execute=True, all_writers_stopped=True)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT state FROM access_accounts').fetchone(), ('active',))
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone(),
                             (migration.EXISTING_ACCESS_REVISION,))
            self.assertNotIn('access_uploads', migration.full.schema(db))
            self.assertNotIn('display_name', migration.full.schema(db)['access_accounts'])

    def test_repeat_application_refuses(self):
        self.apply(execute=True, all_writers_stopped=True)
        with self.assertRaises(migration.full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)

    def test_current_upload_revision_preserves_existing_receipts_and_memberships(self):
        from sqlalchemy import create_engine
        from alembic import command
        engine = create_engine('sqlite:///' + str(self.db))
        try:
            with engine.begin() as connection:
                config = migration.full.small.migration_config()
                config.attributes['connection'] = connection
                command.upgrade(config, migration.EXISTING_UPLOAD_REVISION)
        finally:
            engine.dispose()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('''INSERT INTO access_uploads(asset_id,account_id,incoming_label,batch,
                original_name,sha256,bytes,state,created_at) VALUES(?,?,?,?,?,?,?,?,?)''',
                (1, 'owner', 'synthetic-owner', '1' * 32, 'synthetic.jpg', '2' * 64,
                 1234, 'assigned', 1770000000))
            db.commit()
            previous = db.execute('SELECT * FROM access_uploads').fetchall()
            membership = db.execute('SELECT * FROM access_memberships').fetchall()
        self.backup = self.root / 'upload-backup.sqlite'
        self.digest = migration.full.snapshot(self.db, self.backup, self.budget())['snapshot_digest']
        result = migration.apply(self.db, self.backup, self.digest, self.budget(),
            from_revision=migration.EXISTING_UPLOAD_REVISION, execute=True, all_writers_stopped=True)
        self.assertTrue(result['applied'])
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT * FROM access_uploads').fetchall(), previous)
            self.assertEqual(db.execute('SELECT * FROM access_memberships').fetchall(), membership)
            self.assertEqual(db.execute('SELECT count(*) FROM access_upload_transfers').fetchone(), (0,))
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone(),
                             (migration.TO_REVISION,))

    def test_cli_selects_existing_account_upgrade_explicitly(self):
        from contextlib import redirect_stdout
        import io
        import json
        output = io.StringIO()
        with redirect_stdout(output):
            result = migration.main(['--database', str(self.db), '--backup', str(self.backup),
                '--reviewed-backup-digest', self.digest, '--max-bytes', str(128 * 1024**2),
                '--timeout-seconds', '120', '--from-revision', migration.EXISTING_ACCESS_REVISION])
        self.assertEqual(result, 0)
        receipt = json.loads(output.getvalue())
        self.assertFalse(receipt['applied'])
        self.assertEqual(receipt['source_revision'], migration.EXISTING_ACCESS_REVISION)

    def test_running_task_is_refused_even_after_matching_backup(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO tasks(type,state,priority,payload_json) VALUES('caption','running',0,'{}')")
            db.commit()
        next_backup = self.root / 'running-backup.sqlite'
        self.digest = migration.full.snapshot(self.db, next_backup, self.budget())['snapshot_digest']
        self.backup = next_backup
        with self.assertRaises(migration.full.small.Refused):
            self.apply(execute=True, all_writers_stopped=True)
