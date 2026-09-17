"""Synthetic coverage for promoting member uploads and reassigning photos.

The load-bearing property is that promotion is the **only** reviewed path from the incoming area
into a library, and that it does the file move and the mapping together: an assignment without a
promotion would leave `assets.path` outside the originals root, so the photo would be in a
library and still unviewable.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.bootstrap import bootstrap_owner
from app.access.library import LibraryReads
from app.access.promotion import (PROMOTE_OPERATION, REASSIGN_OPERATION, PromotionPlanner,
                                  PromotionReview, promote_and_assign, reassign_assets)
from app.access.provisioning import PlanRejected
from app.access.runtime import ExistingDatabase
from app.access.service import AccessService
from app.access.transport import AccessRuntime
from app.access.upload import UploadRuntime
from app.access.provisioning_apply import plan_digest
from test_orm_migrations import config
from test_access_foundation import OWNER, OTHER_OWNER, MEMBER, PASSWORD, NOW

BATCH = 'b' * 32


def png(width, height):
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    chunk = struct.pack('>I', len(ihdr)) + b'IHDR' + ihdr + b'\x00' * 4
    return b'\x89PNG\r\n\x1a\n' + chunk


class PromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='photohouse-promotion-template-')
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
        bootstrap_owner(cls.template, phone=OTHER_OWNER, password=PASSWORD, library_id='family-b')
        service = AccessService(cls.template, clock=lambda: NOW)
        cls.owner_token = service.login(OWNER, PASSWORD)
        cls.other_token = service.login(OTHER_OWNER, PASSWORD)
        cls.member_token = service.register(
            MEMBER, PASSWORD, service.invite(cls.owner_token, 'family-a', MEMBER), 'Synthetic Member')
        cls.member_id = service.profile(cls.member_token)['account_id']
        cls.owner_id = service.profile(cls.owner_token)['account_id']
        cls.other_id = service.profile(cls.other_token)['account_id']
        # An already-mapped asset, so reassignment has something to move.
        cls.template.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height)
            VALUES (900,'private-synthetic/900.jpg','private-hash-900','active','image/jpeg',640,480)''')
        cls.template.execute("INSERT INTO access_asset_libraries VALUES (900,'family-a')")
        cls.template.commit()

    @classmethod
    def tearDownClass(cls):
        cls.template.close()
        cls.directory.cleanup()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-promotion-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.path = self.root / 'synthetic.sqlite'
        with closing(sqlite3.connect(self.path)) as db:
            self.template.backup(db)
        self.incoming = self.root / '00_MEMBER_UPLOADS'
        self.originals = self.root / '01_INCOMING'
        self.originals.mkdir()
        self.access = AccessRuntime(self.connection, 'https://photohouse.test', clock=lambda: NOW)
        self.uploads = UploadRuntime(self.access, self.incoming, (self.originals,))

    def connection(self):
        db = sqlite3.connect(self.path)
        db.execute('PRAGMA foreign_keys=ON')
        db.row_factory = sqlite3.Row
        return db

    def rows(self, sql, args=()):
        with closing(self.connection()) as db:
            return db.execute(sql, args).fetchall()

    def upload(self, data=None, filename='photo.png'):
        return self.uploads.store(self.member_token, data or png(640, 480), filename, BATCH)

    def planned(self, method, **kwargs):
        with ExistingDatabase(self.path.resolve(), read_only=True)() as db:
            planner = PromotionPlanner(db, clock=lambda: NOW)
            return getattr(planner, method)(**kwargs)

    def review(self, envelope, **overrides):
        values = {'database': self.path.resolve(), 'database_identity': None,
                  'plan_digest': plan_digest(envelope), 'authority_reference': 'ticket-0001',
                  'incoming_root': self.incoming, 'originals_root': self.originals}
        values.update(overrides)
        from app.access.provisioning_apply import _identity
        if values['database_identity'] is None:
            values['database_identity'] = _identity(self.path.resolve())
        return PromotionReview(**values)

    def test_promotion_moves_the_file_and_makes_the_photo_visible(self):
        uploaded = self.upload()
        asset_id = int(uploaded['asset_id'])
        # Invisible before: it is in no library.
        reads = LibraryReads(AccessService(self.connection(), clock=lambda: NOW))
        self.assertNotIn(str(asset_id),
                         [str(item['id']) for item in reads.gallery(self.owner_token, 'family-a')['items']])
        envelope = self.planned('promote', library_id='family-a',
                                operator_account_id=self.owner_id, asset_ids=[asset_id])
        self.assertEqual(envelope['plan']['operation'], PROMOTE_OPERATION)
        receipt = promote_and_assign(envelope, review=self.review(envelope), clock=lambda: NOW)
        self.assertEqual(receipt['asset_count'], 1)
        self.assertEqual(receipt['library_id'], 'family-a')
        # The row now points into the originals root, grouped, and the mapping exists.
        stored = Path(self.rows('SELECT path FROM assets WHERE id=?', (asset_id,))[0][0])
        self.assertTrue(stored.is_relative_to(self.originals.resolve()), stored)
        self.assertEqual(stored.parent.name, BATCH)
        self.assertEqual(stored.parent.parent.parent.name, '_member_uploads')
        self.assertTrue(stored.exists())
        self.assertEqual(self.rows('SELECT state FROM access_uploads WHERE asset_id=?', (asset_id,))[0][0],
                         'assigned')
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                   (asset_id,))[0][0], 'family-a')
        self.assertEqual(len(self.rows('SELECT 1 FROM access_provisioning_receipts')), 1)
        # And it is now visible, which is the point of the operation.
        reads = LibraryReads(AccessService(self.connection(), clock=lambda: NOW))
        self.assertIn(str(asset_id),
                      [str(item['id']) for item in reads.gallery(self.owner_token, 'family-a')['items']])
        # The incoming copy is gone, so nothing is left behind to be reviewed twice.
        self.assertEqual(list(self.incoming.rglob('*.png')), [])

    def test_an_upload_can_only_be_promoted_once(self):
        uploaded = self.upload()
        asset_id = int(uploaded['asset_id'])
        envelope = self.planned('promote', library_id='family-a',
                                operator_account_id=self.owner_id, asset_ids=[asset_id])
        promote_and_assign(envelope, review=self.review(envelope), clock=lambda: NOW)
        with self.assertRaises(PlanRejected):
            self.planned('promote', library_id='family-a',
                         operator_account_id=self.owner_id, asset_ids=[asset_id])

    def test_promotion_requires_an_owner_who_is_also_a_registered_operator(self):
        uploaded = self.upload()
        asset_id = int(uploaded['asset_id'])
        # The member is approved for family-a but is not an owner and not an operator.
        with self.assertRaises(PlanRejected):
            self.planned('promote', library_id='family-a',
                         operator_account_id=self.member_id, asset_ids=[asset_id])
        # The other owner is an operator, but of a different library.
        with self.assertRaises(PlanRejected):
            self.planned('promote', library_id='family-a',
                         operator_account_id=self.other_id, asset_ids=[asset_id])

    def test_a_recorded_path_outside_the_configured_incoming_root_is_refused(self):
        """Applying against the wrong roots must move nothing."""
        uploaded = self.upload()
        asset_id = int(uploaded['asset_id'])
        envelope = self.planned('promote', library_id='family-a',
                                operator_account_id=self.owner_id, asset_ids=[asset_id])
        elsewhere = self.root / 'somewhere-else'
        elsewhere.mkdir()
        review = self.review(envelope, incoming_root=elsewhere)
        with self.assertRaises(PlanRejected):
            promote_and_assign(envelope, review=review, clock=lambda: NOW)
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                   (asset_id,)), [])
        self.assertEqual(len(list(self.incoming.rglob('*.png'))), 1, 'the file must not have moved')

    def test_a_file_that_changed_since_planning_is_refused(self):
        uploaded = self.upload()
        asset_id = int(uploaded['asset_id'])
        envelope = self.planned('promote', library_id='family-a',
                                operator_account_id=self.owner_id, asset_ids=[asset_id])
        stored = Path(self.rows('SELECT path FROM assets WHERE id=?', (asset_id,))[0][0])
        stored.write_bytes(stored.read_bytes() + b'x')
        with self.assertRaises(PlanRejected):
            promote_and_assign(envelope, review=self.review(envelope), clock=lambda: NOW)
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                   (asset_id,)), [])

    def test_the_incoming_root_must_not_overlap_the_originals_root(self):
        uploaded = self.upload()
        envelope = self.planned('promote', library_id='family-a',
                                operator_account_id=self.owner_id, asset_ids=[int(uploaded['asset_id'])])
        with self.assertRaises(PlanRejected):
            promote_and_assign(envelope, review=self.review(envelope, incoming_root=self.originals),
                               clock=lambda: NOW)

    def make_owner_of_both(self):
        """A reassignment takes a photo away from one audience, so one person must own both."""
        with self.connection() as db:
            db.execute('''INSERT INTO access_memberships
                (account_id,library_id,status,role,revision,approved_by)
                VALUES (?,?,'approved','owner',1,?)''', (self.owner_id, 'family-b', self.other_id))
            db.commit()

    def test_reassign_moves_a_photo_between_libraries(self):
        self.make_owner_of_both()
        envelope = self.planned('reassign', library_id='family-b',
                                operator_account_id=self.owner_id, asset_ids=[900])
        self.assertEqual(envelope['plan']['operation'], REASSIGN_OPERATION)
        receipt = reassign_assets(envelope, review=self.review(envelope), clock=lambda: NOW)
        self.assertEqual(receipt['source_libraries'], ['family-a'])
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=900')[0][0],
                         'family-b')
        # Exactly one mapping, because asset_id is the primary key.
        self.assertEqual(len(self.rows('SELECT 1 FROM access_asset_libraries WHERE asset_id=900')), 1)
        # The bytes never moved: reassignment is database-only.
        self.assertEqual(self.rows('SELECT path FROM assets WHERE id=900')[0][0], 'private-synthetic/900.jpg')

    def test_reassign_refuses_an_asset_already_in_the_target_library(self):
        with self.assertRaises(PlanRejected):
            self.planned('reassign', library_id='family-a',
                         operator_account_id=self.owner_id, asset_ids=[900])

    def test_reassign_requires_ownership_of_both_libraries(self):
        """Owning only one side is not enough, in either direction."""
        # Owns the source, not the target.
        with self.assertRaises(PlanRejected):
            self.planned('reassign', library_id='family-b',
                         operator_account_id=self.owner_id, asset_ids=[900])
        # Owns the target, not the source.
        with self.assertRaises(PlanRejected):
            self.planned('reassign', library_id='family-b',
                         operator_account_id=self.other_id, asset_ids=[900])
        # And it succeeds once one account owns both.
        self.make_owner_of_both()
        self.planned('reassign', library_id='family-b',
                     operator_account_id=self.owner_id, asset_ids=[900])

    def test_a_plan_is_bound_to_its_database_and_review(self):
        uploaded = self.upload()
        envelope = self.planned('promote', library_id='family-a',
                                operator_account_id=self.owner_id, asset_ids=[int(uploaded['asset_id'])])
        # A different reviewed digest must not be accepted.
        from dataclasses import replace
        with self.assertRaises(PlanRejected):
            promote_and_assign(envelope, review=replace(self.review(envelope), plan_digest='0' * 64),
                               clock=lambda: NOW)
        # Nor a tampered envelope.
        tampered = {'plan': dict(envelope['plan']), 'seal': envelope['seal']}
        tampered['plan']['target'] = dict(tampered['plan']['target'], library_id='family-b')
        with self.assertRaises(PlanRejected):
            promote_and_assign(tampered, review=self.review(envelope), clock=lambda: NOW)
