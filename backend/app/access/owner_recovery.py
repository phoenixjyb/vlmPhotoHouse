"""Offline first-owner recovery of a quarantined library; never mount on HTTP.

The local operator independently verifies identity, post-backup history and stopped
workers. References record those reviews, not authentication or proof of quiescence.
"""
import getpass
import json
import sqlite3
import time
import uuid
import warnings

from .credentials import hash_password, verify_password
from .provisioning import PlanRejected, _PlanState, _json, _library
from .provisioning_apply import ApplyReview, _identity, _reference, _review_backup, _snapshot, plan_digest
from .recovery import _assert_quarantined, _quarantine_access_state
from .runtime import ExistingDatabase

OPERATION = 'recover_one_owner_library'


class _OwnerRecoveryState(_PlanState):
    def _state(self, operation, target):
        if operation != OPERATION or type(target) is not dict or set(target) != {
                'operator_account_id', 'library_id', 'quiescence_reference', 'reconciliation_reference'}:
            raise PlanRejected('Invalid owner recovery plan')
        actor = target['operator_account_id']
        try:
            if not isinstance(actor, str) or str(uuid.UUID(actor)) != actor:
                raise ValueError
        except ValueError:
            raise PlanRejected('Explicit recorded owner required') from None
        library = _library(target['library_id'])
        _reference(target['quiescence_reference'])
        _reference(target['reconciliation_reference'])
        db = self.access.db
        key = db.execute('SELECT secret FROM access_admission_key WHERE id=1').fetchone()[0]
        _assert_quarantined(db, key)
        # No promotion of a viewer/revoked owner or alternate bootstrap identity.
        owner = db.execute('''SELECT m.revision FROM access_memberships m
            JOIN access_accounts a ON a.id=m.account_id
            JOIN access_operators o ON o.account_id=m.account_id
            JOIN access_libraries l ON l.id=m.library_id
            WHERE m.account_id=? AND m.library_id=? AND l.bootstrap_operator=?
            AND m.status='approved' AND m.role='owner' AND m.expires_at IS NULL''',
            (actor, library, actor)).fetchone()
        if owner is None:
            raise PlanRejected('Recorded nonexpiring bootstrap owner required')
        if db.execute("SELECT 1 FROM access_memberships WHERE typeof(revision)!='integer' OR revision>=?", (2**63-1,)).fetchone():
            raise PlanRejected('Membership revision cannot advance')
        return {
            'snapshot_digest': _snapshot(db), 'owner_revision': owner[0],
            'memberships_to_revoke': db.execute('SELECT count(*) FROM access_memberships').fetchone()[0]-1,
            'original_grants_to_remove': db.execute('SELECT count(*) FROM access_memberships WHERE originals=1').fetchone()[0],
            'selected_library_mapped_assets': db.execute('SELECT count(*) FROM access_asset_libraries WHERE library_id=?', (library,)).fetchone()[0],
            'accounts_to_enable': 1, 'libraries_to_open': 1, 'password_replaced': True,
            'sessions_created': 0, 'originals_granted': False,
            'other_accounts_remain_disabled': True, 'other_libraries_remain_closed': True,
        }


class OwnerRecoveryPlanner(_OwnerRecoveryState):
    def __init__(self, connection, *, clock=time.time):
        super().__init__(connection, clock=clock)
        if connection.execute('PRAGMA query_only').fetchone()[0] != 1:
            raise PlanRejected('Owner recovery planning requires read-only connection')

    def recover(self, *, operator_account_id, library_id, quiescence_reference, reconciliation_reference):
        return self._plan(OPERATION, dict(operator_account_id=operator_account_id,
            library_id=library_id, quiescence_reference=quiescence_reference,
            reconciliation_reference=reconciliation_reference))

    def validate(self, envelope):
        with self.access._transaction():
            return self._validate_in_transaction(envelope)


def review_owner_recovery_backup(*, database, backup, envelope, reviewed_plan_digest,
                                authority_reference, restore_reference, clock=time.time):
    return _review_backup(database=database, backup=backup, envelope=envelope,
        reviewed_plan_digest=reviewed_plan_digest, authority_reference=authority_reference,
        restore_reference=restore_reference, clock=clock, state_type=_OwnerRecoveryState)


def _replacement_password(old_hash):
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        first = getpass.getpass('New recovered owner password: ')
        second = getpass.getpass('Confirm new recovered owner password: ')
    if first != second:
        raise PlanRejected('Password confirmation failed')
    encoded = hash_password(first)
    if verify_password(first, old_hash):
        raise PlanRejected('A different owner password is required')
    return encoded


def _assert_reopened(db, actor, library, encoded, key, revision):
    if (db.execute("SELECT id FROM access_accounts WHERE state='active'").fetchall() != [(actor,)]
            or db.execute("SELECT id FROM access_libraries WHERE state='active'").fetchall() != [(library,)]
            or db.execute('SELECT password_hash FROM access_accounts WHERE id=?', (actor,)).fetchone() != (encoded,)
            or db.execute('SELECT secret FROM access_admission_key WHERE id=1').fetchone() != (key,)
            or db.execute('''SELECT account_id,library_id,status,role,revision,expires_at,originals,approved_by
                FROM access_memberships WHERE status!='revoked' ''').fetchall() != [
                    (actor, library, 'approved', 'owner', revision, None, 0, actor)]):
        raise PlanRejected('Owner recovery barrier failed')
    for query in ('SELECT 1 FROM access_memberships WHERE originals!=0',
                  'SELECT 1 FROM access_sessions WHERE revoked!=1',
                  'SELECT 1 FROM access_invitations WHERE consumed=0 AND cancelled=0',
                  'SELECT 1 FROM access_attempts', 'SELECT 1 FROM access_kdf_slot'):
        if db.execute(query).fetchone():
            raise PlanRejected('Restored access remains usable')


def recover_owner_library(envelope, *, review, clock=time.time):
    """Recover exactly one owner/library and revoke every other restored membership.

    Protected password entry and sequential KDF work occur before the write lock.
    Revalidate the sealed plan, full snapshot, identities and backup afterward.
    No other account recovery, audience import, originals, login session or cutover.
    """
    if type(review) is not ApplyReview or plan_digest(envelope) != review.plan_digest:
        raise PlanRejected('Exact owner recovery review required')
    envelope = json.loads(_json(envelope))
    if plan_digest(envelope) != review.plan_digest:
        raise PlanRejected('Recovery plan changed')
    _reference(review.authority_reference); _reference(review.restore_reference)
    if _identity(review.database) != review.database_identity or _identity(review.backup) != review.backup_identity:
        raise PlanRejected('Recovery target changed')
    with ExistingDatabase(review.database, read_only=True)() as db:
        state = _OwnerRecoveryState(db, clock=clock)
        with state.access._transaction():
            state._validate_in_transaction(envelope)
            old_hash = db.execute('SELECT password_hash FROM access_accounts WHERE id=?',
                                 (envelope['plan']['target']['operator_account_id'],)).fetchone()[0]
    encoded = _replacement_password(old_hash)
    try:
        with ExistingDatabase(review.database)() as db:
            state = _OwnerRecoveryState(db, clock=clock)
            with state.access._transaction(write=True):
                if _identity(review.database) != review.database_identity or _identity(review.backup) != review.backup_identity:
                    raise PlanRejected('Recovery target changed')
                plan = envelope['plan']
                if db.execute('SELECT 1 FROM access_provisioning_receipts WHERE plan_id=? OR plan_digest=?',
                              (plan['plan_id'], review.plan_digest)).fetchone():
                    raise PlanRejected('Recovery already applied')
                state._validate_in_transaction(envelope)
                if _snapshot(db) != review.snapshot_digest:
                    raise PlanRejected('Recovery snapshot changed')
                with ExistingDatabase(review.backup, read_only=True)() as backup:
                    backup.execute('BEGIN')
                    if _snapshot(backup) != review.snapshot_digest:
                        raise PlanRejected('Recovery backup changed')
                state._validate_in_transaction(envelope)
                target = plan['target']; actor = target['operator_account_id']; library = target['library_id']
                key = _quarantine_access_state(db)
                # Do not trust restored audience or originals, even in closed libraries.
                db.execute("UPDATE access_memberships SET status='revoked',originals=0,revision=revision+1")
                db.execute("UPDATE access_memberships SET status='approved',approved_by=? WHERE account_id=? AND library_id=?",
                           (actor, actor, library))
                db.execute("UPDATE access_accounts SET password_hash=?,state='active' WHERE id=?", (encoded, actor))
                db.execute("UPDATE access_libraries SET state='active' WHERE id=?", (library,))
                receipt = {'version': 1, 'operation': OPERATION, 'plan_id': plan['plan_id'],
                    'plan_digest': review.plan_digest, 'actor_account_id': actor, 'library_id': library,
                    'applied_at': state.access._now(), 'authority_reference': review.authority_reference,
                    'restore_reference': review.restore_reference,
                    'quiescence_reference': target['quiescence_reference'],
                    'reconciliation_reference': target['reconciliation_reference'],
                    'database_identity': list(review.database_identity), 'backup_snapshot_digest': review.snapshot_digest,
                    'reviewed_state': plan['expected'], 'originals_granted': False, 'sessions_created': 0}
                db.execute('INSERT INTO access_provisioning_receipts VALUES (?,?,?)',
                           (plan['plan_id'], review.plan_digest, _json(receipt).decode()))
                state.access._audit(actor, 'offline.'+OPERATION, library, actor)
                _assert_reopened(db, actor, library, encoded, key, plan['expected']['owner_revision']+1)
                if _identity(review.database) != review.database_identity or _identity(review.backup) != review.backup_identity:
                    raise PlanRejected('Recovery target changed')
                if not plan['created_at'] <= state.access._now() < plan['expires_at']:
                    raise PlanRejected('Recovery expired during application')
            return receipt
    except sqlite3.Error:
        raise PlanRejected('Owner recovery failed; no partial operation committed') from None
