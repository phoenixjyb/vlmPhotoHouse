"""Synthetic regression coverage for the explicit member-upload migration.

The migration is additive and must not invalidate an existing account: `display_name` is
nullable precisely because accounts created earlier have no name, and the deployed owner is one
of them. The provenance table must also refuse a state or byte count it does not understand,
since it is the only record that a photo was added and by whom.
"""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

PRE_UPLOAD = 'd8e5b2f7a904'
UPLOAD_HEAD = 'f2a6d8b4c915'


def migration_config():
    config = Config()
    config.set_main_option('script_location', str(ROOT / 'backend/migrations'))
    return config


class UploadMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-upload-migration-')
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
            config = migration_config()
            config.attributes['connection'] = connection
            command.upgrade(config, target)

    def rows(self, sql, args=()):
        with self.engine.begin() as connection:
            return connection.exec_driver_sql(sql, args).fetchall()

    def test_chain_has_exactly_one_head_and_it_is_this_revision(self):
        heads = ScriptDirectory.from_config(migration_config()).get_heads()
        self.assertEqual(heads, [UPLOAD_HEAD])

    def test_existing_account_survives_with_a_null_display_name(self):
        self.upgrade(PRE_UPLOAD)
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO access_accounts(id,phone_login,password_hash,state) "
                "VALUES('00000000-0000-4000-8000-000000000001','+12025550199','synthetic','active')")
        self.upgrade()
        rows = self.rows('SELECT id,display_name FROM access_accounts')
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0][1], 'an existing account must not be given a name it did not choose')

    def test_database_that_predates_the_revision_gains_the_column(self):
        """The deployed database predates this revision, so it needs the real ADD COLUMN.

        A database built from migrations already carries the column, because the foundation
        migration composes `access/schema.py`. Dropping it here reproduces the older shape and
        proves the conditional branch does the work rather than being dead code.
        """
        self.upgrade(PRE_UPLOAD)
        with self.engine.begin() as connection:
            present = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(access_accounts)')}
            if 'display_name' in present:
                connection.exec_driver_sql('ALTER TABLE access_accounts DROP COLUMN display_name')
            connection.exec_driver_sql(
                "INSERT INTO access_accounts(id,phone_login,password_hash,state) "
                "VALUES('00000000-0000-4000-8000-000000000001','+12025550199','synthetic','active')")
        self.upgrade()
        self.assertEqual(self.rows('SELECT display_name FROM access_accounts'), [(None,)])

    def test_provenance_table_shape(self):
        self.upgrade()
        columns = {row[1] for row in self.rows('PRAGMA table_info(access_uploads)')}
        self.assertEqual(columns, {'id', 'asset_id', 'account_id', 'incoming_label', 'batch',
                                   'original_name', 'sha256', 'bytes', 'state', 'created_at'})
        indexes = {row[1] for row in self.rows('PRAGMA index_list(access_uploads)')}
        self.assertIn('ix_access_uploads_account', indexes)
        self.assertIn('ix_access_uploads_state', indexes)

    def test_provenance_refuses_an_unknown_state_and_negative_bytes(self):
        self.upgrade()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO assets(id,path,hash_sha256) VALUES(1,'synthetic/a.jpg','h')")
            connection.exec_driver_sql(
                "INSERT INTO access_accounts(id,phone_login,password_hash,state) "
                "VALUES('00000000-0000-4000-8000-000000000001','+12025550199','synthetic','active')")
            connection.exec_driver_sql(
                "INSERT INTO access_uploads(id,asset_id,account_id,incoming_label,batch,original_name,"
                "sha256,bytes,state,created_at) VALUES(1,1,'00000000-0000-4000-8000-000000000001',"
                "'label','batch','a.jpg','h',10,'incoming',1)")
        for bad in ("UPDATE access_uploads SET state='promoted'",
                    "UPDATE access_uploads SET bytes=-1"):
            with self.assertRaises(Exception):
                with self.engine.begin() as connection:
                    connection.exec_driver_sql(bad)

    def test_one_provenance_row_per_asset(self):
        self.upgrade()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO assets(id,path,hash_sha256) VALUES(1,'synthetic/a.jpg','h')")
            connection.exec_driver_sql(
                "INSERT INTO access_accounts(id,phone_login,password_hash,state) "
                "VALUES('00000000-0000-4000-8000-000000000001','+12025550199','synthetic','active')")
            connection.exec_driver_sql(
                "INSERT INTO access_uploads(id,asset_id,account_id,incoming_label,batch,original_name,"
                "sha256,bytes,state,created_at) VALUES(1,1,'00000000-0000-4000-8000-000000000001',"
                "'label','batch','a.jpg','h',10,'incoming',1)")
        with self.assertRaises(Exception):
            with self.engine.begin() as connection:
                connection.exec_driver_sql(
                    "INSERT INTO access_uploads(id,asset_id,account_id,incoming_label,batch,original_name,"
                    "sha256,bytes,state,created_at) VALUES(2,1,'00000000-0000-4000-8000-000000000001',"
                    "'label','batch','a.jpg','h',10,'incoming',1)")

    def test_downgrade_refuses_rather_than_guessing(self):
        self.upgrade()
        with self.assertRaises(RuntimeError):
            with self.engine.begin() as connection:
                config = migration_config()
                config.attributes['connection'] = connection
                command.downgrade(config, PRE_UPLOAD)

    def test_upload_table_is_not_reachable_without_the_access_layer(self):
        """The provenance row records no library, so nothing here can widen visibility."""
        self.upgrade()
        columns = {row[1] for row in self.rows('PRAGMA table_info(access_uploads)')}
        self.assertNotIn('library_id', columns)
