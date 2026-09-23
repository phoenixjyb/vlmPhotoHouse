"""Synthetic regression coverage for the explicit management ownership migration."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

PRE_MANAGEMENT = 'c7f4a9e2b610'
# The upgrade test below targets head, so this tracks the current head rather than the revision
# that any single migration produced.
CURRENT_HEAD = 'a8d4c2e6f901'
OWNERSHIP_TABLES = {'access_person_libraries', 'access_album_libraries'}


def migration_config():
    config = Config()
    config.set_main_option('script_location', str(ROOT / 'backend/migrations'))
    return config


class ManagementMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-management-migration-')
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

    def reset_database(self):
        self.engine.dispose()
        if self.path.exists():
            self.path.unlink()
        self.engine = create_engine('sqlite:///' + str(self.path))
        self.addCleanup(self.engine.dispose)

    def seed_c7_records(self):
        self.upgrade(PRE_MANAGEMENT)
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO assets(id,path,hash_sha256,status) VALUES "
                "(101,'synthetic/first.jpg','hash-1','active'),"
                "(102,'synthetic/second.jpg','hash-2',NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO persons(id,display_name,face_count) VALUES "
                "(7,'Grandma',2),(8,'Child',1)"
            )
            connection.exec_driver_sql(
                "INSERT INTO albums(id,title,title_zh,theme,status,cover_asset_id) VALUES "
                "(11,'Summer','夏天','custom','published',101)"
            )
            connection.exec_driver_sql(
                "INSERT INTO album_assets(id,album_id,asset_id,position) VALUES "
                "(21,11,102,2),(22,11,101,1)"
            )
            connection.exec_driver_sql(
                "INSERT INTO access_accounts(id,phone_login,password_hash) VALUES "
                "('owner','+12025550101','synthetic-hash')"
            )
            connection.exec_driver_sql(
                "INSERT INTO access_libraries(id,bootstrap_operator) VALUES "
                "('family-a','owner')"
            )
            connection.exec_driver_sql(
                "INSERT INTO access_stories "
                "(id,asset_id,library_id,author_id,revision,title,text,language,byline,"
                "created_at,updated_at,deleted) VALUES "
                "('story-1',101,'family-a','owner',1,'Old title','Old text','en','Dad',100,100,0)"
            )
            connection.exec_driver_sql(
                "INSERT INTO access_story_revisions "
                "(story_id,revision,editor_id,mutation_id,request_digest,title,text,language,"
                "byline,occurred_at,deleted) VALUES "
                "('story-1',1,'owner','mutation-1','digest-1','Old title','Old text','en','Dad',100,0)"
            )

    def legacy_snapshot(self, connection):
        tables = ('assets', 'persons', 'albums', 'album_assets', 'access_stories',
                  'access_story_revisions')
        return {table: connection.exec_driver_sql(
            'SELECT * FROM ' + table + ' ORDER BY rowid').all() for table in tables}

    def test_each_ownership_ddl_failure_rolls_back_without_touching_c7_records(self):
        for failed_table in sorted(OWNERSHIP_TABLES):
            with self.subTest(failed_table=failed_table):
                self.reset_database()
                self.seed_c7_records()
                with self.engine.connect() as connection:
                    before = self.legacy_snapshot(connection)

                def fail(conn, cursor, statement, parameters, context, executemany):
                    if (statement.lstrip().upper().startswith('CREATE TABLE')
                            and failed_table in statement):
                        raise RuntimeError('Synthetic ownership DDL interruption: ' + failed_table)

                event.listen(self.engine, 'before_cursor_execute', fail)
                try:
                    with self.assertRaisesRegex(RuntimeError, failed_table):
                        self.upgrade()
                finally:
                    event.remove(self.engine, 'before_cursor_execute', fail)

                with self.engine.connect() as connection:
                    self.assertEqual(
                        connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(),
                        PRE_MANAGEMENT)
                    self.assertEqual(self.legacy_snapshot(connection), before)
                    self.assertFalse(OWNERSHIP_TABLES & set(inspect(connection).get_table_names()))

                self.upgrade()

    def test_management_upgrade_preserves_c7_rows_and_does_not_guess_ownership(self):
        self.seed_c7_records()
        with self.engine.connect() as connection:
            before = self.legacy_snapshot(connection)

        self.upgrade()

        with self.engine.connect() as connection:
            self.assertEqual(
                connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(),
                CURRENT_HEAD)
            self.assertEqual(self.legacy_snapshot(connection), before)
            for table in OWNERSHIP_TABLES:
                self.assertEqual(connection.exec_driver_sql('SELECT count(*) FROM ' + table).scalar_one(), 0)
            self.assertEqual(
                connection.exec_driver_sql(
                    'SELECT album_id,asset_id,position FROM album_assets ORDER BY album_id,position'
                ).all(), [(11, 101, 1), (11, 102, 2)])


if __name__ == '__main__':
    unittest.main()
