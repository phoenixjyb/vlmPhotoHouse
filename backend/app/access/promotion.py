"""Offline promotion of member uploads into a library, and bounded reassignment.

Two operations, both sealed plans in the existing offline family and neither mounted on HTTP:

* **promote_and_assign** moves bytes out of the incoming area into the originals root and writes
  the library mapping. It is deliberately **one** operation: assigning without promoting would
  leave `assets.path` pointing outside `original_roots`, so the media route would refuse the
  photo — it would be *in* a library but unviewable.
* **reassign** corrects a wrong library. Because `asset_id` is the primary key of
  `access_asset_libraries`, a photo is in exactly one library, so this is an `UPDATE` rather than
  a second row. It is database-only; the bytes are already in the originals root.

Neither operation can run from the planner: `ProvisioningPlanner` and its siblings require a
read-only connection, and applying requires a write reservation.
"""
from dataclasses import dataclass
import errno
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import time
import uuid

from .provisioning import PlanRejected, _PlanState, _json, _library
from .provisioning_apply import _identity, _reference, plan_digest
from .runtime import ExistingDatabase

PROMOTE_OPERATION = 'promote_and_assign_uploads'
REASSIGN_OPERATION = 'reassign_library_assets'
MAX_ASSETS = 10000
# Promoted member photos are grouped so they stay traceable inside the originals root rather
# than scattered flat among the family's own folders.
PROMOTED_FOLDER = '_member_uploads'


@dataclass(frozen=True)
class PromotionReview:
    """The operator's explicit review of a promotion or reassignment.

    No backup is required because neither operation restores one; the plan is already bound to
    one database through the admission-key MAC, and this carries the identity check and the
    operator's own ticket reference.
    """

    database: Path
    database_identity: tuple
    plan_digest: str
    authority_reference: str
    incoming_root: Path = None
    originals_root: Path = None


def _directory(path, message):
    if not isinstance(path, Path) or not path.is_absolute() or not path.is_dir():
        raise PlanRejected(message)
    return path


def _operator(db, actor, library, now):
    """The actor must be a registered operator AND an approved owner of the library."""
    if not isinstance(actor, str):
        raise PlanRejected('Explicit operator account required')
    try:
        if str(uuid.UUID(actor)) != actor:
            raise ValueError
    except (ValueError, AttributeError):
        raise PlanRejected('Explicit operator account required') from None
    row = db.execute('''SELECT m.revision FROM access_memberships m
        JOIN access_accounts a ON a.id=m.account_id JOIN access_libraries l ON l.id=m.library_id
        JOIN access_operators o ON o.account_id=m.account_id
        WHERE m.account_id=? AND m.library_id=? AND m.role='owner' AND m.status='approved'
        AND a.state='active' AND l.state='active' AND (m.expires_at IS NULL OR m.expires_at>?)''',
        (actor, library, now)).fetchone()
    if row is None:
        raise PlanRejected('Selected operator and library owner required')
    return row[0]


def _audience(db, library, now):
    rows = db.execute('''SELECT m.account_id,m.status,m.role,m.revision,m.expires_at,m.originals,a.state
        FROM access_memberships m JOIN access_accounts a ON a.id=m.account_id
        WHERE m.library_id=? ORDER BY m.account_id''', (library,)).fetchall()
    current = [member for member in rows if member[1] == 'approved' and member[6] == 'active'
               and (member[4] is None or member[4] > now)]
    return rows, current


def _ids(target):
    raw = target['asset_ids']
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_ASSETS:
        raise PlanRejected('Select a bounded nonempty asset list')
    if any(not isinstance(item, str) or not item.isascii() or not item.isdigit()
           or item.startswith('0') or len(item) > 19 for item in raw):
        raise PlanRejected('Invalid asset selection')
    values = [int(item) for item in raw]
    if values != sorted(set(values)) or any(value > 2 ** 63 - 1 for value in values):
        raise PlanRejected('Asset selection must be sorted and unique')
    return values


class _PromotionState(_PlanState):
    def _state(self, operation, target):
        if type(target) is not dict:
            raise PlanRejected('Invalid plan')
        if operation == PROMOTE_OPERATION:
            return self._promote_state(target)
        if operation == REASSIGN_OPERATION:
            return self._reassign_state(target)
        raise PlanRejected('Invalid plan')

    def _promote_state(self, target):
        if set(target) != {'library_id', 'operator_account_id', 'asset_ids'}:
            raise PlanRejected('Invalid plan')
        db = self.access.db
        now = self.access._now()
        library = _library(target['library_id'])
        actor = target['operator_account_id']
        revision = _operator(db, actor, library, now)
        values = _ids(target)
        fingerprints = []
        total = 0
        for start in range(0, len(values), 500):
            chunk = values[start:start + 500]
            rows = db.execute('''SELECT a.id,a.path,a.hash_sha256,a.status,a.file_size,
                    u.account_id,u.incoming_label,u.batch,u.sha256,u.bytes,u.state,m.library_id
                FROM assets a JOIN access_uploads u ON u.asset_id=a.id
                LEFT JOIN access_asset_libraries m ON m.asset_id=a.id
                WHERE a.id IN (''' + ','.join('?' for _ in chunk) + ') ORDER BY a.id', chunk).fetchall()
            if len(rows) != len(chunk):
                raise PlanRejected('Every selected asset must have upload provenance')
            for row in rows:
                # Unmapped, active, still incoming, and the provenance must agree with the asset.
                if (row[3] not in (None, 'active') or row[10] != 'incoming' or row[11] is not None
                        or row[2] != row[8] or row[4] != row[9]):
                    raise PlanRejected('Only unassigned incoming uploads can be promoted')
                fingerprints.append(list(row[:11]))
                total += row[9]
        audience, current = _audience(db, library, now)
        return {'operator_revision': str(revision), 'asset_state': self._mac('upload-promotion', fingerprints),
                'count': len(values), 'bytes_to_promote': total,
                'audience_state': self._mac('library-audience', audience), 'current_readers': len(current),
                'current_original_readers': sum(bool(member[5]) for member in current),
                'originals_granted': False, 'media_writes': True, 'moves_between_libraries': False}

    def _reassign_state(self, target):
        if set(target) != {'library_id', 'operator_account_id', 'asset_ids'}:
            raise PlanRejected('Invalid plan')
        db = self.access.db
        now = self.access._now()
        library = _library(target['library_id'])
        actor = target['operator_account_id']
        revision = _operator(db, actor, library, now)
        values = _ids(target)
        fingerprints = []
        sources = set()
        for start in range(0, len(values), 500):
            chunk = values[start:start + 500]
            rows = db.execute('''SELECT a.id,a.path,a.hash_sha256,a.status,m.library_id
                FROM assets a JOIN access_asset_libraries m ON m.asset_id=a.id
                WHERE a.id IN (''' + ','.join('?' for _ in chunk) + ') ORDER BY a.id', chunk).fetchall()
            if len(rows) != len(chunk):
                raise PlanRejected('Every selected asset must currently belong to a library')
            for row in rows:
                if row[3] not in (None, 'active') or row[4] == library:
                    raise PlanRejected('Select assets that currently belong to another library')
                sources.add(row[4])
                fingerprints.append(list(row))
        # The actor must own every library the change takes something away from, not only the
        # one it gives to: a reassignment is a removal from the source audience's point of view.
        for source in sorted(sources):
            _operator(db, actor, source, now)
        audience, current = _audience(db, library, now)
        return {'operator_revision': str(revision), 'asset_state': self._mac('library-reassignment', fingerprints),
                'count': len(values), 'source_libraries': sorted(sources),
                'audience_state': self._mac('library-audience', audience), 'current_readers': len(current),
                'current_original_readers': sum(bool(member[5]) for member in current),
                'originals_granted': False, 'media_writes': False, 'moves_between_libraries': True}


class PromotionPlanner(_PromotionState):
    def __init__(self, connection, *, clock=time.time):
        super().__init__(connection, clock=clock)
        if connection.execute('PRAGMA query_only').fetchone()[0] != 1:
            raise PlanRejected('Promotion planning requires a read-only connection')

    def promote(self, *, library_id, operator_account_id, asset_ids):
        if (not isinstance(asset_ids, list) or not 1 <= len(asset_ids) <= MAX_ASSETS
                or any(type(item) is not int for item in asset_ids)
                or len(set(asset_ids)) != len(asset_ids)):
            raise PlanRejected('Explicit unique integer asset IDs required')
        return self._plan(PROMOTE_OPERATION, {'library_id': _library(library_id),
            'operator_account_id': operator_account_id,
            'asset_ids': [str(item) for item in sorted(asset_ids)]})

    def reassign(self, *, library_id, operator_account_id, asset_ids):
        if (not isinstance(asset_ids, list) or not 1 <= len(asset_ids) <= MAX_ASSETS
                or any(type(item) is not int for item in asset_ids)
                or len(set(asset_ids)) != len(asset_ids)):
            raise PlanRejected('Explicit unique integer asset IDs required')
        return self._plan(REASSIGN_OPERATION, {'library_id': _library(library_id),
            'operator_account_id': operator_account_id,
            'asset_ids': [str(item) for item in sorted(asset_ids)]})

    def validate(self, envelope):
        with self.access._transaction():
            return self._validate_in_transaction(envelope)


def _place(source, destination):
    """Move a file, refusing to overwrite and never leaving a half-written destination."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise PlanRejected('Destination already exists')
    try:
        os.replace(source, destination)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        # Cross-filesystem: land a complete copy first, then replace, so a partial file is
        # never visible under the final name.
        partial = destination.with_name(destination.name + '.part')
        try:
            shutil.copyfile(source, partial)
            os.replace(partial, destination)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        source.unlink()
    return destination


def _checked_envelope(envelope, review, operation):
    if type(review) is not PromotionReview or plan_digest(envelope) != review.plan_digest:
        raise PlanRejected('Exact reviewed plan required')
    envelope = json.loads(_json(envelope))
    if plan_digest(envelope) != review.plan_digest:
        raise PlanRejected('Plan changed during review')
    if envelope['plan']['operation'] != operation:
        raise PlanRejected('Exact reviewed plan required')
    _reference(review.authority_reference)
    if _identity(review.database) != review.database_identity:
        raise PlanRejected('Promotion target changed')
    return envelope


def _receipt(state, plan, review, extra):
    return {'version': 1, 'operation': plan['operation'], 'plan_id': plan['plan_id'],
            'plan_digest': review.plan_digest, 'applied_at': state.access._now(),
            'authority_reference': review.authority_reference,
            'database_identity': list(review.database_identity),
            'reviewed_state': plan['expected'], 'originals_granted': False, **extra}


def _record(state, plan, receipt):
    db = state.access.db
    db.execute('INSERT INTO access_provisioning_receipts VALUES (?,?,?)',
               (plan['plan_id'], receipt['plan_digest'], _json(receipt).decode()))
    state.access._audit(plan['target']['operator_account_id'], 'offline.' + plan['operation'],
                        plan['target']['library_id'], None)


def _assert_unexpired(state, plan):
    if not plan['created_at'] <= state.access._now() < plan['expires_at']:
        raise PlanRejected('Plan expired during application')


def promote_and_assign(envelope, *, review, clock=time.time):
    """Move each selected upload into the originals root and map it into the library.

    One operation, not two. Assigning without promoting would leave `assets.path` pointing
    outside `original_roots`, so the media route would refuse the photo: it would be in a library
    and still unviewable. Files are moved before the rows, so a database failure leaves a file in
    the originals root with no mapping — recoverable by inspection — rather than a row pointing
    at a path that is no longer valid.
    """
    envelope = _checked_envelope(envelope, review, PROMOTE_OPERATION)
    incoming = _directory(review.incoming_root, 'Explicit incoming root required')
    originals = _directory(review.originals_root, 'Explicit originals root required')
    if incoming.resolve().is_relative_to(originals.resolve()) or originals.resolve().is_relative_to(incoming.resolve()):
        raise PlanRejected('The incoming root must sit outside every original root')
    moved = []
    try:
        with ExistingDatabase(review.database)() as db:
            state = _PromotionState(db, clock=clock)
            with state.access._transaction(write=True):
                if _identity(review.database) != review.database_identity:
                    raise PlanRejected('Promotion target changed')
                plan = envelope['plan']
                if db.execute('SELECT 1 FROM access_provisioning_receipts WHERE plan_id=? OR plan_digest=?',
                              (plan['plan_id'], review.plan_digest)).fetchone():
                    raise PlanRejected('Plan already applied')
                state._validate_in_transaction(envelope)
                target = plan['target']
                library = target['library_id']
                rows = db.execute('''SELECT a.id,a.path,u.incoming_label,u.batch,a.hash_sha256,u.bytes
                    FROM assets a JOIN access_uploads u ON u.asset_id=a.id
                    WHERE a.id IN (''' + ','.join('?' for _ in target['asset_ids']) + ''')
                    ORDER BY a.id''', [int(v) for v in target['asset_ids']]).fetchall()
                for asset_id, path, label, batch, digest, size in rows:
                    source = Path(path)
                    # The recorded path must be inside the configured incoming root; otherwise the
                    # operator is applying against the wrong roots and nothing should move.
                    if not source.is_absolute() or not source.resolve().is_relative_to(incoming.resolve()):
                        raise PlanRejected('Recorded upload path is outside the incoming root')
                    info = source.lstat()
                    if not stat.S_ISREG(info.st_mode) or info.st_size != size:
                        raise PlanRejected('Uploaded file changed since planning')
                    destination = originals / PROMOTED_FOLDER / label / batch / source.name
                    _place(source, destination)
                    moved.append((source, destination))
                    db.execute('UPDATE assets SET path=? WHERE id=?', (str(destination.resolve()), asset_id))
                    db.execute("UPDATE access_uploads SET state='assigned' WHERE asset_id=?", (asset_id,))
                    db.execute('INSERT INTO access_asset_libraries VALUES (?,?)', (asset_id, library))
                receipt = _receipt(state, plan, review, {
                    'library_id': library, 'asset_count': len(rows),
                    'bytes_promoted': sum(row[5] for row in rows),
                    'promoted_folder': PROMOTED_FOLDER, 'media_writes': True})
                _record(state, plan, receipt)
                _assert_unexpired(state, plan)
                if db.execute('PRAGMA foreign_key_check').fetchone():
                    raise PlanRejected('Promotion barrier failed')
            return receipt
    except sqlite3.Error:
        # The rows rolled back. Put the bytes back so the incoming area still reflects the
        # database, which is the whole point of moving them after validation and before rows.
        for source, destination in reversed(moved):
            try:
                if destination.exists() and not source.exists():
                    _place(destination, source)
            except OSError:
                pass
        raise PlanRejected('Promotion failed; no partial operation committed') from None


def reassign_assets(envelope, *, review, clock=time.time):
    """Move selected assets from their current library into another one.

    Database-only: after promotion the bytes are already in the originals root. Because
    `asset_id` is the primary key of `access_asset_libraries`, this is an `UPDATE`, so a photo
    still belongs to exactly one library afterwards.
    """
    envelope = _checked_envelope(envelope, review, REASSIGN_OPERATION)
    with ExistingDatabase(review.database)() as db:
        state = _PromotionState(db, clock=clock)
        with state.access._transaction(write=True):
            if _identity(review.database) != review.database_identity:
                raise PlanRejected('Reassignment target changed')
            plan = envelope['plan']
            if db.execute('SELECT 1 FROM access_provisioning_receipts WHERE plan_id=? OR plan_digest=?',
                          (plan['plan_id'], review.plan_digest)).fetchone():
                raise PlanRejected('Plan already applied')
            state._validate_in_transaction(envelope)
            target = plan['target']
            library = target['library_id']
            sources = set()
            for value in target['asset_ids']:
                row = db.execute('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                 (int(value),)).fetchone()
                if row is None:
                    raise PlanRejected('Every selected asset must currently belong to a library')
                sources.add(row[0])
                db.execute('UPDATE access_asset_libraries SET library_id=? WHERE asset_id=?',
                           (library, int(value)))
            receipt = _receipt(state, plan, review, {
                'library_id': library, 'asset_count': len(target['asset_ids']),
                'source_libraries': sorted(sources), 'media_writes': False})
            _record(state, plan, receipt)
            _assert_unexpired(state, plan)
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise PlanRejected('Reassignment barrier failed')
        return receipt
