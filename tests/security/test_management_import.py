"""Synthetic CLI coverage for explicit offline management ownership import."""
from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / 'scripts'))
import test_library_reads as fixtures
from app.access.runtime import ExistingDatabase
from app.access.service import AccessService
from app.access.people import People
from app.access.albums import Albums
import provision_access as cli
from test_access_foundation import NOW


class ManagementImportCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.LibraryReadTests.tearDownClass()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-management-cli-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.db, self.backup = self.root / 'synthetic.sqlite', self.root / 'backup.sqlite'
        self.request, self.plan = self.root / 'request.json', self.root / 'plan.json'
        with closing(sqlite3.connect(self.db)) as db:
            fixtures.LibraryReadTests.template.backup(db)
            self.owner = db.execute(
                "SELECT account_id FROM access_memberships WHERE library_id='family-a' AND role='owner'"
            ).fetchone()[0]
            db.execute("INSERT INTO persons(id,display_name,face_count) VALUES (1,'Alice',1),(2,'Orphan',0)")
            db.execute("INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id) "
                       "VALUES (900,101,0,0,1,1,1)")
            db.execute("INSERT INTO albums(id,title,theme,status,cover_asset_id) "
                       "VALUES (1,'Family trip','trip','draft',101),(2,'Empty','custom','draft',NULL)")
            db.execute("INSERT INTO album_assets(id,album_id,asset_id,position) VALUES "
                       "(901,1,101,1),(902,1,102,2)")
            db.commit()
        self.now = NOW
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def call(self, command, *args):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = cli.main([command, '--database', str(self.db), *map(str, args)], clock=lambda: self.now)
        text = output.getvalue() + error.getvalue()
        for private in ('private-synthetic', 'private-hash', 'embedding_path', 'face_count',
                        'Alice', 'Orphan', 'Family trip'):
            self.assertNotIn(private, text)
        return code, json.loads(output.getvalue()) if output.getvalue() else None, error.getvalue()

    def request_value(self, **overrides):
        value = {'library_id': 'family-a', 'operator_account_id': self.owner,
                 'person_ids': [1, 2], 'album_ids': [1, 2],
                 'include_orphan_people': True, 'include_empty_albums': True,
                 'quiescence_reference': 'synthetic-stopped'}
        value.update(overrides)
        self.request.write_text(json.dumps(value))
        return value

    def make_plan(self, **overrides):
        self.request_value(**overrides)
        code, result, error = self.call('plan-management', '--request', self.request, '--out', self.plan)
        self.assertEqual((code, error), (0, ''))
        self.plan_digest, self.plan_id = result['plan_digest'], result['plan_id']
        return result

    def copy_backup(self):
        with ExistingDatabase(self.db, read_only=True)() as source, closing(sqlite3.connect(self.backup)) as target:
            source.backup(target)

    def review(self):
        self.copy_backup()
        args = ['--plan', self.plan, '--backup', self.backup,
                '--reviewed-plan-digest', self.plan_digest,
                '--authority-reference', 'synthetic-authority',
                '--restore-reference', 'synthetic-restore']
        code, result, error = self.call('review', *args)
        self.assertEqual((code, error), (0, ''))
        self.review_hash = result['review_digest']
        return args

    def apply(self, args, stopped=True):
        extra = ['--review-digest', self.review_hash]
        if stopped: extra.append('--all-writers-stopped')
        return self.call('apply', *args, *extra)

    def query(self, sql, args=()):
        with ExistingDatabase(self.db, read_only=True)() as db:
            return db.execute(sql, args).fetchall()

    def mutate(self, sql, args=()):
        with ExistingDatabase(self.db)() as db:
            db.execute(sql, args); db.commit()

    def test_plan_validate_review_are_read_only_and_seal_effects(self):
        before = self.db.read_bytes()
        result = self.make_plan()
        self.assertFalse(result['applied'])
        self.assertEqual(self.call('validate', '--plan', self.plan)[0], 0)
        args = self.review()
        self.assertEqual(self.db.read_bytes(), before)
        effects = json.loads(self.plan.read_text())['plan']['expected']
        self.assertEqual((effects['originals_granted'], effects['memberships_changed'], effects['legacy_records_changed']),
                         (False, False, False))
        self.assertEqual(self.query('SELECT * FROM access_provisioning_receipts'), [])

    def test_happy_apply_is_atomic_scoped_and_visible(self):
        self.make_plan(); args = self.review()
        before_assets = self.query('SELECT * FROM access_asset_libraries')
        before_person = self.query('SELECT * FROM persons')
        before_album = self.query('SELECT * FROM albums')
        code, result, error = self.apply(args)
        self.assertEqual((code, error), (0, '')); self.assertTrue(result['applied'])
        self.assertEqual(self.query('SELECT person_id,library_id,creator_id,revision FROM access_person_libraries'),
                         [(1, 'family-a', self.owner, 1), (2, 'family-a', self.owner, 1)])
        self.assertEqual(self.query('SELECT album_id,library_id,creator_id,revision FROM access_album_libraries'),
                         [(1, 'family-a', self.owner, 1), (2, 'family-a', self.owner, 1)])
        self.assertEqual(self.query('SELECT * FROM access_asset_libraries'), before_assets)
        self.assertEqual(self.query('SELECT * FROM persons'), before_person)
        self.assertEqual(self.query('SELECT * FROM albums'), before_album)
        self.assertEqual(self.query("SELECT action FROM access_audit WHERE action LIKE 'offline.%'"),
                         [('offline.import_management_ownership',)])
        self.assertEqual(self.query('SELECT count(*) FROM access_provisioning_receipts'), [(1,)])
        with ExistingDatabase(self.db, read_only=True)() as db:
            access = AccessService(db, clock=lambda: self.now)
            people = People(access).list(fixtures.LibraryReadTests.owner_token, 'family-a', 1, '')
            albums = Albums(access).list(fixtures.LibraryReadTests.owner_token, 'family-a', 1)
        self.assertEqual([item['id'] for item in people['items']], ['1', '2'])
        self.assertEqual([item['id'] for item in albums['items']], ['2', '1'])

    def test_apply_requires_shutdown_and_replay_receipt(self):
        self.make_plan(); args = self.review()
        before = self.db.read_bytes()
        self.assertEqual(self.apply(args, stopped=False)[0], 2)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.apply(args)[0], 0)
        self.assertEqual(self.apply(args)[0], 2)
        code, result, error = self.call('receipt', '--plan-id', self.plan_id,
                                         '--reviewed-plan-digest', self.plan_digest)
        self.assertEqual((code, error), (0, '')); self.assertTrue(result['receipt_found'])

    def test_refuses_foreign_unmapped_shared_unknown_and_malformed_entities(self):
        cases = [
            ({'person_ids': [9999]}, 'unknown'),
            ({'person_ids': [2], 'include_orphan_people': False}, 'orphan'),
            ({'album_ids': [2], 'include_empty_albums': False}, 'empty'),
            ({'album_ids': [1], 'person_ids': []}, 'unmapped'),
            ({'person_ids': [1, 1]}, 'duplicate'),
            ({'person_ids': ['1']}, 'string'),
        ]
        for changes, _label in cases:
            with self.subTest(changes=changes):
                if changes.get('album_ids') == [1] and changes.get('person_ids') == []:
                    self.mutate('DELETE FROM access_asset_libraries WHERE asset_id=102')
                self.request_value(**changes)
                self.assertEqual(self.call('plan-management', '--request', self.request, '--out', self.plan)[0], 2)
        self.mutate("INSERT INTO access_person_libraries VALUES (1,'family-b',?,1)", (self.owner,))
        self.request_value(person_ids=[1], album_ids=[])
        self.assertEqual(self.call('plan-management', '--request', self.request, '--out', self.plan)[0], 2)

    def test_refuses_person_faces_foreign_or_unmapped_to_selected_library(self):
        self.mutate("INSERT INTO persons(id,display_name,face_count) VALUES (3,'Foreign face',1)")
        self.mutate("INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id) "
                    "VALUES (903,201,0,0,1,1,3)")
        self.mutate("INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id) "
                    "VALUES (905,101,0,0,1,1,3)")
        self.request_value(person_ids=[3], album_ids=[])
        self.assertEqual(self.call('plan-management', '--request', self.request, '--out', self.plan)[0], 2)
        self.mutate("INSERT INTO persons(id,display_name,face_count) VALUES (4,'Unmapped face',1)")
        self.mutate("INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id) "
                    "VALUES (904,999,0,0,1,1,4)")
        self.request_value(person_ids=[4], album_ids=[])
        self.assertEqual(self.call('plan-management', '--request', self.request, '--out', self.plan)[0], 2)

    def test_refuses_running_task_and_wal(self):
        self.mutate("INSERT INTO tasks(type,payload_json,state,priority,retry_count) VALUES ('synthetic','{}','running',1,0)")
        self.request_value()
        self.assertEqual(self.call('plan-management', '--request', self.request, '--out', self.plan)[0], 2)
        self.mutate('DELETE FROM tasks')
        self.mutate('PRAGMA journal_mode=WAL')
        self.assertEqual(self.call('plan-management', '--request', self.request, '--out', self.plan)[0], 2)

    def test_refuses_entity_size_bounds(self):
        self.request_value(person_ids=list(range(1, 502)), album_ids=[])
        self.assertEqual(self.call('plan-management', '--request', self.request, '--out', self.plan)[0], 2)

    def test_pending_face_jobs_refused_but_stopped_caption_queue_preserved(self):
        for kind in ('face', 'face_embed', 'person_cluster', 'person_recluster', 'person_label_propagate'):
            with self.subTest(kind=kind):
                self.mutate("INSERT INTO tasks(type,payload_json,state,priority,retry_count) VALUES (?,'{}','pending',1,0)", (kind,))
                self.request_value()
                self.assertEqual(self.call('plan-management', '--request', self.request, '--out', self.plan)[0], 2)
                self.mutate('DELETE FROM tasks')
        self.mutate("INSERT INTO tasks(type,payload_json,state,priority,retry_count) VALUES ('caption','{}','pending',1,0)")
        before = self.query('SELECT * FROM tasks')
        self.make_plan(); args = self.review()
        self.assertEqual(self.apply(args)[0], 0)
        self.assertEqual(self.query('SELECT * FROM tasks'), before)

    def test_refuses_oversized_legacy_metadata_without_rewriting_it(self):
        for sql in ("UPDATE persons SET display_name=? WHERE id=1",
                    "UPDATE persons SET embedding_path=? WHERE id=1",
                    "UPDATE albums SET title=? WHERE id=1"):
            with self.subTest(sql=sql):
                self.mutate(sql, ('x' * 5000,))
                before = self.db.read_bytes()
                self.request_value()
                self.assertEqual(self.call('plan-management', '--request', self.request, '--out', self.plan)[0], 2)
                self.assertEqual(self.db.read_bytes(), before)
                self.mutate("UPDATE persons SET display_name='Alice',embedding_path=NULL WHERE id=1")
                self.mutate("UPDATE albums SET title='Family trip' WHERE id=1")

    def test_refuses_album_with_more_than_sixty_ordered_items(self):
        with ExistingDatabase(self.db)() as db:
            db.execute("INSERT INTO albums(id,title,theme,status) VALUES (3,'Too many','trip','draft')")
            db.executemany("INSERT INTO assets(id,path,hash_sha256,status) VALUES (?,?,'synthetic','active')",
                           ((asset_id, 'synthetic/size-' + str(asset_id)) for asset_id in range(1001, 1062)))
            db.executemany("INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (?,'family-a')",
                           ((asset_id,) for asset_id in range(1001, 1062)))
            db.executemany('INSERT INTO album_assets(album_id,asset_id,position) VALUES (3,?,?)',
                           ((asset_id, position) for position, asset_id in enumerate(range(1001, 1062), 1)))
            db.commit()
        self.request_value(person_ids=[], album_ids=[3], include_orphan_people=False, include_empty_albums=True)
        self.assertEqual(self.call('plan-management', '--request', self.request, '--out', self.plan)[0], 2)

    def test_refuses_preowned_entity_even_when_owned_by_same_library(self):
        self.mutate("INSERT INTO access_person_libraries VALUES (1,'family-a',?,1)", (self.owner,))
        self.request_value(person_ids=[1], album_ids=[])
        self.assertEqual(self.call('plan-management', '--request', self.request, '--out', self.plan)[0], 2)

    def test_stale_entity_refuses_without_apply(self):
        self.make_plan(); args = self.review()
        self.mutate("UPDATE persons SET display_name='Changed' WHERE id=1")
        self.assertEqual(self.apply(args)[0], 2)
        self.assertEqual(self.query('SELECT * FROM access_person_libraries'), [])

    def test_stale_audience_refuses_without_apply(self):
        self.make_plan(); args = self.review(); self.mutate("UPDATE access_memberships SET revision=revision+1 WHERE account_id=?", (self.owner,))
        self.assertEqual(self.apply(args)[0], 2)

    def test_expiry_refuses_without_apply(self):
        self.make_plan(); args = self.review(); self.now = NOW + 900
        self.assertEqual(self.apply(args)[0], 2)

    def test_database_changed_since_matching_backup_refuses_review(self):
        self.make_plan(); self.copy_backup()
        self.mutate("UPDATE persons SET display_name='Changed' WHERE id=1")
        args = ['--plan', self.plan, '--backup', self.backup,
                '--reviewed-plan-digest', self.plan_digest,
                '--authority-reference', 'synthetic-authority',
                '--restore-reference', 'synthetic-restore']
        self.assertEqual(self.call('review', *args)[0], 2)

    def test_trigger_failure_rolls_back_ownership_receipt_and_audit(self):
        self.mutate("""CREATE TRIGGER fail_management_audit AFTER INSERT ON access_audit
                     WHEN NEW.action='offline.import_management_ownership'
                     BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END""")
        self.make_plan(); args = self.review()
        self.assertEqual(self.apply(args)[0], 2)
        self.assertEqual(self.query('SELECT * FROM access_person_libraries'), [])
        self.assertEqual(self.query('SELECT * FROM access_album_libraries'), [])
        self.assertEqual(self.query('SELECT * FROM access_provisioning_receipts'), [])
        self.assertEqual(self.query("SELECT action FROM access_audit WHERE action LIKE 'offline.%'"), [])

    def test_post_apply_management_freshness_guard_rolls_back_trigger_mutation(self):
        self.mutate("""CREATE TRIGGER mutate_management_person AFTER INSERT ON access_person_libraries
                     BEGIN UPDATE persons SET display_name='Tampered' WHERE id=NEW.person_id; END""")
        self.make_plan(); args = self.review()
        self.assertEqual(self.apply(args)[0], 2)
        self.assertEqual(self.query('SELECT display_name FROM persons WHERE id=1'), [('Alice',)])
        self.assertEqual(self.query('SELECT * FROM access_person_libraries'), [])
        self.assertEqual(self.query('SELECT * FROM access_album_libraries'), [])
        self.assertEqual(self.query('SELECT * FROM access_provisioning_receipts'), [])
        self.assertEqual(self.query("SELECT action FROM access_audit WHERE action LIKE 'offline.%'"), [])


if __name__ == '__main__':
    unittest.main()
