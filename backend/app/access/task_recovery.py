"""Offline recovery of an abandoned task claim; never mounted on HTTP.

A worker claims a task by moving it to `running`. If the process dies — the machine sleeping
mid-task is the case that prompted this — the claim is never released. That is not self-healing
by design: `admission.py` states *"No automatic stale-claim stealing: that would defeat the
memory cap"*, and the caption worker's `preflight` refuses to start while any caption task is
`running`. Each decision is right alone; together they stop the queue permanently.

This is the reviewed way out. An operator names the claims, the plan refuses anything that is not
genuinely abandoned, and the apply requeues them.

**Timestamps here are UTC.** Task rows are written with `datetime.utcnow()`, so an age computed
against local time is wrong by the host's offset — the exact mistake that produced a false
"8-hour stall" diagnosis on 2026-09-18.
"""
from dataclasses import dataclass
from datetime import datetime
import json
import sqlite3
import time
import uuid

from .provisioning import PlanRejected, _PlanState, _json
from .provisioning_apply import _identity, _reference, plan_digest
from .runtime import ExistingDatabase

OPERATION = 'clear_abandoned_task_claim'
MAX_TASKS = 100
# A claim younger than this is presumed live. Requeueing a slow task would steal work from a
# worker that is merely taking a while, so the operator has to wait out a real interval first.
MIN_CLAIM_AGE_SECONDS = 900
TASK_STATES = ('pending', 'running', 'finished', 'done', 'failed', 'dead')


@dataclass(frozen=True)
class ClaimRecoveryReview:
    """The operator's explicit review. No backup: this restores nothing."""

    database: object
    database_identity: tuple
    plan_digest: str
    authority_reference: str
    quiescence_reference: str


def claim_age_seconds(started_at):
    """Age of a claim, in seconds, from the naive-UTC string the worker wrote."""
    if not isinstance(started_at, str) or not started_at:
        return None
    try:
        moment = datetime.fromisoformat(started_at)
    except ValueError:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(tz=None).replace(tzinfo=None)
    return (datetime.utcnow() - moment).total_seconds()


class _ClaimRecoveryState(_PlanState):
    def _state(self, operation, target):
        if operation != OPERATION or type(target) is not dict or set(target) != {
                'operator_account_id', 'task_ids', 'quiescence_reference'}:
            raise PlanRejected('Invalid claim recovery plan')
        actor = target['operator_account_id']
        try:
            if not isinstance(actor, str) or str(uuid.UUID(actor)) != actor:
                raise ValueError
        except (ValueError, AttributeError):
            raise PlanRejected('Explicit operator account required') from None
        _reference(target['quiescence_reference'])
        db = self.access.db
        if db.execute("SELECT 1 FROM access_operators WHERE account_id=?", (actor,)).fetchone() is None:
            raise PlanRejected('Registered operator required')
        if db.execute("SELECT 1 FROM access_accounts WHERE id=? AND state='active'",
                      (actor,)).fetchone() is None:
            raise PlanRejected('Active operator account required')
        raw = target['task_ids']
        if (not isinstance(raw, list) or not 1 <= len(raw) <= MAX_TASKS
                or any(not isinstance(item, str) or not item.isascii() or not item.isdigit()
                       or item.startswith('0') or len(item) > 19 for item in raw)):
            raise PlanRejected('Select a bounded nonempty task list')
        values = [int(item) for item in raw]
        if values != sorted(set(values)) or any(value > 2 ** 63 - 1 for value in values):
            raise PlanRejected('Task selection must be sorted and unique')
        fingerprints = []
        for start in range(0, len(values), 100):
            chunk = values[start:start + 100]
            rows = db.execute('''SELECT id, type, state, started_at, retry_count, priority,
                    updated_at, finished_at FROM tasks WHERE id IN ('''
                + ','.join('?' for _ in chunk) + ') ORDER BY id', chunk).fetchall()
            if len(rows) != len(chunk):
                raise PlanRejected('Every selected task must exist')
            for row in rows:
                if row[2] != 'running':
                    raise PlanRejected('Only a claimed task can be recovered')
                age = claim_age_seconds(row[3])
                if age is None:
                    raise PlanRejected('Claim has no readable start time')
                if age < MIN_CLAIM_AGE_SECONDS:
                    raise PlanRejected('Claim is younger than the minimum abandonment age')
                fingerprints.append(list(row))
        return {'operator_verified': True, 'task_state': self._mac('abandoned-claim', fingerprints),
                'count': len(values), 'minimum_claim_age_seconds': MIN_CLAIM_AGE_SECONDS,
                'claims_are_abandoned': True, 'requeued_as_pending': True,
                'retry_count_incremented': True, 'media_writes': False}


class ClaimRecoveryPlanner(_ClaimRecoveryState):
    def __init__(self, connection, *, clock=time.time):
        super().__init__(connection, clock=clock)
        if connection.execute('PRAGMA query_only').fetchone()[0] != 1:
            raise PlanRejected('Claim recovery planning requires a read-only connection')

    def clear(self, *, operator_account_id, task_ids, quiescence_reference):
        if (not isinstance(task_ids, list) or not 1 <= len(task_ids) <= MAX_TASKS
                or any(type(item) is not int for item in task_ids)
                or len(set(task_ids)) != len(task_ids)):
            raise PlanRejected('Explicit unique integer task IDs required')
        return self._plan(OPERATION, {'operator_account_id': operator_account_id,
            'task_ids': [str(item) for item in sorted(task_ids)],
            'quiescence_reference': quiescence_reference})

    def validate(self, envelope):
        with self.access._transaction():
            return self._validate_in_transaction(envelope)


def clear_abandoned_claim(envelope, *, review, clock=time.time):
    """Requeue the named abandoned claims so a worker can pick them up again.

    `retry_count` is incremented, so a task that keeps being abandoned eventually reaches the
    existing failure handling instead of cycling forever. `started_at` is cleared because the
    next claim writes its own.
    """
    if type(review) is not ClaimRecoveryReview or plan_digest(envelope) != review.plan_digest:
        raise PlanRejected('Exact reviewed plan required')
    envelope = json.loads(_json(envelope))
    if plan_digest(envelope) != review.plan_digest:
        raise PlanRejected('Plan changed during review')
    if envelope['plan']['operation'] != OPERATION:
        raise PlanRejected('Exact reviewed plan required')
    _reference(review.authority_reference)
    _reference(review.quiescence_reference)
    # The operator must restate the same quiescence claim the plan was built on, so a plan
    # reviewed under one assumption cannot be applied under another.
    if review.quiescence_reference != envelope['plan']['target']['quiescence_reference']:
        raise PlanRejected('Quiescence reference must match the reviewed plan')
    if _identity(review.database) != review.database_identity:
        raise PlanRejected('Recovery target changed')
    try:
        with ExistingDatabase(review.database)() as db:
            state = _ClaimRecoveryState(db, clock=clock)
            with state.access._transaction(write=True):
                if _identity(review.database) != review.database_identity:
                    raise PlanRejected('Recovery target changed')
                plan = envelope['plan']
                if db.execute('SELECT 1 FROM access_provisioning_receipts WHERE plan_id=? OR plan_digest=?',
                              (plan['plan_id'], review.plan_digest)).fetchone():
                    raise PlanRejected('Plan already applied')
                state._validate_in_transaction(envelope)
                requeued = []
                for value in plan['target']['task_ids']:
                    task_id = int(value)
                    age = claim_age_seconds(db.execute('SELECT started_at FROM tasks WHERE id=?',
                                                       (task_id,)).fetchone()[0])
                    changed = db.execute("""UPDATE tasks SET state='pending', started_at=NULL,
                        retry_count=retry_count+1 WHERE id=? AND state='running'""",
                        (task_id,)).rowcount
                    if changed != 1:
                        raise PlanRejected('Claim changed during application')
                    requeued.append({'task_id': task_id,
                                     'abandoned_for_seconds': int(age) if age is not None else None})
                receipt = {'version': 1, 'operation': OPERATION, 'plan_id': plan['plan_id'],
                    'plan_digest': review.plan_digest, 'applied_at': state.access._now(),
                    'authority_reference': review.authority_reference,
                    'actor_account_id': plan['target']['operator_account_id'],
                    'database_identity': list(review.database_identity),
                    'quiescence_reference': plan['target']['quiescence_reference'],
                    'reviewed_state': plan['expected'], 'requeued': requeued,
                    'media_writes': False, 'originals_granted': False}
                db.execute('INSERT INTO access_provisioning_receipts VALUES (?,?,?)',
                           (plan['plan_id'], review.plan_digest, _json(receipt).decode()))
                state.access._audit(plan['target']['operator_account_id'], 'offline.' + OPERATION)
                if not plan['created_at'] <= state.access._now() < plan['expires_at']:
                    raise PlanRejected('Plan expired during application')
            return receipt
    except sqlite3.Error:
        raise PlanRejected('Claim recovery failed; no partial operation committed') from None
