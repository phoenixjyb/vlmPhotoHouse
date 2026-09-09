"""Additive legacy schema reconciliation with real ORM reads and preserved data."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.db import Asset, AssetTag, Base, Tag, VideoSegment
from app.access.metadata import migration_metadata
from test_orm_migrations import config

PRE_REPAIR = 'f4c1a8d2e703'
HEAD = 'a5d2e8f4b610'


class LegacyReadMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-read-schema-')
        self.addCleanup(directory.cleanup)
        self.engine = create_engine('sqlite:///' + str(Path(directory.name) / 'synthetic.sqlite'))
        self.addCleanup(self.engine.dispose)
        for target in ('socket.socket.connect', 'socket.socket.bind', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def upgrade(self, target='head'):
        with self.engine.begin() as connection:
            cfg = config(); cfg.attributes['connection'] = connection
            command.upgrade(cfg, target)

    def seed(self):
        self.upgrade(PRE_REPAIR)
        with self.engine.begin() as connection:
            connection.exec_driver_sql('''INSERT INTO assets(id,path,hash_sha256,status)
                VALUES (101,'synthetic/original.mp4','synthetic-one',NULL),
                       (102,'synthetic/deleted.jpg','synthetic-two','deleted')''')

    def test_fresh_chain_has_complete_structural_metadata_and_real_orm_asset_reads(self):
        self.seed()
        self.upgrade()
        with self.engine.connect() as connection:
            self.assertEqual(compare_metadata(MigrationContext.configure(connection), migration_metadata(Base.metadata)), [])
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])
        with Session(self.engine) as session:
            assets = session.scalars(select(Asset).order_by(Asset.id)).all()
            self.assertEqual([(a.id, a.path, a.status, a.duration_sec, a.fps) for a in assets],
                [(101, 'synthetic/original.mp4', None, None, None), (102, 'synthetic/deleted.jpg', 'deleted', None, None)])
            self.assertEqual(session.scalars(select(Tag)).all(), [])
            self.assertEqual(session.scalars(select(VideoSegment)).all(), [])
            self.assertEqual(session.scalars(select(AssetTag)).all(), [])

    def test_existing_compatible_startup_tables_and_rows_are_preserved(self):
        self.seed()
        Base.metadata.create_all(self.engine)  # Synthetic reproduction of old fallback.
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO tags(id,name,type) VALUES (1,'synthetic-tag','custom')")
            connection.exec_driver_sql("INSERT INTO asset_tags(id,asset_id,tag_id,source) VALUES (2,101,1,'manual')")
            connection.exec_driver_sql('INSERT INTO asset_tag_blocks(id,asset_id,tag_id) VALUES (3,102,1)')
            connection.exec_driver_sql('INSERT INTO video_segments(id,asset_id,start_sec,end_sec) VALUES (4,101,0,1)')
            connection.exec_driver_sql('CREATE INDEX synthetic_existing_index ON assets(hash_sha256)')
        self.upgrade()
        self.upgrade()  # Already at head: revision runner performs no rewrite.
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql('SELECT id,name FROM tags').all(), [(1, 'synthetic-tag')])
            self.assertEqual(connection.exec_driver_sql('SELECT id,asset_id,tag_id FROM asset_tags').all(), [(2,101,1)])
            self.assertEqual(connection.exec_driver_sql('SELECT id,asset_id,tag_id FROM asset_tag_blocks').all(), [(3,102,1)])
            self.assertEqual(connection.exec_driver_sql('SELECT id,asset_id,start_sec,end_sec FROM video_segments').all(), [(4,101,0,1)])
            self.assertIn('synthetic_existing_index', {i['name'] for i in inspect(connection).get_indexes('assets')})
            self.assertEqual(connection.exec_driver_sql('SELECT count(*) FROM access_asset_libraries').scalar_one(), 0)

    def test_no_asset_table_rebuild_drop_delete_or_security_grant_occurs(self):
        self.seed()
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.strip().upper())
        event.listen(self.engine, 'before_cursor_execute', capture)
        try:
            self.upgrade()
        finally:
            event.remove(self.engine, 'before_cursor_execute', capture)
        self.assertFalse(any(s.startswith(('DROP ', 'DELETE ', 'REPLACE ')) for s in statements))
        self.assertFalse(any('_ALEMBIC_TMP_ASSETS' in s for s in statements))
        self.assertFalse(any(s.startswith('INSERT INTO ACCESS_') or s.startswith('UPDATE ACCESS_') for s in statements))

    def test_incompatible_existing_table_or_index_fails_without_partial_changes(self):
        self.seed()
        with self.engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE tags(id INTEGER PRIMARY KEY, name TEXT)')
        with self.assertRaisesRegex(RuntimeError, 'Existing table requires explicit schema review'):
            self.upgrade()
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(), PRE_REPAIR)
            self.assertNotIn('asset_tags', inspect(connection).get_table_names())
            self.assertNotIn('duration_sec', {c['name'] for c in inspect(connection).get_columns('assets')})

    def test_incompatible_index_is_not_silently_replaced(self):
        self.seed()
        with self.engine.begin() as connection:
            connection.exec_driver_sql('CREATE INDEX ix_assets_taken_at ON assets(path)')
        with self.assertRaisesRegex(RuntimeError, 'Existing index requires explicit schema review'):
            self.upgrade()
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(), PRE_REPAIR)
            self.assertNotIn('tags', inspect(connection).get_table_names())
            self.assertEqual(next(i for i in inspect(connection).get_indexes('assets') if i['name']=='ix_assets_taken_at')['column_names'], ['path'])


if __name__ == '__main__':
    unittest.main()
