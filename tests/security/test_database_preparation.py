"""Offline preparation with disposable databases and external I/O denied."""
from contextlib import closing, redirect_stdout, redirect_stderr
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
from app.access.runtime import ExistingDatabase, REQUIRED_REVISION


class DatabasePreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = sqlite3.connect(':memory:')
        cli.configure(cls.template)
        cli.upgrade_memory(cls.template)

    @classmethod
    def tearDownClass(cls):
        cls.template.close()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-prepare-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.source = self.root / 'synthetic.sqlite'
        self.output = self.root / 'new.sqlite'
        with closing(sqlite3.connect(self.source)) as db:
            self.template.backup(db)
            db.execute("INSERT INTO assets(id,path,hash_sha256,status) VALUES (101,'private-synthetic.jpg','private-hash','active')")
            db.commit()
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def call(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = cli.main(list(map(str, args)))
        text = stdout.getvalue() + stderr.getvalue()
        for private in (str(self.root), 'private-synthetic', 'private-hash'):
            self.assertNotIn(private, text)
        return status, json.loads(stdout.getvalue()) if stdout.getvalue() else None

    def backup(self):
        return self.call('backup', '--database', self.source, '--out', self.output)

    def test_initialize_is_private_empty_and_has_no_access_grants(self):
        code, result = self.call('initialize', '--out', self.output)
        self.assertEqual(code, 0)
        self.assertEqual(result['revision'], REQUIRED_REVISION)
        self.assertTrue(result['restore_verified_in_memory'])
        with ExistingDatabase(self.output, read_only=True)() as db:
            for table in ('assets', 'access_accounts', 'access_sessions', 'access_libraries',
                          'access_memberships', 'access_asset_libraries', 'access_provisioning_receipts'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0], 0)
        if os.name != 'nt':
            self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_backup_preserves_source_bytes_and_logical_content_and_restores_in_memory(self):
        before = self.source.read_bytes()
        code, result = self.backup()
        self.assertEqual(code, 0)
        self.assertTrue(result['restore_verified_in_memory'])
        self.assertEqual(result['source_snapshot_digest'], result['snapshot_digest'])
        self.assertEqual(self.source.read_bytes(), before)
        with ExistingDatabase(self.output, read_only=True)() as db:
            self.assertEqual(db.execute('SELECT path FROM assets').fetchall(), [('private-synthetic.jpg',)])
            self.assertEqual(db.execute('SELECT secret FROM access_admission_key').fetchall(),
                             self.template.execute('SELECT secret FROM access_admission_key').fetchall())

    def test_existing_outputs_source_alias_and_symlinks_never_overwritten(self):
        before = self.source.read_bytes()
        self.output = self.source
        self.assertEqual(self.backup()[0], 2)
        alias = self.root / 'alias.sqlite'; alias.symlink_to(self.source)
        self.output = alias
        self.assertEqual(self.backup()[0], 2)
        self.assertEqual(self.call('initialize', '--out', self.source)[0], 2)
        self.assertEqual(self.call('rehearse-migration', '--database', alias)[0], 2)
        self.assertEqual(self.source.read_bytes(), before)

    def test_missing_relative_indirect_and_sidecar_paths_refuse_without_creation(self):
        missing = self.root / 'missing.sqlite'
        self.assertEqual(self.call('backup', '--database', missing, '--out', self.output)[0], 2)
        self.assertFalse(missing.exists() or self.output.exists())
        self.assertEqual(self.call('initialize', '--out', 'relative.sqlite')[0], 2)
        alias = self.root / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(self.call('initialize', '--out', alias / 'new.sqlite')[0], 2)
        sidecar = Path(str(self.output) + '-journal'); sidecar.write_bytes(b'private-synthetic')
        self.assertEqual(self.call('initialize', '--out', self.output)[0], 2)
        self.assertEqual(sidecar.read_bytes(), b'private-synthetic')
        self.assertFalse(self.output.exists())

    def test_wal_and_active_journals_refused_without_checkpointing(self):
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('UPDATE assets SET width=42'); db.commit()
            before = {p.name: p.read_bytes() for p in self.root.iterdir()}
            self.assertEqual(self.backup()[0], 2)
            self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)
        self.assertFalse(self.output.exists())

    def test_unknown_revision_and_corruption_refuse_without_output(self):
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("UPDATE alembic_version SET version_num='unknown-private-hash'"); db.commit()
        before = self.source.read_bytes()
        self.assertEqual(self.backup()[0], 2)
        self.assertEqual(self.source.read_bytes(), before)
        self.source.write_bytes(b'not-a-database private-synthetic')
        self.assertEqual(self.backup()[0], 2)
        self.assertFalse(self.output.exists())

    def test_foreign_key_violations_and_size_budget_refuse(self):
        with patch.object(cli, 'MAX_DATABASE_BYTES', 1):
            self.assertEqual(self.backup()[0], 2)
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("INSERT INTO access_asset_libraries VALUES (101,'missing-library')"); db.commit()
        self.assertEqual(self.backup()[0], 2)
        self.assertFalse(self.output.exists())

    def test_environment_cannot_redirect_initialization_or_rehearsal(self):
        forbidden = self.root / 'forbidden.sqlite'
        with patch.dict(os.environ, {'DATABASE_URL': 'sqlite:///'+str(forbidden)}):
            self.assertEqual(self.call('initialize', '--out', self.output)[0], 0)
            self.assertEqual(self.call('rehearse-migration', '--database', self.source)[0], 0)
        self.assertFalse(forbidden.exists())

    def test_pre_access_rehearsal_preserves_original_and_migrates_only_copy(self):
        from alembic import command
        from sqlalchemy import create_engine
        legacy = self.root / 'legacy.sqlite'
        engine = create_engine('sqlite:///'+str(legacy))
        try:
            with engine.connect() as connection:
                config = cli.migration_config(); config.attributes['connection'] = connection
                command.upgrade(config, 'd2b7e4f6a901')
                connection.exec_driver_sql("INSERT INTO assets(id,path,hash_sha256,status) VALUES (7,'private-synthetic','private-hash','active')")
                connection.commit()
        finally:
            engine.dispose()
        before = legacy.read_bytes()
        self.source = legacy
        upgrade = cli.upgrade_memory
        def inspect_copy(db):
            upgrade(db)
            self.assertEqual(db.execute('SELECT id,path FROM assets').fetchall(), [(7, 'private-synthetic')])
            self.assertEqual(db.execute('SELECT count(*) FROM access_memberships').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_asset_libraries').fetchone()[0], 0)
        with patch.object(cli, 'upgrade_memory', side_effect=inspect_copy):
            code, result = self.call('rehearse-migration', '--database', legacy)
        self.assertEqual(code, 0)
        self.assertEqual(result['source_revision'], 'd2b7e4f6a901')
        self.assertEqual(result['revision'], REQUIRED_REVISION)
        self.assertFalse(result['migration_applied_to_source'])
        self.assertEqual(legacy.read_bytes(), before)
        self.assertEqual(self.backup()[0], 0)
        with closing(sqlite3.connect(self.output)) as db:
            self.assertEqual(cli.revision(db), 'd2b7e4f6a901')
            self.assertEqual(db.execute('SELECT id FROM assets').fetchall(), [(7,)])

    def test_migration_failure_leaves_no_initialized_file_or_source_changes(self):
        before = self.source.read_bytes()
        with patch('alembic.command.upgrade', side_effect=RuntimeError('private-synthetic')):
            self.assertEqual(self.call('initialize', '--out', self.output)[0], 2)
            self.assertEqual(self.call('rehearse-migration', '--database', self.source)[0], 2)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), before)

    def test_snapshot_or_file_identity_mismatch_refuses_before_backup_output(self):
        real = cli.identity
        calls = 0
        def changed(path):
            nonlocal calls
            calls += 1
            value = real(path)
            return value if calls == 1 else (value[0], value[1]+1)
        with patch.object(cli, 'identity', side_effect=changed):
            self.assertEqual(self.backup()[0], 2)
        self.assertFalse(self.output.exists())
        with patch.object(cli, 'snapshot_digest', side_effect=['a'*64, 'b'*64]):
            self.assertEqual(self.backup()[0], 2)
        self.assertFalse(self.output.exists())

    def test_failed_output_keeps_private_artifact_and_stdout_failure_reports_completion(self):
        real = cli.copy_database
        def fail_output(source, destination):
            if destination.execute('PRAGMA database_list').fetchone()[2]:
                raise sqlite3.OperationalError('private-synthetic')
            return real(source, destination)
        with patch.object(cli, 'copy_database', side_effect=fail_output):
            self.assertEqual(self.backup()[0], 2)
        self.assertTrue(self.output.exists())
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.output = self.root / 'another.sqlite'
        with patch('sys.stdout.write', side_effect=BrokenPipeError), redirect_stderr(io.StringIO()):
            code = cli.main(['backup', '--database', str(self.source), '--out', str(self.output)])
        self.assertEqual(code, 3)
        with ExistingDatabase(self.output, read_only=True)() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM assets').fetchone()[0], 1)

    def test_no_existing_migrate_restore_or_secret_argument_surface(self):
        for arguments in (['migrate', '--database', self.source], ['restore', '--database', self.source],
                          ['initialize', '--out', self.output, '--password', 'private-synthetic'],
                          ['rehearse-migration', '--database', self.source, '--out', self.output]):
            self.assertEqual(self.call(*arguments)[0], 2)
        self.assertFalse(self.output.exists())

    def test_memory_upgrade_rejects_file_connection_and_incomplete_runtime_schema(self):
        before = self.source.read_bytes()
        with closing(sqlite3.connect(self.source)) as db:
            with self.assertRaises(cli.Refused):
                cli.upgrade_memory(db)
        self.assertEqual(self.source.read_bytes(), before)
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('DROP TABLE access_provisioning_receipts'); db.commit()
        self.assertEqual(self.call('rehearse-migration', '--database', self.source)[0], 2)


if __name__ == '__main__':
    unittest.main()
