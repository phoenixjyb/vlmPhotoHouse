"""Reviewed offline quarantine of an already restored database; no restore or reopen.

Local callers independently establish authority and stop all workers before use.
A reference records those external decisions; it does not verify or replace them.
"""
import json
import secrets
import sqlite3
import time

from .provisioning import PlanRejected, _PlanState, _json
from .provisioning_apply import (ApplyReview, _identity, _reference, _review_backup,
                                 _snapshot, plan_digest)
from .runtime import ExistingDatabase

OPERATION = 'quarantine_restored_access'


def _assert_quarantined(db, expected_key):
    """Check the access barrier, including trigger-induced changes, before commit."""
    if db.execute('SELECT secret FROM access_admission_key WHERE id=1').fetchone() != (expected_key,):
        raise PlanRejected('Recovery key replacement failed')
    for query in (
        "SELECT 1 FROM access_accounts WHERE state != 'disabled'",
        "SELECT 1 FROM access_libraries WHERE state != 'closed'",
        'SELECT 1 FROM access_sessions WHERE revoked != 1',
        'SELECT 1 FROM access_invitations WHERE cancelled=0 AND consumed=0',
        'SELECT 1 FROM access_attempts',
        'SELECT 1 FROM access_kdf_slot',
    ):
        if db.execute(query).fetchone() is not None:
            raise PlanRejected('Access quarantine incomplete')


def _quarantine_access_state(db):
    """Shared mutation, never an authorization entry point; caller owns transaction.

    Call only after offline authority/quiescence review, or on an owned in-memory
    candidate. No account is invented for pre-access databases. Nothing is reopened.
    """
    if not db.in_transaction:
        raise PlanRejected('Explicit quarantine transaction required')
    # Fresh random material must not repeat on restore/rollback.
    old_key = db.execute('SELECT secret FROM access_admission_key WHERE id=1').fetchone()[0]
    key = secrets.token_bytes(32)
    if not isinstance(key, bytes) or len(key) != 32 or key == old_key:
        raise PlanRejected('Fresh recovery key unavailable')
    db.execute("UPDATE access_accounts SET state='disabled' WHERE state='active'")
    db.execute("UPDATE access_libraries SET state='closed' WHERE state='active'")
    db.execute('UPDATE access_sessions SET revoked=1 WHERE revoked=0')
    db.execute('UPDATE access_invitations SET cancelled=1 WHERE cancelled=0 AND consumed=0')
    db.execute('UPDATE access_admission_key SET secret=? WHERE id=1', (key,))
    db.execute('DELETE FROM access_attempts')
    db.execute('DELETE FROM access_kdf_slot')
    _assert_quarantined(db, key)
    return key


class _RecoveryState(_PlanState):
    def _state(self, operation, target):
        if operation != OPERATION or not isinstance(target, dict) or set(target) != {'operator_account_id', 'quiescence_reference'}:
            raise PlanRejected('Invalid recovery plan')
        _reference(target['quiescence_reference'])
        actor = target['operator_account_id']
        if not isinstance(actor, str) or len(actor) != 36:
            raise PlanRejected('Explicit recorded operator required')
        db = self.access.db
        # This is attribution to an existing record, not authentication via restored
        # credentials. Disabled operators may need to quarantine a second restore.
        if not db.execute('SELECT account_id FROM access_operators WHERE account_id=?', (actor,)).fetchone():
            raise PlanRejected('Explicit recorded operator required')
        return {
            'snapshot_digest': _snapshot(db),
            'accounts_to_disable': db.execute("SELECT count(*) FROM access_accounts WHERE state='active'").fetchone()[0],
            'libraries_to_close': db.execute("SELECT count(*) FROM access_libraries WHERE state='active'").fetchone()[0],
            'sessions_to_revoke': db.execute('SELECT count(*) FROM access_sessions WHERE revoked=0').fetchone()[0],
            'invitations_to_cancel': db.execute('SELECT count(*) FROM access_invitations WHERE cancelled=0 AND consumed=0').fetchone()[0],
            'admission_buckets_to_clear': db.execute('SELECT count(*) FROM access_attempts').fetchone()[0],
            'kdf_claims_to_clear': db.execute('SELECT count(*) FROM access_kdf_slot').fetchone()[0],
            'plan_key_replaced': True, 'passwords_changed': False,
            'memberships_and_asset_mappings_preserved': True, 'access_reopened': False,
        }


class RecoveryPlanner(_RecoveryState):
    def __init__(self, connection, *, clock=time.time):
        super().__init__(connection, clock=clock)
        if connection.execute('PRAGMA query_only').fetchone()[0] != 1:
            raise PlanRejected('Recovery planning requires a read-only connection')

    def quarantine(self, *, operator_account_id, quiescence_reference):
        return self._plan(OPERATION, {'operator_account_id': operator_account_id,
                                     'quiescence_reference': _reference(quiescence_reference)})

    def validate(self, envelope):
        with self.access._transaction():
            return self._validate_in_transaction(envelope)


def review_recovery_backup(*, database, backup, envelope, reviewed_plan_digest,
                           authority_reference, restore_reference, clock=time.time):
    return _review_backup(database=database, backup=backup, envelope=envelope,
        reviewed_plan_digest=reviewed_plan_digest, authority_reference=authority_reference,
        restore_reference=restore_reference, clock=clock, state_type=_RecoveryState)


def quarantine_restored_access(envelope, *, review, clock=time.time):
    """Invalidate restored credentials/artifacts and leave every library closed.

    Only a stopped, explicitly selected, already migrated/restored database is in
    scope. This function cannot stop workers, copy backups, restore lost records,
    reconstruct post-backup revocations, reset passwords or enable any account.
    """
    if type(review) is not ApplyReview or plan_digest(envelope) != review.plan_digest:
        raise PlanRejected('Exact local recovery review required')
    envelope = json.loads(_json(envelope))
    if plan_digest(envelope) != review.plan_digest:
        raise PlanRejected('Plan changed during review')
    _reference(review.authority_reference)
    _reference(review.restore_reference)
    try:
        with ExistingDatabase(review.database)() as db:
            state = _RecoveryState(db, clock=clock)
            with state.access._transaction(write=True):
                if _identity(review.database) != review.database_identity or _identity(review.backup) != review.backup_identity:
                    raise PlanRejected('Recovery target changed')
                state._validate_in_transaction(envelope)
                plan = envelope['plan']
                if db.execute('SELECT 1 FROM access_provisioning_receipts WHERE plan_id=? OR plan_digest=?',
                              (plan['plan_id'], review.plan_digest)).fetchone():
                    raise PlanRejected('Recovery already applied')
                if _snapshot(db) != review.snapshot_digest:
                    raise PlanRejected('Recovery database changed; review again')
                with ExistingDatabase(review.backup, read_only=True)() as backup:
                    backup.execute('BEGIN')
                    if _snapshot(backup) != review.snapshot_digest:
                        raise PlanRejected('Recovery backup changed')
                state._validate_in_transaction(envelope)
                if not plan['created_at'] <= state.access._now() < plan['expires_at']:
                    raise PlanRejected('Recovery plan expired')
                key = _quarantine_access_state(db)
                receipt = {
                    'version': 1, 'operation': OPERATION, 'plan_id': plan['plan_id'],
                    'plan_digest': review.plan_digest, 'applied_at': state.access._now(),
                    'actor_account_id': plan['target']['operator_account_id'],
                    'authority_reference': review.authority_reference,
                    'restore_reference': review.restore_reference,
                    'quiescence_reference': plan['target']['quiescence_reference'],
                    'database_identity': list(review.database_identity),
                    'backup_snapshot_digest': review.snapshot_digest,
                    'reviewed_state': plan['expected'], 'access_reopened': False,
                }
                db.execute('INSERT INTO access_provisioning_receipts VALUES (?,?,?)',
                           (plan['plan_id'], review.plan_digest, _json(receipt).decode()))
                state.access._audit(plan['target']['operator_account_id'], 'offline.' + OPERATION, None, None)
                _assert_quarantined(db, key)
                if _identity(review.database) != review.database_identity or _identity(review.backup) != review.backup_identity:
                    raise PlanRejected('Recovery target changed')
                if not plan['created_at'] <= state.access._now() < plan['expires_at']:
                    raise PlanRejected('Recovery plan expired during application')
            return receipt
    except sqlite3.Error:
        raise PlanRejected('Offline recovery failed; no partial operation committed') from None
