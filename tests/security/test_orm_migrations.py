"""Actual SQLAlchemy/Alembic against temporary synthetic SQLite; no runtime config."""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, event, inspect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.db import Base
from app.access.metadata import migration_metadata

PRE_ACCESS = 'd2b7e4f6a901'
ACCESS_HEAD = 'a5d2e8f4b610'
ACCESS_TABLES = {'access_accounts', 'access_sessions', 'access_operators', 'access_libraries',
    'access_memberships', 'access_invitations', 'access_asset_libraries', 'access_audit',
    'access_admission_key', 'access_attempts', 'access_kdf_slot'}


def config():
    cfg = Config()
    cfg.set_main_option('script_location', str(ROOT / 'backend/migrations'))
    return cfg


class OrmMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-migration-')
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'synthetic.sqlite'
        self.engine = create_engine('sqlite:///' + str(self.path))
        self.addCleanup(self.engine.dispose)
        for target in ('socket.socket.connect', 'socket.socket.bind', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start()
            self.addCleanup(guard.stop)

    def upgrade(self, target='head'):
        with self.engine.begin() as connection:
            cfg = config()
            cfg.attributes['connection'] = connection
            command.upgrade(cfg, target)

    def seed_legacy(self):
        self.upgrade(PRE_ACCESS)
        with self.engine.begin() as connection:
            connection.exec_driver_sql('''INSERT INTO assets(id,path,hash_sha256,status)
                VALUES (101,'synthetic/first.jpg','synthetic-hash','active'),
                       (102,'synthetic/null-status.mp4','synthetic-second',NULL)''')

    def test_actual_revision_chain_and_access_metadata_have_no_autogenerate_drift(self):
        self.seed_legacy()
        self.upgrade()
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(), ACCESS_HEAD)
            self.assertTrue(ACCESS_TABLES <= set(inspect(connection).get_table_names()))
            only_access = lambda obj, name, kind, reflected, compare_to: kind != 'table' or name.startswith('access_')
            context = MigrationContext.configure(connection, opts={'include_object': only_access, 'compare_server_default': True})
            self.assertEqual(compare_metadata(context, migration_metadata(Base.metadata)), [])
            self.assertEqual(connection.exec_driver_sql('SELECT id,path,status FROM assets ORDER BY id').all(),
                [(101, 'synthetic/first.jpg', 'active'), (102, 'synthetic/null-status.mp4', None)])
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])
            for name in ACCESS_TABLES - {'access_admission_key'}:
                self.assertEqual(connection.exec_driver_sql('SELECT count(*) FROM ' + name).scalar_one(), 0)
            self.assertEqual(connection.exec_driver_sql('SELECT length(secret) FROM access_admission_key').scalar_one(), 32)

    def test_metadata_copy_cannot_enable_startup_security_schema_creation(self):
        before = set(Base.metadata.tables)
        combined = migration_metadata(Base.metadata)
        self.assertEqual(set(Base.metadata.tables), before)
        self.assertEqual(set(combined.tables), before | ACCESS_TABLES)
        Base.metadata.create_all(self.engine)
        self.assertEqual(set(inspect(self.engine).get_table_names()), before)
        self.assertFalse(ACCESS_TABLES & set(inspect(self.engine).get_table_names()))

    def test_failed_access_upgrade_rolls_back_ddl_and_revision_ledger_together(self):
        self.seed_legacy()
        def fail(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith('CREATE TABLE access_invitations'):
                raise RuntimeError('Synthetic migration interruption')
        event.listen(self.engine, 'before_cursor_execute', fail)
        try:
            with self.assertRaisesRegex(RuntimeError, 'Synthetic migration interruption'):
                self.upgrade()
        finally:
            event.remove(self.engine, 'before_cursor_execute', fail)
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(), PRE_ACCESS)
            self.assertFalse(ACCESS_TABLES & set(inspect(connection).get_table_names()))
            self.assertEqual(connection.exec_driver_sql('SELECT count(*) FROM assets').scalar_one(), 2)
        self.upgrade()

    def test_failed_fresh_upgrade_leaves_no_partial_schema_or_version(self):
        def fail(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith('CREATE TABLE access_attempts'):
                raise RuntimeError('Synthetic admission interruption')
        event.listen(self.engine, 'before_cursor_execute', fail)
        try:
            with self.assertRaisesRegex(RuntimeError, 'Synthetic admission interruption'):
                self.upgrade()
        finally:
            event.remove(self.engine, 'before_cursor_execute', fail)
        self.assertEqual(inspect(self.engine).get_table_names(), [])

    def test_caller_owns_commit_and_environment_cannot_redirect_supplied_connection(self):
        with self.engine.connect() as connection:
            transaction = connection.begin()
            cfg = config()
            cfg.attributes['connection'] = connection
            with patch.dict(os.environ, {'DATABASE_URL': 'sqlite:////forbidden-real-database.sqlite'}):
                command.upgrade(cfg, 'head')
            self.assertTrue(transaction.is_active)
            self.assertEqual(connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(), ACCESS_HEAD)
            transaction.rollback()
        self.assertEqual(inspect(self.engine).get_table_names(), [])

    def test_explicit_url_runner_commits_without_injected_connection(self):
        cfg = config()
        cfg.set_main_option('sqlalchemy.url', 'sqlite:///' + str(self.path))
        with patch.dict(os.environ, {'DATABASE_URL': ''}):
            command.upgrade(cfg, 'head')
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(), ACCESS_HEAD)

    def test_missing_target_and_offline_mode_refuse_before_any_database_open(self):
        with patch.dict(os.environ, {'DATABASE_URL': ''}), \
             patch('sqlalchemy.engine_from_config', side_effect=AssertionError('Implicit database target')):
            with self.assertRaisesRegex(RuntimeError, 'Explicit migration database'):
                command.upgrade(config(), 'head')
        cfg = config()
        cfg.set_main_option('sqlalchemy.url', 'sqlite:///' + str(self.path))
        with patch.dict(os.environ, {'DATABASE_URL': ''}):
            with self.assertRaisesRegex(RuntimeError, 'Offline SQL generation is unsupported'):
                command.upgrade(cfg, 'head', sql=True)
        self.assertFalse(self.path.exists())

    def test_downgrade_refuses_and_offline_backup_restore_is_synthetic(self):
        self.seed_legacy()
        backup = self.path.with_name('synthetic-backup.sqlite')
        source, destination = sqlite3.connect(self.path), sqlite3.connect(backup)
        try:
            source.backup(destination)
        finally:
            source.close(); destination.close()
        self.upgrade()
        with self.assertRaisesRegex(RuntimeError, 'reviewed offline backup restoration'):
            with self.engine.begin() as connection:
                cfg = config(); cfg.attributes['connection'] = connection
                command.downgrade(cfg, PRE_ACCESS)
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(), ACCESS_HEAD)
        # Rehearse restoring into another temporary offline file, never overwrite
        # an active database or automatically re-enable an older HTTP server.
        restored = self.path.with_name('synthetic-restored.sqlite')
        source, destination = sqlite3.connect(backup), sqlite3.connect(restored)
        try:
            source.backup(destination)
            self.assertEqual(destination.execute('SELECT version_num FROM alembic_version').fetchone()[0], PRE_ACCESS)
            self.assertEqual(destination.execute('SELECT id,path FROM assets ORDER BY id').fetchall(),
                [(101, 'synthetic/first.jpg'), (102, 'synthetic/null-status.mp4')])
        finally:
            source.close(); destination.close()

    def test_foreign_key_and_membership_constraints_are_enforced_by_real_migration(self):
        self.upgrade()
        from sqlalchemy.exc import IntegrityError
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_keys').scalar_one(), 1)
            for sql in ("INSERT INTO access_asset_libraries VALUES (101,'unassigned')",
                        "INSERT INTO access_accounts VALUES ('synthetic','+12025550199','synthetic','unknown')",
                        'INSERT INTO access_kdf_slot VALUES (2,\'synthetic\')'):
                with self.assertRaises(IntegrityError):
                    connection.exec_driver_sql(sql)
                connection.rollback()

    def test_legacy_schema_drift_is_reported_separately_from_access_parity(self):
        # Preserve the finding at the old head; the new additive revision repairs it.
        self.upgrade('f4c1a8d2e703')
        missing = set(Base.metadata.tables) - set(inspect(self.engine).get_table_names())
        self.assertEqual(missing, {'tags', 'asset_tags', 'asset_tag_blocks', 'video_segments'})
        columns = {c['name'] for c in inspect(self.engine).get_columns('assets')}
        self.assertFalse({'duration_sec', 'fps'} & columns)


if __name__ == '__main__':
    unittest.main()
