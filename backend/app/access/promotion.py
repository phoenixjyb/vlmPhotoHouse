"""Reviewed promotion of member uploads into a library, and bounded reassignment.

Sealed plans shared by the offline tool and the explicitly enabled admin upload inbox:

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
from contextlib import contextmanager
from dataclasses import dataclass
import errno
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import stat
import time
import uuid

from .provisioning import PlanRejected, _PlanState, _json, _library
from .provisioning_apply import _identity, _reference, plan_digest
from .runtime import ExistingDatabase

PROMOTE_OPERATION = 'promote_and_assign_uploads'
REASSIGN_OPERATION = 'reassign_library_assets'
UNASSIGN_OPERATION = 'unassign_library_assets'
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
    STORY_REVIEW_ROWS = 10000
    STORY_REVIEW_BYTES = 8 * 1024 * 1024

    def _story_review_state(self, source_by_asset):
        """Hash story rows/history incrementally, with an explicit review budget."""
        key = self.access.db.execute('SELECT secret FROM access_admission_key WHERE id=1').fetchone()
        if not key or not isinstance(key[0], bytes) or len(key[0]) != 32:
            raise PlanRejected('Planning unavailable')
        mac = hmac.new(key[0], b'PhotoHouse offline plan v1\0library-reassignment-stories\0', hashlib.sha256)
        rows_seen = 0
        bytes_seen = 0
        story_ids = []

        def add(marker, row):
            nonlocal rows_seen, bytes_seen
            encoded = _json([marker, *list(row)])
            rows_seen += 1
            bytes_seen += len(encoded)
            if rows_seen > self.STORY_REVIEW_ROWS or bytes_seen > self.STORY_REVIEW_BYTES:
                raise PlanRejected('Story metadata exceeds review budget')
            mac.update(encoded)

        db = self.access.db
        for asset_id, source in sorted(source_by_asset.items()):
            cursor = db.execute('''SELECT id,asset_id,library_id,author_id,revision,title,text,
                    language,byline,created_at,updated_at,deleted
                FROM access_stories WHERE asset_id=? AND library_id=? ORDER BY id''',
                (asset_id, source))
            while True:
                batch = cursor.fetchmany(128)
                if not batch:
                    break
                for row in batch:
                    add(['story', asset_id, source], row)
                    story_ids.append(row[0])
        for story_id in story_ids:
            cursor = db.execute('''SELECT story_id,revision,editor_id,mutation_id,request_digest,
                    title,text,language,byline,occurred_at,deleted
                FROM access_story_revisions WHERE story_id=? ORDER BY revision''', (story_id,))
            while True:
                batch = cursor.fetchmany(128)
                if not batch:
                    break
                for row in batch:
                    add(['revision', story_id], row)
        return mac.hexdigest(), len(story_ids)

    def _state(self, operation, target):
        if type(target) is not dict:
            raise PlanRejected('Invalid plan')
        if operation == PROMOTE_OPERATION:
            return self._promote_state(target)
        if operation == REASSIGN_OPERATION:
            return self._reassign_state(target)
        if operation == UNASSIGN_OPERATION:
            return self._unassign_state(target)
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
        source_by_asset = {}
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
                source_by_asset[row[0]] = row[4]
                fingerprints.append(list(row))
        # The actor must own every library the change takes something away from, not only the
        # one it gives to: a reassignment is a removal from the source audience's point of view.
        for source in sorted(sources):
            _operator(db, actor, source, now)
        # Reassignment also moves stories that belong to the selected asset and its
        # current source library. Bind both the story rows and their complete revision
        # history into the review so a concurrent edit cannot be silently carried across.
        album_links = []
        face_count = 0
        for asset_id, source in sorted(source_by_asset.items()):
            links = db.execute('''SELECT aa.album_id,aa.asset_id,aa.position,a.cover_asset_id,
                    substr(a.title,1,160),substr(a.title_zh,1,160),substr(a.description,1,1000),
                    a.theme,a.status,a.updated_at,o.library_id,o.revision
                FROM album_assets aa JOIN albums a ON a.id=aa.album_id
                JOIN access_album_libraries o ON o.album_id=aa.album_id
                WHERE aa.asset_id=? AND o.library_id=? ORDER BY aa.album_id,aa.position,aa.id''',
                (asset_id, source)).fetchall()
            album_links.extend([list(row) for row in links])
            # A malformed/legacy album may retain a cover reference without an
            # album_assets edge. Bind that reference too; the move must never
            # silently change which cover is exposed after owner review.
            covers = db.execute('''SELECT a.id,NULL,-1,a.cover_asset_id,
                    substr(a.title,1,160),substr(a.title_zh,1,160),substr(a.description,1,1000),
                    a.theme,a.status,a.updated_at,o.library_id,o.revision
                FROM albums a JOIN access_album_libraries o ON o.album_id=a.id
                WHERE a.cover_asset_id=? AND o.library_id=?
                AND NOT EXISTS (SELECT 1 FROM album_assets aa
                                WHERE aa.album_id=a.id AND aa.asset_id=?)
                ORDER BY a.id''', (asset_id, source, asset_id)).fetchall()
            album_links.extend([list(row) for row in covers])
            face_count += db.execute('SELECT count(*) FROM face_detections WHERE asset_id=?',
                                     (asset_id,)).fetchone()[0]
        story_state, story_count = self._story_review_state(source_by_asset)
        album_state = self._mac('library-reassignment-albums', album_links)
        source_audiences = {}
        source_current_audiences = {}
        source_owner_revisions = {}
        for source in sorted(sources):
            audience, current = _audience(db, source, now)
            source_audiences[source] = self._mac('library-audience', audience)
            source_current_audiences[source] = self._mac('library-current-audience', current)
            source_owner_revisions[source] = {row[0]: row[3] for row in audience if row[2] == 'owner'}
        audience, current = _audience(db, library, now)
        return {'operator_revision': str(revision), 'asset_state': self._mac('library-reassignment', fingerprints),
                'count': len(values), 'source_libraries': sorted(sources),
                'audience_state': self._mac('library-audience', audience), 'current_readers': len(current),
                'current_original_readers': sum(bool(member[5]) for member in current),
                'source_audiences': source_audiences, 'source_current_audiences': source_current_audiences,
                'source_owner_revisions': source_owner_revisions, 'story_state': story_state,
                'album_state': album_state, 'story_count': story_count,
                'source_album_count': len({row[0] for row in album_links}), 'face_count': face_count,
                'originals_granted': False, 'media_writes': False, 'moves_between_libraries': True}


    def _unassign_state(self, target):
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
                    u.incoming_label,u.batch,u.state,m.library_id
                FROM assets a JOIN access_uploads u ON u.asset_id=a.id
                JOIN access_asset_libraries m ON m.asset_id=a.id
                WHERE a.id IN (''' + ','.join('?' for _ in chunk) + ') ORDER BY a.id', chunk).fetchall()
            if len(rows) != len(chunk):
                raise PlanRejected('Every selected asset must be a promoted upload')
            for row in rows:
                # Restricted to promoted uploads on purpose. An asset with no provenance row
                # could never be promoted again, because promotion requires that row, so
                # un-assigning one would be a one-way door out of every library.
                if (row[3] not in (None, 'active') or row[7] != 'assigned'
                        or row[8] != library):
                    raise PlanRejected('Only promoted uploads in this library can be un-assigned')
                fingerprints.append(list(row))
                total += row[4]
        audience, current = _audience(db, library, now)
        return {'operator_revision': str(revision),
                'asset_state': self._mac('upload-unassignment', fingerprints),
                'count': len(values), 'bytes_to_return': total,
                'audience_state': self._mac('library-audience', audience), 'current_readers': len(current),
                'current_original_readers': sum(bool(member[5]) for member in current),
                'originals_granted': False, 'media_writes': True, 'moves_between_libraries': False}


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

    def unassign(self, *, library_id, operator_account_id, asset_ids):
        if (not isinstance(asset_ids, list) or not 1 <= len(asset_ids) <= MAX_ASSETS
                or any(type(item) is not int for item in asset_ids)
                or len(set(asset_ids)) != len(asset_ids)):
            raise PlanRejected('Explicit unique integer asset IDs required')
        return self._plan(UNASSIGN_OPERATION, {'library_id': _library(library_id),
            'operator_account_id': operator_account_id,
            'asset_ids': [str(item) for item in sorted(asset_ids)]})

    def validate(self, envelope):
        with self.access._transaction():
            return self._validate_in_transaction(envelope)


def _place(source, destination):
    """Move a file, refusing to overwrite and never leaving a half-written destination."""
    def remove_owned(path, identity):
        current = os.lstat(path)
        if (current.st_dev, current.st_ino) != identity:
            raise PlanRejected('Move cleanup path changed; manual recovery required')
        os.unlink(path)

    destination.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(destination):
        raise PlanRejected('Destination already exists')
    source_info = os.lstat(source)
    source_identity = (source_info.st_dev, source_info.st_ino)
    try:
        # A hard-link install is atomic and cannot clobber a destination that appears after
        # the preflight check.  Removing the source completes the same-filesystem move.
        os.link(source, destination)
        try:
            remove_owned(source, source_identity)
        except BaseException as error:
            try:
                remove_owned(destination, source_identity)
            except BaseException as cleanup_error:
                raise PlanRejected('Move cleanup failed; manual recovery required') from cleanup_error
            raise error
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        # Cross-filesystem: land a complete copy first, then install it without replacing an
        # existing destination, so a partial file is never visible under the final name.
        partial = destination.with_name('.' + destination.name + '.' + uuid.uuid4().hex + '.part')
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        partial_info = os.fstat(descriptor)
        partial_identity = (partial_info.st_dev, partial_info.st_ino)
        try:
            with os.fdopen(descriptor, 'wb') as output, open(source, 'rb') as input_stream:
                shutil.copyfileobj(input_stream, output)
                output.flush()
                os.fsync(output.fileno())
        except BaseException:
            remove_owned(partial, partial_identity)
            raise
        try:
            os.link(partial, destination)
        except BaseException:
            remove_owned(partial, partial_identity)
            raise
        try:
            remove_owned(partial, partial_identity)
        except BaseException as error:
            try:
                remove_owned(destination, partial_identity)
            except BaseException as cleanup_error:
                raise PlanRejected('Move cleanup failed; manual recovery required') from cleanup_error
            raise error
        try:
            remove_owned(source, source_identity)
        except BaseException as error:
            try:
                remove_owned(destination, partial_identity)
            except BaseException as cleanup_error:
                raise PlanRejected('Move cleanup failed; manual recovery required') from cleanup_error
            raise error
    return destination


def _restore_moves(moved):
    """Reverse completed moves without replacing an existing path.

    A rollback must never overwrite a file that appeared while the transfer was in
    progress.  Missing source/destination paths are failures too: silently carrying
    on would leave SQLite and the filesystem describing different states.
    """
    failures = []
    for source, destination in reversed(moved):
        try:
            if os.path.lexists(source) or not os.path.lexists(destination):
                raise PlanRejected('Rollback path changed; manual recovery required')
            _place(destination, source)
        except BaseException as error:
            failures.append(error)
    if failures:
        names = ', '.join(type(error).__name__ for error in failures)
        raise PlanRejected('Rollback failed; manual recovery required (' + names + ')')


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
            'actor_account_id': plan['target']['operator_account_id'],
            'database_identity': list(review.database_identity),
            'reviewed_state': plan['expected'], 'originals_granted': False, **extra}


def _record(state, plan, receipt):
    db = state.access.db
    db.execute('INSERT INTO access_provisioning_receipts VALUES (?,?,?)',
               (plan['plan_id'], receipt['plan_digest'], _json(receipt).decode()))
    audit_prefix = 'web.' if receipt.get('channel') == 'web' else 'offline.'
    state.access._audit(plan['target']['operator_account_id'], audit_prefix + plan['operation'],
                        plan['target']['library_id'], None)


def _assert_unexpired(state, plan):
    if not plan['created_at'] <= state.access._now() < plan['expires_at']:
        raise PlanRejected('Plan expired during application')


@contextmanager
def _file_transaction(access, moves, operation):
    """Keep the writer reservation until failed file moves are compensated.

    Upload publication takes the same reservation. Restoring after a database rollback
    would let a waiting upload repopulate a path before compensation could restore it.
    Process death or a storage failure still requires operator reconciliation.
    """
    db = access.db
    if db.in_transaction:
        raise ValueError('Promotion must own its transaction')
    db.execute('BEGIN IMMEDIATE')
    try:
        yield
        db.commit()
    except BaseException as error:
        try:
            if moves:
                _restore_moves(moves)
        except BaseException as recovery_error:
            raise PlanRejected(operation + ' failed; rollback failed after '
                               + type(error).__name__) from recovery_error
        finally:
            db.rollback()
        raise


def promote_and_assign(envelope, *, review, clock=time.time, authorize=None, allow_replay=False):
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
    with ExistingDatabase(review.database)() as db:
        state = _PromotionState(db, clock=clock)
        with _file_transaction(state.access, moved, 'Promotion'):
            if _identity(review.database) != review.database_identity:
                raise PlanRejected('Promotion target changed')
            plan = envelope['plan']
            # HTTP callers recheck the live session, operator, owner and uploader scope
            # inside the same writer reservation as all file and mapping changes.
            if authorize is not None:
                authorize(state.access, plan)
            prior = db.execute('SELECT plan_digest,receipt FROM access_provisioning_receipts WHERE plan_id=? OR plan_digest=?',
                               (plan['plan_id'], review.plan_digest)).fetchone()
            if prior:
                if allow_replay and authorize is not None and prior[0] == review.plan_digest:
                    # A later offline unassignment/reassignment must never be reported
                    # as this old approval still being applied.
                    for asset in plan['target']['asset_ids']:
                        current = db.execute('''SELECT u.state,m.library_id FROM access_uploads u
                            LEFT JOIN access_asset_libraries m ON m.asset_id=u.asset_id
                            WHERE u.asset_id=?''', (int(asset),)).fetchone()
                        if current != ('assigned', plan['target']['library_id']):
                            raise PlanRejected('Applied upload changed; review again')
                    return json.loads(prior[1])
                raise PlanRejected('Plan already applied')
            state._validate_in_transaction(envelope)
            target = plan['target']
            library = target['library_id']
            rows = db.execute('''SELECT a.id,a.path,u.incoming_label,u.batch,a.hash_sha256,u.bytes
                FROM assets a JOIN access_uploads u ON u.asset_id=a.id
                WHERE a.id IN (''' + ','.join('?' for _ in target['asset_ids']) + ''')
                ORDER BY a.id''', [int(v) for v in target['asset_ids']]).fetchall()
            transfers = []
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
                if os.path.lexists(destination):
                    raise PlanRejected('Destination already exists')
                transfers.append((asset_id, source, destination, label, batch, digest, size))
            for asset_id, source, destination, label, batch, digest, size in transfers:
                _place(source, destination)
                moved.append((source, destination))
                db.execute('UPDATE assets SET path=? WHERE id=?', (str(destination.resolve()), asset_id))
                db.execute("UPDATE access_uploads SET state='assigned' WHERE asset_id=?", (asset_id,))
                db.execute('INSERT INTO access_asset_libraries VALUES (?,?)', (asset_id, library))
            receipt = _receipt(state, plan, review, {
                'library_id': library, 'asset_count': len(rows),
                'bytes_promoted': sum(row[5] for row in rows),
                'promoted_folder': PROMOTED_FOLDER, 'media_writes': True})
            if authorize is not None:
                authorize(state.access, plan)
                receipt['channel'] = 'web'
            _record(state, plan, receipt)
            _assert_unexpired(state, plan)
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise PlanRejected('Promotion barrier failed')
        return receipt


def unassign_assets(envelope, *, review, clock=time.time):
    """Return promoted uploads to the incoming area and unmap them.

    The exact inverse of promotion, **including the file move**. Leaving the bytes in the
    originals root would make the photo un-promotable again, because promotion requires the
    recorded path to sit inside the incoming root — so an un-assign that skipped the move would
    be a one-way door dressed up as an undo.

    Restricted to assets that carry upload provenance and are currently assigned, so a photo that
    never came through upload cannot be made unrecoverable this way.
    """
    envelope = _checked_envelope(envelope, review, UNASSIGN_OPERATION)
    incoming = _directory(review.incoming_root, 'Explicit incoming root required')
    originals = _directory(review.originals_root, 'Explicit originals root required')
    if incoming.resolve().is_relative_to(originals.resolve()) or originals.resolve().is_relative_to(incoming.resolve()):
        raise PlanRejected('The incoming root must sit outside every original root')
    returned = []
    with ExistingDatabase(review.database)() as db:
        state = _PromotionState(db, clock=clock)
        with _file_transaction(state.access, returned, 'Unassignment'):
            if _identity(review.database) != review.database_identity:
                raise PlanRejected('Unassignment target changed')
            plan = envelope['plan']
            if db.execute('SELECT 1 FROM access_provisioning_receipts WHERE plan_id=? OR plan_digest=?',
                          (plan['plan_id'], review.plan_digest)).fetchone():
                raise PlanRejected('Plan already applied')
            state._validate_in_transaction(envelope)
            target = plan['target']
            library = target['library_id']
            rows = db.execute('''SELECT a.id,a.path,u.incoming_label,u.batch,u.bytes
                FROM assets a JOIN access_uploads u ON u.asset_id=a.id
                WHERE a.id IN (''' + ','.join('?' for _ in target['asset_ids']) + ''')
                ORDER BY a.id''', [int(v) for v in target['asset_ids']]).fetchall()
            transfers = []
            for asset_id, path, label, batch, size in rows:
                source = Path(path)
                # The recorded path must be inside the originals root, or the operator is
                # applying against the wrong roots and nothing should move.
                if not source.is_absolute() or not source.resolve().is_relative_to(originals.resolve()):
                    raise PlanRejected('Recorded path is outside the originals root')
                info = source.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_size != size:
                    raise PlanRejected('Promoted file changed since planning')
                destination = incoming / label / batch / source.name
                if os.path.lexists(destination):
                    raise PlanRejected('Destination already exists')
                transfers.append((asset_id, source, destination, label, batch, size))
            for asset_id, source, destination, label, batch, size in transfers:
                _place(source, destination)
                returned.append((source, destination))
                db.execute('UPDATE assets SET path=? WHERE id=?', (str(destination.resolve()), asset_id))
                db.execute("UPDATE access_uploads SET state='incoming' WHERE asset_id=?", (asset_id,))
                db.execute('DELETE FROM access_asset_libraries WHERE asset_id=?', (asset_id,))
            receipt = _receipt(state, plan, review, {
                'library_id': library, 'asset_count': len(rows),
                'bytes_returned': sum(row[4] for row in rows), 'media_writes': True})
            _record(state, plan, receipt)
            _assert_unexpired(state, plan)
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise PlanRejected('Unassignment barrier failed')
        return receipt


def reassign_assets(envelope, *, review, clock=time.time, authorize=None, allow_replay=False):
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
            if authorize is not None:
                authorize(state.access, plan)
            if db.execute('SELECT 1 FROM access_provisioning_receipts WHERE plan_id=? OR plan_digest=?',
                          (plan['plan_id'], review.plan_digest)).fetchone():
                prior = db.execute('SELECT plan_digest,receipt FROM access_provisioning_receipts WHERE plan_id=? OR plan_digest=?',
                                   (plan['plan_id'], review.plan_digest)).fetchone()
                if allow_replay and authorize is not None and prior[0] == review.plan_digest:
                    for asset in plan['target']['asset_ids']:
                        current = db.execute('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                             (int(asset),)).fetchone()
                        if current != (plan['target']['library_id'],):
                            raise PlanRejected('Reassigned asset changed; review again')
                    return json.loads(prior[1])
                raise PlanRejected('Plan already applied')
            state._validate_in_transaction(envelope)
            target = plan['target']
            library = target['library_id']
            sources = set()
            source_by_asset = {}
            for value in target['asset_ids']:
                row = db.execute('SELECT library_id FROM access_asset_libraries WHERE asset_id=?',
                                 (int(value),)).fetchone()
                if row is None:
                    raise PlanRejected('Every selected asset must currently belong to a library')
                sources.add(row[0])
                source_by_asset[int(value)] = row[0]
                db.execute('UPDATE access_asset_libraries SET library_id=? WHERE asset_id=?',
                           (library, int(value)))
            story_count = 0
            for asset_id, source in source_by_asset.items():
                cursor = db.execute('''UPDATE access_stories SET library_id=?
                    WHERE asset_id=? AND library_id=?''', (library, asset_id, source))
                story_count += cursor.rowcount
            receipt = _receipt(state, plan, review, {
                'library_id': library, 'asset_count': len(target['asset_ids']),
                'source_libraries': sorted(sources), 'stories_moved': story_count,
                'stories_preserved_history': True, 'source_album_count': plan['expected'].get('source_album_count', 0),
                'face_count': plan['expected'].get('face_count', 0), 'media_writes': False})
            if authorize is not None:
                authorize(state.access, plan)
                receipt['channel'] = 'web'
            _record(state, plan, receipt)
            _assert_unexpired(state, plan)
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise PlanRejected('Reassignment barrier failed')
        return receipt
