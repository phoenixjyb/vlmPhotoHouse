"""Synthetic coverage for promoting member uploads and reassigning photos.

The load-bearing property is that promotion is the **only** reviewed path from the incoming area
into a library, and that it does the file move and the mapping together: an assignment without a
promotion would leave `assets.path` outside the originals root, so the photo would be in a
library and still unviewable.
"""
from contextlib import closing
import json
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
from app.access.promotion import (PROMOTE_OPERATION, REASSIGN_OPERATION, UNASSIGN_OPERATION,
                                  PromotionPlanner, PromotionReview, promote_and_assign,
                                  reassign_assets, unassign_assets)
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
        # ExistingDatabase is the closing context manager AccessRuntime expects; a raw
        # sqlite3.connect here would leak a connection on every call.
        self.access = AccessRuntime(ExistingDatabase(self.path.resolve()),
                                    'https://photohouse.test', clock=lambda: NOW)
        self.uploads = UploadRuntime(self.access, self.incoming, (self.originals,))

    def connection(self):
        db = sqlite3.connect(self.path)
        db.execute('PRAGMA foreign_keys=ON')
        db.row_factory = sqlite3.Row
        return db

    def rows(self, sql, args=()):
        with closing(self.connection()) as db:
            return db.execute(sql, args).fetchall()

    def gallery(self, token):
        """Read the gallery and close the connection; a leak shows up as a ResourceWarning."""
        with closing(self.connection()) as db:
            reads = LibraryReads(AccessService(db, clock=lambda: NOW))
            return [str(item['id']) for item in reads.gallery(token, 'family-a')['items']]

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
        self.assertNotIn(str(asset_id), self.gallery(self.owner_token))
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
        self.assertIn(str(asset_id), self.gallery(self.owner_token))
        # The incoming copy is gone, so nothing is left behind to be reviewed twice.
        self.assertEqual(list(self.incoming.rglob('*.png')), [])

    def test_expired_promotion_after_move_restores_file_and_rows(self):
        uploaded = self.upload()
        asset_id = int(uploaded['asset_id'])
        envelope = self.planned('promote', library_id='family-a',
                                operator_account_id=self.owner_id, asset_ids=[asset_id])
        calls = 0
        def clock():
            nonlocal calls
            calls += 1
            return NOW if calls <= 4 else NOW + 901
        with self.assertRaises(PlanRejected):
            promote_and_assign(envelope, review=self.review(envelope), clock=clock)
        stored = Path(self.rows('SELECT path FROM assets WHERE id=?', (asset_id,))[0][0])
        self.assertTrue(stored.exists())
        self.assertEqual(self.rows('SELECT state FROM access_uploads WHERE asset_id=?', (asset_id,))[0][0],
                         'incoming')
        self.assertEqual(self.rows('SELECT 1 FROM access_asset_libraries WHERE asset_id=?',
                                   (asset_id,)), [])
        self.assertEqual(list(self.originals.rglob('*.png')), [])

    def test_promotion_failure_after_first_move_restores_all_files_and_rows(self):
        first = int(self.upload(data=png(640, 480))['asset_id'])
        second = int(self.upload(data=png(641, 480))['asset_id'])
        envelope = self.planned('promote', library_id='family-a',
                                operator_account_id=self.owner_id, asset_ids=[first, second])
        from app.access import promotion as implementation
        real_place = implementation._place
        calls = 0
        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('synthetic second-source failure')
            return real_place(source, destination)
        with patch('app.access.promotion._place', side_effect=fail_second):
            with self.assertRaises(OSError):
                promote_and_assign(envelope, review=self.review(envelope), clock=lambda: NOW)
        for asset_id in (first, second):
            stored = Path(self.rows('SELECT path FROM assets WHERE id=?', (asset_id,))[0][0])
            self.assertTrue(stored.exists())
            self.assertEqual(self.rows('SELECT state FROM access_uploads WHERE asset_id=?',
                                       (asset_id,))[0][0], 'incoming')
            self.assertEqual(self.rows('SELECT 1 FROM access_asset_libraries WHERE asset_id=?',
                                       (asset_id,)), [])
        self.assertEqual(list(self.originals.rglob('*.png')), [])

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
        with closing(self.connection()) as db:
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

    def promote(self, asset_id, library='family-a'):
        envelope = self.planned('promote', library_id=library,
                                operator_account_id=self.owner_id, asset_ids=[asset_id])
        return promote_and_assign(envelope, review=self.review(envelope), clock=lambda: NOW)

    def test_unassign_returns_the_photo_to_pending_and_it_can_be_promoted_again(self):
        """The round trip is the point: an undo that cannot be redone is not an undo."""
        uploaded = self.upload()
        asset_id = int(uploaded['asset_id'])
        self.promote(asset_id)
        self.assertIn(str(asset_id), self.gallery(self.owner_token))

        envelope = self.planned('unassign', library_id='family-a',
                                operator_account_id=self.owner_id, asset_ids=[asset_id])
        self.assertEqual(envelope['plan']['operation'], UNASSIGN_OPERATION)
        receipt = unassign_assets(envelope, review=self.review(envelope), clock=lambda: NOW)
        self.assertEqual(receipt['asset_count'], 1)
        # Invisible again, unmapped, and back in the incoming area with a matching row.
        self.assertNotIn(str(asset_id), self.gallery(self.owner_token))
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                   (asset_id,)), [])
        self.assertEqual(self.rows('SELECT state FROM access_uploads WHERE asset_id=?', (asset_id,))[0][0],
                         'incoming')
        stored = Path(self.rows('SELECT path FROM assets WHERE id=?', (asset_id,))[0][0])
        self.assertTrue(stored.is_relative_to(self.incoming.resolve()), stored)
        self.assertTrue(stored.exists())
        # And the same plan can be made and applied again, which is what makes this an undo.
        self.promote(asset_id)
        self.assertIn(str(asset_id), self.gallery(self.owner_token))
        # Three receipts: the first promotion, the un-assignment, and the second promotion.
        self.assertEqual(len(self.rows('SELECT 1 FROM access_provisioning_receipts')), 3)

    def test_expired_unassignment_after_move_restores_file_and_rows(self):
        asset_id = int(self.upload()['asset_id'])
        self.promote(asset_id)
        envelope = self.planned('unassign', library_id='family-a',
                                operator_account_id=self.owner_id, asset_ids=[asset_id])
        calls = 0
        def clock():
            nonlocal calls
            calls += 1
            return NOW if calls <= 4 else NOW + 901
        with self.assertRaises(PlanRejected):
            unassign_assets(envelope, review=self.review(envelope), clock=clock)
        stored = Path(self.rows('SELECT path FROM assets WHERE id=?', (asset_id,))[0][0])
        self.assertTrue(stored.exists())
        self.assertTrue(stored.is_relative_to(self.originals.resolve()), stored)
        self.assertEqual(self.rows('SELECT state FROM access_uploads WHERE asset_id=?', (asset_id,))[0][0],
                         'assigned')
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                   (asset_id,))[0][0], 'family-a')
        self.assertEqual(list(self.incoming.rglob('*.png')), [])

    def test_unassignment_failure_after_first_move_restores_all_files_and_rows(self):
        first = int(self.upload(data=png(640, 480))['asset_id'])
        second = int(self.upload(data=png(641, 480))['asset_id'])
        self.promote(first)
        self.promote(second)
        envelope = self.planned('unassign', library_id='family-a',
                                operator_account_id=self.owner_id, asset_ids=[first, second])
        from app.access import promotion as implementation
        real_place = implementation._place
        calls = 0
        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('synthetic second-source failure')
            return real_place(source, destination)
        with patch('app.access.promotion._place', side_effect=fail_second):
            with self.assertRaises(OSError):
                unassign_assets(envelope, review=self.review(envelope), clock=lambda: NOW)
        for asset_id in (first, second):
            stored = Path(self.rows('SELECT path FROM assets WHERE id=?', (asset_id,))[0][0])
            self.assertTrue(stored.exists())
            self.assertTrue(stored.is_relative_to(self.originals.resolve()), stored)
            self.assertEqual(self.rows('SELECT state FROM access_uploads WHERE asset_id=?',
                                       (asset_id,))[0][0], 'assigned')
            self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                       (asset_id,))[0][0], 'family-a')
        self.assertEqual(list(self.incoming.rglob('*.png')), [])

    def test_unassign_refuses_an_asset_that_never_came_through_upload(self):
        """An asset with no provenance row could never be promoted again, so this is a one-way door."""
        with self.assertRaises(PlanRejected):
            self.planned('unassign', library_id='family-a',
                         operator_account_id=self.owner_id, asset_ids=[900])
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=900')[0][0],
                         'family-a', 'the mapping must be untouched')

    def test_unassign_requires_an_owner_of_that_library(self):
        uploaded = self.upload()
        asset_id = int(uploaded['asset_id'])
        self.promote(asset_id)
        for actor in (self.member_id, self.other_id):
            with self.subTest(actor=actor):
                with self.assertRaises(PlanRejected):
                    self.planned('unassign', library_id='family-a',
                                 operator_account_id=actor, asset_ids=[asset_id])

    def test_unassign_refuses_an_asset_in_another_library(self):
        uploaded = self.upload()
        asset_id = int(uploaded['asset_id'])
        self.promote(asset_id)
        with self.assertRaises(PlanRejected):
            self.planned('unassign', library_id='family-b',
                         operator_account_id=self.other_id, asset_ids=[asset_id])

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


class PromotionCliTests(PromotionTests):
    """The same operations, driven through the operator tool an operator would actually use."""

    def setUp(self):
        super().setUp()
        import io
        from contextlib import redirect_stdout, redirect_stderr
        self.io, self.redirect = io, (redirect_stdout, redirect_stderr)
        sys.path.insert(0, str(ROOT / 'scripts'))
        import provision_access as cli
        self.cli = cli
        self.request = self.root / 'request.json'
        self.plan = self.root / 'plan.json'
        # write_new_plan never overwrites, so every sealed plan needs a fresh file.
        self.plan2 = self.root / 'plan2.json'
        self.plan3 = self.root / 'plan3.json'

    def assertClean(self, code, error, expected=0):
        """The operator tool's own output must be clean.

        Not `stderr == ''`: the suite has a pre-existing unclosed-connection leak elsewhere, and
        when GC happens to run inside this capture the resulting ResourceWarning lands on stderr
        through no fault of the command. Asserting on the tool's own message keeps the check
        meaningful without making it depend on unrelated collection timing.
        """
        self.assertEqual(code, expected, error)
        self.assertNotIn('refused', error, error)

    def call(self, command, *args):
        output, error = self.io.StringIO(), self.io.StringIO()
        with self.redirect[0](output), self.redirect[1](error):
            code = self.cli.main([command, '--database', str(self.path), *map(str, args)],
                                 clock=lambda: NOW)
        return code, (json.loads(output.getvalue()) if output.getvalue() else None), error.getvalue()

    def plan_promotion(self, asset_ids, out=None):
        self.request.write_text(json.dumps({'library_id': 'family-a',
            'operator_account_id': self.owner_id, 'asset_ids': asset_ids}))
        code, result, error = self.call('plan-promote', '--request', self.request,
                                        '--out', out or self.plan)
        self.assertClean(code, error)
        self.assertEqual(result['operation'], PROMOTE_OPERATION)
        return result

    def test_plan_promote_then_apply_promotion(self):
        uploaded = self.upload()
        asset_id = int(uploaded['asset_id'])
        planned = self.plan_promotion([asset_id])
        # A read-only validation must succeed and grant nothing.
        code, validated, error = self.call('validate-promotion', '--plan', self.plan)
        self.assertClean(code, error)
        self.assertTrue(validated['valid'])
        self.assertFalse(validated['applied'])
        code, applied, error = self.call('apply-promotion', '--plan', self.plan,
            '--reviewed-plan-digest', planned['plan_digest'],
            '--authority-reference', 'synthetic-authority',
            '--incoming-root', self.incoming, '--originals-root', self.originals)
        self.assertClean(code, error)
        self.assertTrue(applied['applied'])
        self.assertEqual(applied['library_id'], 'family-a')
        self.assertEqual(applied['asset_count'], 1)
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                   (asset_id,))[0][0], 'family-a')

    def test_apply_promotion_requires_the_exact_reviewed_digest(self):
        uploaded = self.upload()
        self.plan_promotion([int(uploaded['asset_id'])])
        code, _result, error = self.call('apply-promotion', '--plan', self.plan,
            '--reviewed-plan-digest', '0' * 64,
            '--authority-reference', 'synthetic-authority',
            '--incoming-root', self.incoming, '--originals-root', self.originals)
        self.assertEqual(code, 2)
        self.assertTrue(error.startswith('Operator command refused'), error)
        self.assertEqual(self.rows('SELECT 1 FROM access_provisioning_receipts'), [])

    def test_plan_unassign_round_trips_through_the_operator_tool(self):
        uploaded = self.upload()
        asset_id = int(uploaded['asset_id'])
        planned = self.plan_promotion([asset_id])
        code, applied, error = self.call('apply-promotion', '--plan', self.plan,
            '--reviewed-plan-digest', planned['plan_digest'],
            '--authority-reference', 'synthetic-authority',
            '--incoming-root', self.incoming, '--originals-root', self.originals)
        self.assertClean(code, error)
        self.assertTrue(applied['applied'])

        self.request.write_text(json.dumps({'library_id': 'family-a',
            'operator_account_id': self.owner_id, 'asset_ids': [asset_id]}))
        code, planned_unassign, error = self.call('plan-unassign', '--request', self.request,
                                                  '--out', self.plan2)
        self.assertClean(code, error)
        self.assertEqual(planned_unassign['operation'], UNASSIGN_OPERATION)
        code, undone, error = self.call('apply-promotion', '--plan', self.plan2,
            '--reviewed-plan-digest', planned_unassign['plan_digest'],
            '--authority-reference', 'synthetic-authority',
            '--incoming-root', self.incoming, '--originals-root', self.originals)
        self.assertClean(code, error)
        self.assertTrue(undone['applied'])
        self.assertEqual(undone['asset_count'], 1)
        self.assertEqual(self.rows('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                   (asset_id,)), [])
        # And the same command promotes it again, so the tool offers a real undo.
        planned_again = self.plan_promotion([asset_id], out=self.plan3)
        code, reapplied, error = self.call('apply-promotion', '--plan', self.plan3,
            '--reviewed-plan-digest', planned_again['plan_digest'],
            '--authority-reference', 'synthetic-authority',
            '--incoming-root', self.incoming, '--originals-root', self.originals)
        self.assertClean(code, error)
        self.assertTrue(reapplied['applied'])

    def test_plan_reassign_is_available_and_validates(self):
        self.make_owner_of_both()
        self.request.write_text(json.dumps({'library_id': 'family-b',
            'operator_account_id': self.owner_id, 'asset_ids': [900]}))
        code, result, error = self.call('plan-reassign', '--request', self.request, '--out', self.plan)
        self.assertClean(code, error)
        self.assertEqual(result['operation'], REASSIGN_OPERATION)
        code, validated, error = self.call('validate-promotion', '--plan', self.plan)
        self.assertClean(code, error)
        self.assertEqual(validated['operation'], REASSIGN_OPERATION)
        # validate reports identity only; the reviewed state lives in the sealed plan itself.
        expected = json.loads(self.plan.read_text())['plan']['expected']
        self.assertEqual(expected['source_libraries'], ['family-a'])
        self.assertTrue(expected['moves_between_libraries'])
        self.assertFalse(expected['media_writes'])

    def test_the_promotion_commands_do_not_appear_for_the_backup_review_flow(self):
        """Promotion restores no backup, so it must not silently accept --backup or --restore-reference."""
        for flag in ('--backup', '--restore-reference'):
            with self.subTest(flag=flag):
                output, error = self.io.StringIO(), self.io.StringIO()
                with self.redirect[0](output), self.redirect[1](error):
                    code = self.cli.main(['apply-promotion', '--database', str(self.path),
                        '--plan', str(self.plan), '--reviewed-plan-digest', '0' * 64,
                        '--authority-reference', 'synthetic-authority',
                        '--incoming-root', str(self.incoming), '--originals-root', str(self.originals),
                        flag, str(self.root / 'x')], clock=lambda: NOW)
                self.assertEqual(code, 2)
                self.assertNotIn('x', output.getvalue())
