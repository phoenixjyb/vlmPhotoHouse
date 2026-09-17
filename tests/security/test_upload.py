"""Real migrated synthetic SQLite against the upload service boundary.

The load-bearing property is that an accepted upload lands in **no** library: the gallery read
must not list it, and the media route must not serve it, until an operator promotes and assigns
it. Everything else here guards a way that could quietly stop being true.
"""
from contextlib import closing
from pathlib import Path
import hashlib
import sqlite3
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.bootstrap import bootstrap_owner
from app.access.library import LibraryReads
from app.access.service import AccessDenied, AccessService
from app.access.transport import AccessRuntime
from app.access.upload import MAX_UPLOAD_BYTES, UploadRuntime, dimensions, sniff
from test_orm_migrations import config
from test_access_foundation import OWNER, MEMBER, PASSWORD, NOW

BATCH = 'a' * 32


def png(width, height, pad=b''):
    """A real PNG header, so the parser is exercised rather than mocked."""
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    chunk = struct.pack('>I', len(ihdr)) + b'IHDR' + ihdr + b'\x00' * 4
    return b'\x89PNG\r\n\x1a\n' + chunk + pad


def jpeg(width, height):
    sof = (b'\xff\xc0' + struct.pack('>H', 17) + b'\x08'
           + struct.pack('>HH', height, width) + b'\x03' + b'\x00' * 9)
    return b'\xff\xd8\xff\xe0' + struct.pack('>H', 4) + b'\x00\x00' + sof + b'\xff\xd9'


class UploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='photohouse-upload-template-')
        path = Path(cls.directory.name) / 'synthetic.sqlite'
        engine = create_engine('sqlite:///' + str(path))
        with engine.begin() as connection:
            cfg = config()
            cfg.attributes['connection'] = connection
            command.upgrade(cfg, 'head')
        engine.dispose()
        cls.template = sqlite3.connect(path)
        cls.template.execute('PRAGMA foreign_keys=ON')
        bootstrap_owner(cls.template, phone=OWNER, password=PASSWORD, library_id='family-a')
        service = AccessService(cls.template, clock=lambda: NOW)
        cls.owner_token = service.login(OWNER, PASSWORD)
        cls.member_token = service.register(
            MEMBER, PASSWORD, service.invite(cls.owner_token, 'family-a', MEMBER), 'Synthetic Member')
        cls.member_id = service.profile(cls.member_token)['account_id']
        # One asset already mapped into the library, to prove cross-library dedup does not
        # return a foreign asset id.
        cls.template.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height)
            VALUES (900,'private-synthetic/900.jpg','private-hash-900','active','image/jpeg',640,480)''')
        cls.template.execute("INSERT INTO access_asset_libraries VALUES (900,'family-a')")
        cls.template.commit()

    @classmethod
    def tearDownClass(cls):
        cls.template.close()
        cls.directory.cleanup()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-upload-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.path = self.root / 'synthetic.sqlite'
        with closing(sqlite3.connect(self.path)) as db:
            self.template.backup(db)
        self.incoming = self.root / 'INCOMING'
        self.originals = self.root / 'originals'
        self.access = AccessRuntime(self.connection, 'https://photohouse.test', clock=lambda: NOW)
        self.runtime = UploadRuntime(self.access, self.incoming, (self.originals,))
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start()
            self.addCleanup(guard.stop)

    def connection(self):
        db = sqlite3.connect(self.path)
        db.execute('PRAGMA foreign_keys=ON')
        db.row_factory = sqlite3.Row
        return db

    def upload(self, data, filename='photo.png', token=None, batch=BATCH):
        return self.runtime.store(token or self.member_token, data, filename, batch)

    def rows(self, sql, args=()):
        with closing(self.connection()) as db:
            return db.execute(sql, args).fetchall()

    def test_accepted_upload_is_in_no_library(self):
        result = self.upload(png(640, 480))
        self.assertIsNone(result['library_id'])
        self.assertEqual(result['tasks_enqueued'], 5)
        asset_id = int(result['asset_id'])
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                   (asset_id,)), [])
        self.assertEqual(len(self.rows('SELECT 1 FROM access_uploads WHERE asset_id=?', (asset_id,))), 1)
        self.assertEqual(len(self.rows("SELECT 1 FROM access_audit WHERE action='upload.create'")), 1)
        self.assertEqual(len(self.rows('SELECT 1 FROM tasks WHERE state=?', ('pending',))), 5)

    def test_uploaded_asset_is_invisible_to_the_library_read(self):
        """The gallery read is the real path a member would use, so assert against it."""
        result = self.upload(png(640, 480))
        reads = LibraryReads(AccessService(self.connection(), clock=lambda: NOW))
        gallery = reads.gallery(self.member_token, 'family-a')
        self.assertEqual([str(item['id']) for item in gallery['items']], ['900'])
        self.assertNotIn(result['asset_id'], [str(item['id']) for item in gallery['items']])

    def test_bytes_decide_the_type_not_the_filename(self):
        # PNG bytes under a .jpg name are stored as PNG; the declared name never selects it.
        result = self.upload(png(64, 64), filename='mislabelled.jpg')
        stored = self.rows('SELECT path FROM assets WHERE id=?', (int(result['asset_id']),))[0][0]
        self.assertTrue(stored.endswith('.png'), stored)
        self.assertEqual(result['kind'], 'image')
        # Garbage under an allowed name is refused, and writes nothing new.
        before = sorted(p.name for p in self.incoming.rglob('*'))
        with self.assertRaises(AccessDenied):
            self.upload(b'not an image at all', filename='photo.png')
        self.assertEqual(sorted(p.name for p in self.incoming.rglob('*')), before)
        self.assertEqual(len(self.rows('SELECT 1 FROM access_uploads')), 1)

    def test_a_decompression_bomb_is_refused_before_anything_is_written(self):
        with self.assertRaises(AccessDenied):
            self.upload(png(20000, 20000))
        self.assertFalse(self.incoming.exists(), 'a refused upload must not create the folder')
        self.assertEqual(self.rows('SELECT 1 FROM access_uploads'), [])

    def test_oversize_body_is_refused(self):
        with self.assertRaises(AccessDenied):
            self.upload(png(8, 8, pad=b'\x00' * (MAX_UPLOAD_BYTES + 1)))
        self.assertEqual(self.rows('SELECT 1 FROM access_uploads'), [])

    def test_retry_of_the_same_bytes_does_not_create_a_second_asset(self):
        first = self.upload(png(640, 480))
        second = self.upload(png(640, 480))
        self.assertEqual(first['asset_id'], second['asset_id'])
        self.assertEqual(second['tasks_enqueued'], 0)
        self.assertEqual(len(self.rows('SELECT 1 FROM access_uploads')), 1)

    def test_dedup_never_returns_an_asset_that_is_already_in_a_library(self):
        """A hash matching a mapped asset must not confirm the file exists elsewhere."""
        with closing(self.connection()) as db:
            existing = db.execute('SELECT hash_sha256 FROM assets WHERE id=900').fetchone()[0]
        # Upload the same content the mapped asset claims; the mapping must not be reused.
        with self.connection() as db:
            db.execute('UPDATE assets SET hash_sha256=? WHERE id=900', (hashlib.sha256(png(32, 32)).hexdigest(),))
            db.commit()
        result = self.upload(png(32, 32))
        self.assertNotEqual(result['asset_id'], '900')
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                   (int(result['asset_id']),)), [])

    def test_a_revoked_member_cannot_upload(self):
        with self.connection() as db:
            db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                       (self.member_id,))
            db.commit()
        with self.assertRaises(AccessDenied):
            self.upload(png(64, 64))
        self.assertEqual(self.rows('SELECT 1 FROM access_uploads'), [])

    def test_an_unknown_session_cannot_upload(self):
        with self.assertRaises(AccessDenied):
            self.upload(png(64, 64), token='not-a-real-session-token')
        self.assertEqual(self.rows('SELECT 1 FROM access_uploads'), [])

    def test_the_batch_must_be_a_bounded_identifier(self):
        for bad in ('', 'short', '../escape', 'a' * 33, 'A' * 32):
            with self.subTest(batch=bad):
                with self.assertRaises(AccessDenied):
                    self.upload(png(64, 64), batch=bad)

    def test_the_incoming_root_must_not_overlap_an_original_root(self):
        """This is the invariant that makes an unassigned upload unservable."""
        for bad in (self.originals / 'INCOMING', self.root, self.originals):
            with self.subTest(incoming=str(bad)):
                with self.assertRaises(ValueError):
                    UploadRuntime(self.access, bad, (self.originals,))
        # The reverse nesting is refused too, not just the one direction.
        with self.assertRaises(ValueError):
            UploadRuntime(self.access, self.root / 'outer', (self.root / 'outer' / 'originals',))
        # And the sibling layout this project actually uses is accepted.
        self.assertIsInstance(self.runtime, UploadRuntime)

    def test_the_file_lands_under_the_members_own_label_and_batch(self):
        result = self.upload(png(640, 480))
        stored = Path(self.rows('SELECT path FROM assets WHERE id=?', (int(result['asset_id']),))[0][0])
        self.assertTrue(stored.is_relative_to(self.incoming.resolve()))
        self.assertEqual(stored.parent.name, BATCH)
        self.assertEqual(stored.parent.parent.name, result['incoming'])
        self.assertIn('-', result['incoming'])

    def client(self, upload_runtime='configured'):
        from app.main import create_app
        return TestClient(
            create_app(access_runtime=self.access,
                       upload_runtime=self.runtime if upload_runtime == 'configured' else upload_runtime),
            base_url='https://photohouse.test', client=('192.0.2.20', 23456))

    def headers(self, **overrides):
        base = {'Authorization': 'Bearer ' + self.member_token,
                'Content-Type': 'application/octet-stream',
                'X-Upload-Filename': 'photo.png', 'X-Upload-Batch': BATCH}
        base.update(overrides)
        return base

    def test_route_answers_503_when_no_upload_runtime_is_configured(self):
        """The default app mounts the route but grants nothing until an operator opts in."""
        response = self.client(upload_runtime=None).post('/uploads', headers=self.headers(),
                                                         content=png(64, 64))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.rows('SELECT 1 FROM access_uploads'), [])

    def test_route_requires_credentials(self):
        anonymous = self.headers()
        anonymous.pop('Authorization')
        self.assertEqual(self.client().post('/uploads', headers=anonymous,
                                            content=png(64, 64)).status_code, 401)

    def test_route_requires_the_filename_and_batch_headers(self):
        for missing in ('X-Upload-Filename', 'X-Upload-Batch'):
            with self.subTest(missing=missing):
                headers = self.headers()
                headers.pop(missing)
                self.assertEqual(self.client().post('/uploads', headers=headers,
                                                    content=png(64, 64)).status_code, 400)

    def test_route_refuses_a_wrong_content_type(self):
        self.assertEqual(self.client().post('/uploads', headers=self.headers(**{'Content-Type': 'application/json'}),
                                            content=png(64, 64)).status_code, 400)
        self.assertEqual(self.client().post('/uploads', headers=self.headers(**{'Content-Encoding': 'gzip'}),
                                            content=png(64, 64)).status_code, 400)

    def test_route_refuses_an_oversize_declared_length_before_reading_the_body(self):
        headers = self.headers(**{'Content-Length': str(MAX_UPLOAD_BYTES + 1)})
        response = self.client().post('/uploads', headers=headers, content=b'')
        self.assertEqual(response.status_code, 413)

    def test_route_accepts_an_upload_that_stays_out_of_every_library(self):
        response = self.client().post('/uploads', headers=self.headers(), content=png(640, 480))
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIsNone(body['library_id'])
        self.assertEqual(body['tasks_enqueued'], 5)
        asset_id = int(body['asset_id'])
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                   (asset_id,)), [])
        # And the library read still does not offer it.
        reads = LibraryReads(AccessService(self.connection(), clock=lambda: NOW))
        self.assertNotIn(str(asset_id),
                         [str(item['id']) for item in reads.gallery(self.member_token, 'family-a')['items']])

    def test_runtime_configuration_refuses_an_incoming_root_inside_an_original_root(self):
        from app.access.runtime import RuntimeConfiguration
        configuration = RuntimeConfiguration(self.path.resolve(), 'https://photohouse.test',
                                              (self.originals,), self.root / 'derived',
                                              incoming_root=self.originals / 'INCOMING')
        with self.assertRaises(ValueError):
            configuration.build_app()

    def test_runtime_configuration_wires_the_upload_runtime_when_configured(self):
        from app.access.runtime import RuntimeConfiguration
        configuration = RuntimeConfiguration(self.path.resolve(), 'https://photohouse.test',
                                              (self.originals,), self.root / 'derived',
                                              incoming_root=self.incoming)
        app = configuration.build_app(clock=lambda: NOW)
        self.assertIsInstance(app.state.upload_runtime, UploadRuntime)
        self.assertIsNone(RuntimeConfiguration(self.path.resolve(), 'https://photohouse.test',
                                               (self.originals,), self.root / 'derived').build_app(
            clock=lambda: NOW).state.upload_runtime)
