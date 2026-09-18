"""Synthetic coverage for clearing an abandoned task claim.

The load-bearing property is that this refuses anything that is not genuinely abandoned: a claim
younger than the minimum age is presumed live, so a slow worker cannot have its work stolen. The
second is that the timestamps are **UTC** — task rows are written with `datetime.utcnow()`, and
computing the age against local time was the mistake that produced a false "8-hour stall"
diagnosis on 2026-09-18.
"""
from contextlib import closing
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from alembic import command
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access.bootstrap import bootstrap_owner
from app.access.provisioning import PlanRejected
from app.access.provisioning_apply import _identity, plan_digest
from app.access.runtime import ExistingDatabase
from app.access.service import AccessService
from app.access.task_recovery import (MIN_CLAIM_AGE_SECONDS, OPERATION, ClaimRecoveryPlanner,
                                      ClaimRecoveryReview, claim_age_seconds, clear_abandoned_claim)
from test_orm_migrations import config
from test_access_foundation import OWNER, MEMBER, PASSWORD, NOW


class ClaimRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='photohouse-claim-template-')
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
        cls.owner_id = service.profile(cls.owner_token)['account_id']
        # A second account that is deliberately NOT a registered operator.
        cls.member_token = service.register(
            MEMBER, PASSWORD, service.invite(cls.owner_token, 'family-a', MEMBER), 'Synthetic Member')
        cls.member_id = service.profile(cls.member_token)['account_id']
        cls.template.commit()

    @classmethod
    def tearDownClass(cls):
        cls.template.close()
        cls.directory.cleanup()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-claim-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.path = self.root / 'synthetic.sqlite'
        with closing(sqlite3.connect(self.path)) as db:
            self.template.backup(db)

    def connection(self):
        db = sqlite3.connect(self.path)
        db.execute('PRAGMA foreign_keys=ON')
        db.row_factory = sqlite3.Row
        return db

    def rows(self, sql, args=()):
        with closing(self.connection()) as db:
            return db.execute(sql, args).fetchall()

    def seed_claim(self, task_id=1, kind='caption', age_seconds=MIN_CLAIM_AGE_SECONDS * 4):
        started = datetime.utcnow() - timedelta(seconds=age_seconds)
        with closing(self.connection()) as db:
            db.execute('''INSERT INTO tasks(id,type,payload_json,state,priority,retry_count,started_at)
                VALUES (?,?,?,'running',110,0,?)''',
                (task_id, kind, '{}', started.isoformat(sep=' ')))
            db.commit()

    def planned(self, task_ids, operator=None, reference='quiescent-0001'):
        with ExistingDatabase(self.path.resolve(), read_only=True)() as db:
            planner = ClaimRecoveryPlanner(db, clock=lambda: NOW)
            return planner.clear(operator_account_id=operator or self.owner_id,
                                 task_ids=task_ids, quiescence_reference=reference)

    def review(self, envelope):
        return ClaimRecoveryReview(database=self.path.resolve(),
                                   database_identity=_identity(self.path.resolve()),
                                   plan_digest=plan_digest(envelope),
                                   authority_reference='ticket-0001',
                                   quiescence_reference='quiescent-0001')

    def test_an_abandoned_claim_is_requeued(self):
        self.seed_claim()
        envelope = self.planned([1])
        self.assertEqual(envelope['plan']['operation'], OPERATION)
        receipt = clear_abandoned_claim(envelope, review=self.review(envelope), clock=lambda: NOW)
        self.assertEqual(receipt['operation'], OPERATION)
        self.assertEqual(len(receipt['requeued']), 1)
        row = self.rows('SELECT state, started_at, retry_count FROM tasks WHERE id=1')[0]
        self.assertEqual(row['state'], 'pending')
        self.assertIsNone(row['started_at'], 'the next claim writes its own start time')
        self.assertEqual(row['retry_count'], 1, 'a repeat abandonment must reach failure handling')
        self.assertEqual(len(self.rows('SELECT 1 FROM access_provisioning_receipts')), 1)
        self.assertEqual(len(self.rows("SELECT 1 FROM access_audit WHERE action='offline." + OPERATION + "'")), 1)

    def test_a_claim_younger_than_the_minimum_age_is_refused(self):
        """A slow worker must not have its work stolen."""
        self.seed_claim(age_seconds=MIN_CLAIM_AGE_SECONDS - 60)
        with self.assertRaises(PlanRejected):
            self.planned([1])
        self.assertEqual(self.rows('SELECT state FROM tasks WHERE id=1')[0][0], 'running')

    def test_a_task_that_is_not_claimed_is_refused(self):
        for state in ('pending', 'finished', 'failed'):
            with self.subTest(state=state):
                with closing(self.connection()) as db:
                    db.execute("DELETE FROM tasks")
                    db.execute('''INSERT INTO tasks(id,type,payload_json,state,priority,retry_count)
                        VALUES (1,'caption','{}',?,110,0)''', (state,))
                    db.commit()
                with self.assertRaises(PlanRejected):
                    self.planned([1])

    def test_a_missing_task_is_refused(self):
        with self.assertRaises(PlanRejected):
            self.planned([1])

    def test_an_unregistered_operator_is_refused(self):
        self.seed_claim()
        with self.assertRaises(PlanRejected):
            self.planned([1], operator=self.member_id)

    def test_a_plan_cannot_be_applied_twice(self):
        self.seed_claim()
        envelope = self.planned([1])
        clear_abandoned_claim(envelope, review=self.review(envelope), clock=lambda: NOW)
        with self.assertRaises(PlanRejected):
            clear_abandoned_claim(envelope, review=self.review(envelope), clock=lambda: NOW)

    def test_the_plan_is_bound_to_its_reviewed_digest(self):
        from dataclasses import replace
        self.seed_claim()
        envelope = self.planned([1])
        with self.assertRaises(PlanRejected):
            clear_abandoned_claim(envelope, review=replace(self.review(envelope), plan_digest='0' * 64),
                                  clock=lambda: NOW)
        self.assertEqual(self.rows('SELECT state FROM tasks WHERE id=1')[0][0], 'running')

    def test_several_claims_are_requeued_together(self):
        for task_id in (1, 2, 3):
            self.seed_claim(task_id=task_id)
        envelope = self.planned([1, 2, 3])
        receipt = clear_abandoned_claim(envelope, review=self.review(envelope), clock=lambda: NOW)
        self.assertEqual(len(receipt['requeued']), 3)
        self.assertEqual([row[0] for row in self.rows('SELECT state FROM tasks ORDER BY id')],
                         ['pending'] * 3)

    def test_age_is_measured_in_utc_not_local_time(self):
        """The mistake that produced a false stall diagnosis must not be repeated here."""
        # A claim stamped now in UTC reads as ~0 seconds old, whatever the host offset is.
        self.seed_claim(age_seconds=0)
        stored = self.rows('SELECT started_at FROM tasks WHERE id=1')[0][0]
        age = claim_age_seconds(stored)
        self.assertLess(abs(age), 30, f'expected a fresh claim, got {age}s')
        # And one stamped an hour ago reads as an hour, not an hour plus the offset.
        self.seed_claim(task_id=2, age_seconds=3600)
        stored = self.rows('SELECT started_at FROM tasks WHERE id=2')[0][0]
        self.assertLess(abs(claim_age_seconds(stored) - 3600), 30)

    def test_an_unreadable_start_time_is_refused(self):
        with closing(self.connection()) as db:
            db.execute('''INSERT INTO tasks(id,type,payload_json,state,priority,retry_count,started_at)
                VALUES (1,'caption','{}','running',110,0,'not-a-time')''')
            db.commit()
        with self.assertRaises(PlanRejected):
            self.planned([1])


class ClaimRecoveryCliTests(ClaimRecoveryTests):
    """The same recovery, driven through the operator tool."""

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

    def call(self, command, *args):
        output, error = self.io.StringIO(), self.io.StringIO()
        with self.redirect[0](output), self.redirect[1](error):
            code = self.cli.main([command, '--database', str(self.path), *map(str, args)],
                                 clock=lambda: NOW)
        return code, (json.loads(output.getvalue()) if output.getvalue() else None), error.getvalue()

    def test_plan_then_apply_claim_recovery(self):
        self.seed_claim()
        self.request.write_text(json.dumps({'operator_account_id': self.owner_id,
            'task_ids': [1], 'quiescence_reference': 'quiescent-0001'}))
        code, planned, error = self.call('plan-clear-claim', '--request', self.request,
                                         '--out', self.plan)
        self.assertEqual((code, error), (0, ''))
        self.assertEqual(planned['operation'], OPERATION)
        code, validated, error = self.call('validate-claim-recovery', '--plan', self.plan)
        self.assertEqual((code, error), (0, ''))
        self.assertTrue(validated['valid'])
        code, applied, error = self.call('apply-claim-recovery', '--plan', self.plan,
            '--reviewed-plan-digest', planned['plan_digest'],
            '--authority-reference', 'ticket-0001',
            '--quiescence-reference', 'quiescent-0001')
        self.assertEqual((code, error), (0, ''))
        self.assertTrue(applied['applied'])
        self.assertEqual(self.rows('SELECT state FROM tasks WHERE id=1')[0][0], 'pending')

    def test_apply_requires_the_matching_quiescence_reference(self):
        """A plan reviewed under one quiescence claim must not be applied under another."""
        self.seed_claim()
        self.request.write_text(json.dumps({'operator_account_id': self.owner_id,
            'task_ids': [1], 'quiescence_reference': 'quiescent-0001'}))
        code, planned, _error = self.call('plan-clear-claim', '--request', self.request,
                                          '--out', self.plan)
        self.assertEqual(code, 0)
        code, _result, error = self.call('apply-claim-recovery', '--plan', self.plan,
            '--reviewed-plan-digest', planned['plan_digest'],
            '--authority-reference', 'ticket-0001',
            '--quiescence-reference', 'a-different-claim')
        self.assertEqual(code, 2)
        self.assertTrue(error.startswith('Operator command refused'), error)
        self.assertEqual(self.rows('SELECT state FROM tasks WHERE id=1')[0][0], 'running')

    def test_plan_clear_claim_refuses_a_live_claim(self):
        self.seed_claim(age_seconds=MIN_CLAIM_AGE_SECONDS - 60)
        self.request.write_text(json.dumps({'operator_account_id': self.owner_id,
            'task_ids': [1], 'quiescence_reference': 'quiescent-0001'}))
        code, _result, error = self.call('plan-clear-claim', '--request', self.request,
                                         '--out', self.plan)
        self.assertEqual(code, 2)
        self.assertTrue(error.startswith('Operator command refused'), error)
