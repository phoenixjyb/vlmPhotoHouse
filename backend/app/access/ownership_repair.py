"""Explicit offline suppressed-asset ownership repair; no HTTP or media access.

Whole-asset ownership has a lasting audience effect. An external owner must
approve provenance, the target-wide permission change and a quiescent maintenance
window. A seal/receipt records that decision; it never supplies that authority.
"""
import hashlib
from pathlib import Path
import re
import sqlite3
import time

from .provisioning import PlanRejected, _json, _library
from .runtime import REQUIRED_REVISION

OPERATION = 'repair_suppressed_person_ownership'
FIELDS = {'library_id', 'operator_account_id', 'person_id', 'asset_ids',
          'quiescence_reference', 'provenance_reference'}
MAX_ASSETS = 500
MAX_PEOPLE = 100
MAX_ROWS = 200000
MAX_BYTES = 64 * 1024 * 1024


def _id(value):
    if (not isinstance(value, str) or not re.fullmatch('[1-9][0-9]{0,18}', value)
            or int(value) > 2**63 - 1):
        raise PlanRejected('Explicit canonical identity required')
    return int(value)


def source_fingerprint():
    """Bind the reviewed Python implementation, including policies and CLI.

    Read source files only, never configuration, models, secrets or media. Local
    administrators remain trusted; this digest is not a code-signing mechanism.
    """
    root = Path(__file__).resolve().parents[3]
    files = [p for directory in ('backend/app', 'backend/migrations')
             for p in (root / directory).rglob('*.py') if '__pycache__' not in p.parts]
    files.append(root / 'scripts/provision_access.py')
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(_json([str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest()]))
        digest.update(b'\n')
    return digest.hexdigest()


def repair_state(state, target, *, repaired=False):
    db = state.access.db
    deadline = time.monotonic() + 30
    db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    try:
        return _state(state, target, repaired=repaired, deadline=deadline)
    except sqlite3.OperationalError as exc:
        if str(exc) == 'interrupted':
            raise PlanRejected('Repair review budget exceeded') from None
        raise
    finally:
        db.set_progress_handler(None, 0)


def _state(state, target, *, repaired, deadline):
    if not isinstance(target, dict) or set(target) != FIELDS:
        raise PlanRejected('Explicit repair fields required')
    library = _library(target['library_id'])
    actor = target['operator_account_id']
    if not isinstance(actor, str) or len(actor) != 36:
        raise PlanRejected('Explicit operator required')
    person = _id(target['person_id'])
    for key in ('quiescence_reference', 'provenance_reference'):
        if not isinstance(target[key], str) or not re.fullmatch('[A-Za-z0-9_-]{3,80}', target[key]):
            raise PlanRejected('Independent shutdown and ownership review references required')
    values = target['asset_ids']
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_ASSETS:
        raise PlanRejected('Bounded explicit suppressed asset selection required')
    selected = [_id(value) for value in values]
    if selected != sorted(set(selected)):
        raise PlanRejected('Sorted unique asset selection required')
    chosen = set(selected)
    db, now = state.access.db, state.access._now()
    if db.execute('SELECT version_num FROM alembic_version').fetchall() != [(REQUIRED_REVISION,)]:
        raise PlanRejected('Reviewed schema required')
    if db.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
        raise PlanRejected('Foreign key enforcement required')
    if db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
        raise PlanRejected('Offline rollback journal database required')
    if db.execute("""SELECT 1 FROM tasks WHERE state='running' OR
        (state='pending' AND type IN ('face','face_embed','person_cluster',
        'person_recluster','person_label_propagate')) LIMIT 1""").fetchone():
        raise PlanRejected('Stopped writers and no pending face work required')
    owner = db.execute('''SELECT m.revision FROM access_memberships m
        JOIN access_accounts a ON a.id=m.account_id JOIN access_libraries l ON l.id=m.library_id
        JOIN access_operators o ON o.account_id=m.account_id WHERE m.account_id=? AND m.library_id=?
        AND m.role='owner' AND m.status='approved' AND a.state='active' AND l.state='active'
        AND (m.expires_at IS NULL OR m.expires_at>?)''', (actor, library, now)).fetchone()
    if not owner:
        raise PlanRejected('Current active operator and library owner required')
    audience = db.execute('''SELECT m.account_id,m.status,m.role,m.revision,m.expires_at,m.originals,a.state
        FROM access_memberships m JOIN access_accounts a ON a.id=m.account_id
        WHERE m.library_id=? ORDER BY m.account_id LIMIT 10001''', (library,)).fetchall()
    if len(audience) > 10000:
        raise PlanRejected('Audience budget exceeded')
    digest = hashlib.sha256()
    used = 0

    def feed(value):
        nonlocal used
        raw = _json(value)
        used += len(raw)
        if used > MAX_BYTES or time.monotonic() > deadline:
            raise PlanRejected('Repair closure budget exceeded')
        digest.update(raw); digest.update(b'\n')

    def rows(table, column, ids):
        # Table/column identifiers are constants owned by this implementation.
        result = []
        for offset in range(0, len(ids), 500):
            chunk = ids[offset:offset + 500]
            cursor = db.execute('SELECT * FROM ' + table + ' WHERE ' + column + ' IN (' +
                ','.join('?' for _ in chunk) + ') ORDER BY 1 LIMIT ?', (*chunk, MAX_ROWS + 1 - len(result)))
            names = [c[0] for c in cursor.description]
            for row in cursor:
                result.append(dict(zip(names, row)))
                if len(result) > MAX_ROWS:
                    raise PlanRejected('Repair reference budget exceeded')
        return sorted(result, key=lambda row: tuple(str(row[k]) for k in row))

    candidate_faces = rows('face_detections', 'asset_id', selected)
    # Include every unassigned detection as well as all named detections.
    cohort = sorted({f['person_id'] for f in candidate_faces if f['person_id'] is not None})
    if person not in cohort or len(cohort) > MAX_PEOPLE:
        raise PlanRejected('Target references or affected people budget invalid')
    faces = rows('face_detections', 'person_id', cohort)
    asset_ids = sorted({f['asset_id'] for f in faces + candidate_faces})
    assets = {row['id']: row for row in rows('assets', 'id', asset_ids)}
    if set(assets) != set(asset_ids):
        raise PlanRejected('Missing referenced asset')
    maps = {row['asset_id']: row['library_id'] for row in rows('access_asset_libraries', 'asset_id', asset_ids)}
    people = {row['id']: row for row in rows('persons', 'id', cohort)}
    owners = {row['person_id']: row for row in rows('access_person_libraries', 'person_id', cohort)}
    if set(people) != set(cohort):
        raise PlanRejected('Missing referenced person')
    if any(mapping != library for mapping in maps.values()):
        raise PlanRejected('Foreign reference requires separate ownership review')
    if any(row['library_id'] != library for row in owners.values()):
        raise PlanRejected('Foreign person ownership requires separate review')
    expected_owner = {'person_id': person, 'library_id': library, 'creator_id': actor, 'revision': 1}
    if (owners.get(person) != expected_owner if repaired else person in owners):
        raise PlanRejected('Target ownership changed or already assigned')
    for asset in selected:
        if (asset not in assets or assets[asset]['status'] != 'suppressed'
                or (maps.get(asset) != library if repaired else asset in maps)):
            raise PlanRejected('Only unchanged suppressed unmapped target assets may be repaired')
    # Normalize only the explicitly allowed inserts for postcondition comparison.
    prior_maps = {asset: value for asset, value in maps.items() if asset not in chosen}
    prior_owners = {pid: value for pid, value in owners.items() if pid != person}
    target_faces = [f for f in faces if f['person_id'] == person]
    missing = {f['asset_id'] for f in target_faces if f['asset_id'] not in prior_maps}
    if missing != chosen:
        raise PlanRejected('Selection must exactly cover all unmapped target references')
    if not any(assets[f['asset_id']]['status'] in (None, 'active') and
               prior_maps.get(f['asset_id']) == library for f in target_faces):
        raise PlanRejected('Target must already be visible through active library faces')

    policy = []
    for pid in cohort:
        refs = [f for f in faces if f['person_id'] == pid]
        active = sum(assets[f['asset_id']]['status'] in (None, 'active') and
                     prior_maps.get(f['asset_id']) == library for f in refs)

        def capabilities(mapping, ownership):
            exclusive = all(mapping.get(f['asset_id']) == library for f in refs)
            visible = pid in ownership or active > 0
            return {'visible': visible, 'exclusive': exclusive,
                    'ownership_import_eligible': pid not in ownership and exclusive,
                    'can_rename': visible and exclusive,
                    'can_assign_target': visible and exclusive,
                    'assignable_active_faces': active if exclusive else 0,
                    'worker_owned_eligible': pid in ownership and exclusive}

        before = capabilities(prior_maps, prior_owners)
        after = capabilities({**prior_maps, **{asset: library for asset in chosen}},
                             {**prior_owners, person: expected_owner})
        if pid != person and before != after:
            raise PlanRejected('Repair would unlock another identity; separate review required')
        policy.append({'person_id': str(pid), 'before': before, 'after': after})

    feed(['schema', db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()])
    feed(['assets', [assets[k] for k in sorted(assets)]])
    feed(['candidate_faces', candidate_faces])
    feed(['all_affected_person_faces', faces])
    feed(['people', [people[k] for k in cohort]])
    feed(['prior_asset_ownership', sorted(prior_maps.items())])
    feed(['prior_person_ownership', [prior_owners[k] for k in sorted(prior_owners)]])
    face_ids = sorted({f['id'] for f in faces + candidate_faces})
    for table, column, identities in (
        ('person_embedding_artifacts', 'person_id', cohort),
        ('face_embedding_artifacts', 'face_id', face_ids),
        ('face_assignment_events', 'face_id', face_ids),
    ):
        feed([table, rows(table, column, identities)])
    # Bind rename-away-and-back revisions without including the repair's own audit.
    for pid in cohort:
        feed(['rename_revision', pid, db.execute('''SELECT coalesce(max(id),0) FROM access_audit
            WHERE library_id=? AND action=?''', (library, 'person.rename.' + str(pid))).fetchone()[0]])
    return {'operator_revision': str(owner[0]), 'source_state': source_fingerprint(),
            'schema_revision': REQUIRED_REVISION,
            'cohort_state': state._mac('suppressed-repair-cohort', digest.hexdigest()),
            'audience_state': state._mac('suppressed-repair-audience', audience),
            'asset_count': len(selected), 'person_count': 1, 'affected_people_count': len(cohort),
            'unassigned_candidate_faces': sum(f['person_id'] is None for f in candidate_faces),
            'policy_delta': policy, 'originals_granted': False, 'memberships_changed': False,
            'legacy_records_changed': False, 'media_writes': False, 'jobs_enqueued': False,
            'suppression_preserved': True}


def apply_repair(state, target):
    if not state.access.db.in_transaction:
        raise PlanRejected('Write reservation required')
    state.access.db.executemany('INSERT INTO access_asset_libraries(asset_id,library_id) VALUES(?,?)',
        ((int(value), target['library_id']) for value in target['asset_ids']))
    state.access.db.execute('''INSERT INTO access_person_libraries(person_id,library_id,creator_id,revision)
        VALUES(?,?,?,1)''', (int(target['person_id']), target['library_id'], target['operator_account_id']))


def restrict_writes(action, table, column, database, trigger):
    """Reject trigger side effects and every update/delete, including hidden ones.

    Installed only on the fresh offline apply connection for this operation.
    Receipt and audit are inserted by the reviewed apply implementation itself.
    """
    if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
        if (action != sqlite3.SQLITE_INSERT or trigger is not None or database != 'main'
                or table not in {'access_asset_libraries', 'access_person_libraries',
                                 'access_provisioning_receipts', 'access_audit'}):
            return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK
