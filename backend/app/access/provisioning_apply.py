"""Offline, explicitly reviewed application. Never register with the web runtime.

The caller must already have independent local database authority. Review references
record that external decision; they are not credentials or an authorization system.
"""
from contextlib import closing, contextmanager
from dataclasses import dataclass
import getpass
import hashlib
import hmac
import json
import os
import shutil
from pathlib import Path
import re
import sqlite3
import stat
import time
import uuid
import warnings

from .credentials import hash_password, verify_password
from .provisioning import PlanRejected, _PlanState, _json
from .runtime import ExistingDatabase


def plan_digest(envelope):
    try:
        encoded = _json(envelope)
        if len(encoded) > 2_000_000:
            raise PlanRejected('Invalid plan')
        return hashlib.sha256(encoded).hexdigest()
    except (TypeError, ValueError, RecursionError, UnicodeError):
        raise PlanRejected('Invalid plan') from None


def _identity(path):
    if not isinstance(path, Path) or not path.is_absolute():
        raise PlanRejected('Explicit absolute target required')
    value = path.lstat()
    if not stat.S_ISREG(value.st_mode) or path.resolve(strict=True) != path:
        raise PlanRejected('Direct regular database file required')
    return value.st_dev, value.st_ino


def _snapshot(db):
    """Hash SQLite's logical dump in memory; never emit rows, hashes or paths."""
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone():
        raise PlanRejected('Database integrity review required')
    digest = hashlib.sha256()
    for statement in db.iterdump():
        digest.update(statement.encode('utf-8'))
        digest.update(b'\n')
    return digest.hexdigest()


def _reference(value):
    # Opaque ticket IDs only: never paste a secret, phone, path or narrative here.
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,80}', value):
        raise PlanRejected('Explicit authority and restore review references required')
    return value


@dataclass(frozen=True)
class ApplyReview:
    database: Path
    database_identity: tuple[int, int]
    backup: Path
    backup_identity: tuple[int, int]
    snapshot_digest: str
    plan_digest: str
    authority_reference: str
    restore_reference: str


def review_backup(*, database, backup, envelope, reviewed_plan_digest,
                  authority_reference, restore_reference, clock=time.time, restore_out=None):
    """Verify a separate backup and restore in memory or a fresh explicit disk file.

    The references attest to independently reviewed authority and the operational
    restore procedure. This rehearsal verifies SQLite content, not disaster recovery.
    Returns a local in-process review; do not deserialize reviews from untrusted input.
    """
    return _review_backup(database=database, backup=backup, envelope=envelope,
        reviewed_plan_digest=reviewed_plan_digest, authority_reference=authority_reference,
        restore_reference=restore_reference, clock=clock, state_type=_PlanState,
        restore_out=restore_out)


@contextmanager
def _restore_target(path, source):
    """An explicit fresh disk copy, or the unchanged small-database memory path.

    Disk output is private operator evidence, retained even on failure. The caller
    owns host ACLs and resource supervision. Never accept an existing scratch file.
    """
    if path is None:
        with closing(sqlite3.connect(':memory:')) as db:
            yield db
        return
    if (not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts
            or path.anchor.startswith(('//', '\\\\')) or path.parent.resolve(strict=True) != path.parent
            or any(os.path.lexists(str(path)+suffix) for suffix in ('-wal', '-shm', '-journal'))):
        raise PlanRejected('Explicit new private restore path required')
    size = source.execute('PRAGMA page_count').fetchone()[0] * source.execute('PRAGMA page_size').fetchone()[0]
    if size > 2 * 1024**3 or shutil.disk_usage(path.parent).free < 2 * size + 256 * 1024**2:
        raise PlanRejected('Disk restore resource review required')
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(path, flags, 0o600), 'r+b') as reserved:
        identity = _identity(path)
        with closing(sqlite3.connect(path.as_uri()+'?mode=rw', uri=True, timeout=3)) as db:
            db.execute('PRAGMA cache_size=-8192'); db.execute('PRAGMA temp_store=FILE')
            db.execute('PRAGMA mmap_size=0'); db.execute('PRAGMA synchronous=FULL')
            yield db
        os.fsync(reserved.fileno())
        if _identity(path) != identity:
            raise PlanRejected('Disk restore identity changed')


def _offline_restore_source(path, db):
    if (any(os.path.lexists(str(path)+suffix) for suffix in ('-wal', '-shm', '-journal'))
            or db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete'):
        raise PlanRejected('Disk review requires offline rollback-journal inputs')
    size = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
    if size > 2 * 1024**3:
        raise PlanRejected('Disk review size budget exceeded')


def _review_backup(*, database, backup, envelope, reviewed_plan_digest,
                   authority_reference, restore_reference, clock, state_type, restore_out=None):
    """Shared internal backup verification; public callers fix the plan validator."""
    authority_reference = _reference(authority_reference)
    restore_reference = _reference(restore_reference)
    digest = plan_digest(envelope)
    envelope = json.loads(_json(envelope))
    if plan_digest(envelope) != digest:
        raise PlanRejected('Plan changed during review')
    if not isinstance(reviewed_plan_digest, str) or not hmac.compare_digest(digest, reviewed_plan_digest):
        raise PlanRejected('Exact reviewed plan digest required')
    target_id, backup_id = _identity(database), _identity(backup)
    if target_id == backup_id:
        raise PlanRejected('A separate backup is required')
    with ExistingDatabase(database, read_only=True)() as db:
        if restore_out is not None or envelope['plan']['operation'] in ('import_management_ownership', 'enqueue_face_assignment'):
            _offline_restore_source(database, db)
        state = state_type(db, clock=clock)
        with state.access._transaction():
            state._validate_in_transaction(envelope)
            snapshot = _snapshot(db)
    with ExistingDatabase(backup, read_only=True)() as source:
        if restore_out is not None or envelope['plan']['operation'] in ('import_management_ownership', 'enqueue_face_assignment'):
            _offline_restore_source(backup, source)
        source.execute('BEGIN')
        with _restore_target(restore_out, source) as restored:
            source.backup(restored)
            if _snapshot(source) != snapshot or _snapshot(restored) != snapshot:
                raise PlanRejected('Backup does not match the reviewed database')
    if _identity(database) != target_id or _identity(backup) != backup_id:
        raise PlanRejected('Database target changed')
    return ApplyReview(database, target_id, backup, backup_id, snapshot, digest,
                       authority_reference, restore_reference)


def _owner_password():
    # getpass otherwise warns and silently falls back to echoed stdin.
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        first = getpass.getpass('New owner password: ')
        second = getpass.getpass('Confirm new owner password: ')
    if first != second:
        raise PlanRejected('Password confirmation failed')
    return hash_password(first)


def apply_reviewed(envelope, *, review, clock=time.time, all_writers_stopped=False):
    """Apply exactly one plan and receipt in one BEGIN IMMEDIATE transaction.

    No password argument, settings discovery, HTTP endpoint, backup creation or
    schema repair. Local administrators and filesystem writers remain trusted.
    """
    if type(review) is not ApplyReview or plan_digest(envelope) != review.plan_digest:
        raise PlanRejected('Exact local review required')
    _reference(review.authority_reference)
    _reference(review.restore_reference)
    # Detach caller-owned containers before any prompt or wait.
    envelope = json.loads(_json(envelope))
    management = envelope['plan']['operation']=='import_management_ownership'
    face_job = envelope['plan']['operation']=='enqueue_face_assignment'
    offline = management or face_job
    if offline and all_writers_stopped is not True:
        raise PlanRejected('Independent all-writer shutdown confirmation required')
    if plan_digest(envelope) != review.plan_digest:
        raise PlanRejected('Plan changed during review')
    if _identity(review.database) != review.database_identity or _identity(review.backup) != review.backup_identity:
        raise PlanRejected('Database target changed')
    # Preflight before prompting; this result is deliberately not trusted for writes.
    with ExistingDatabase(review.database, read_only=True)() as db:
        if offline: _offline_restore_source(review.database, db)
        state = _PlanState(db, clock=clock)
        with state.access._transaction():
            state._validate_in_transaction(envelope)
            if face_job:
                owner_hash = db.execute('SELECT password_hash FROM access_accounts WHERE id=?',
                    (envelope['plan']['target']['operator_account_id'],)).fetchone()[0]
    encoded = _owner_password() if envelope['plan']['operation'] == 'bootstrap_owner' else None
    if face_job:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('Existing owner password: ')
        authenticated = verify_password(password, owner_hash)
        del password
        if not authenticated:
            raise PlanRejected('Owner authentication failed')
    try:
        with ExistingDatabase(review.database)() as db:
            if offline: _offline_restore_source(review.database, db)
            state = _PlanState(db, clock=clock)
            with state.access._transaction(write=True):
                if _identity(review.database) != review.database_identity or _identity(review.backup) != review.backup_identity:
                    raise PlanRejected('Database target changed')
                plan = envelope['plan']
                if db.execute('SELECT 1 FROM access_provisioning_receipts WHERE plan_id=? OR plan_digest=?',
                              (plan['plan_id'], review.plan_digest)).fetchone():
                    raise PlanRejected('Plan already applied')
                state._validate_in_transaction(envelope)
                if _snapshot(db) != review.snapshot_digest:
                    raise PlanRejected('Database changed; review a fresh backup')
                with ExistingDatabase(review.backup, read_only=True)() as backup:
                    if offline: _offline_restore_source(review.backup, backup)
                    backup.execute('BEGIN')
                    if _snapshot(backup) != review.snapshot_digest:
                        raise PlanRejected('Reviewed backup changed')
                # Snapshot scans can be slow: expiry/audience time may have changed
                # even though the writer reservation prevents database mutations.
                state._validate_in_transaction(envelope)
                target = plan['target']
                library = target['library_id']
                if encoded is not None:
                    actor = str(uuid.uuid4())
                    db.execute('INSERT INTO access_accounts(id,phone_login,password_hash) VALUES (?,?,?)',
                               (actor, target['phone_login'], encoded))
                    db.execute('INSERT INTO access_operators(account_id) VALUES (?)', (actor,))
                    db.execute('INSERT INTO access_libraries(id,bootstrap_operator) VALUES (?,?)', (library, actor))
                    db.execute('''INSERT INTO access_memberships(account_id,library_id,status,role,revision,approved_by)
                        VALUES (?,?,'approved','owner',1,?)''', (actor, library, actor))
                    asset_ids = []
                else:
                    actor = target['operator_account_id']
                    asset_ids = [] if offline else target['asset_ids']
                    if face_job:
                        from .face_jobs import enqueue
                        task_id = enqueue(state, target)
                    elif management:
                        from .management_import import apply_management
                        apply_management(state,target)
                    else:
                        db.executemany('INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (?,?)',
                                       ((int(item), library) for item in asset_ids))
                receipt = {'version': 1, 'plan_id': plan['plan_id'], 'plan_digest': review.plan_digest,
                           'operation': plan['operation'], 'actor_account_id': actor,
                           'library_id': library, 'asset_ids': asset_ids, 'applied_at': state.access._now(),
                           'authority_reference': review.authority_reference,
                           'restore_reference': review.restore_reference,
                           'backup_snapshot_digest': review.snapshot_digest,
                           'database_identity': list(review.database_identity),
                           'reviewed_state': plan['expected'], 'originals_granted': False}
                if management:
                    receipt.update(person_ids=target['person_ids'],album_ids=target['album_ids'],
                                   quiescence_reference=target['quiescence_reference'])
                if face_job:
                    from .face_jobs import seal_receipt
                    seal_receipt(state, receipt, envelope, task_id)
                db.execute('INSERT INTO access_provisioning_receipts VALUES (?,?,?)',
                           (plan['plan_id'], review.plan_digest, _json(receipt).decode()))
                state.access._audit(actor, 'offline.' + plan['operation'], library,
                                    actor if encoded is not None else None)
                if management:
                    from .management_import import management_state
                    if management_state(state,target,imported=True)!=plan['expected']:
                        raise PlanRejected('Imported ownership or reviewed state changed')
                if face_job:
                    from .face_jobs import verify_queued
                    verify_queued(state, plan_id=plan['plan_id'], digest=review.plan_digest,
                                  task_id=task_id, database_identity=review.database_identity)
                if _identity(review.database) != review.database_identity or _identity(review.backup) != review.backup_identity:
                    raise PlanRejected('Database target changed')
                if not plan['created_at'] <= state.access._now() < plan['expires_at']:
                    raise PlanRejected('Plan expired during application')
            return receipt
    except sqlite3.Error:
        raise PlanRejected('Offline apply failed; no partial operation committed') from None
