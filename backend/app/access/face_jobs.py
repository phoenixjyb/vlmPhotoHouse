"""Private, sealed face-job provisioning. No HTTP route, vectors or model loading."""
import hashlib
import hmac
import json
import re
import time

from .provisioning import PlanRejected, _json
from ..scoped_face_worker import KINDS, TABLES, _payload, assignment_selection

OPERATION = 'enqueue_face_assignment'
FIELDS = {'kind', 'payload', 'library_id', 'operator_account_id', 'quiescence_reference'}


def face_job_state(state, target):
    if not isinstance(target, dict) or set(target) != FIELDS or target['kind'] not in KINDS:
        raise PlanRejected('Explicit face job required')
    p = _payload(target['payload'], target['kind'])
    if p != target['payload'] or any(target[k] != p[k] for k in ('library_id', 'operator_account_id')):
        raise PlanRejected('Face job identity mismatch')
    if not isinstance(target['quiescence_reference'], str) or not re.fullmatch('[A-Za-z0-9_-]{3,80}', target['quiescence_reference']):
        raise PlanRejected('Independent writer review required')
    db = state.access.db
    if not TABLES <= {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        raise PlanRejected('Migrated face tables required')
    executing = getattr(state, '_executing_face_task', None)
    if executing is None:
        if db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete' or db.execute("SELECT 1 FROM tasks WHERE state='running' LIMIT 1").fetchone():
            raise PlanRejected('Stopped writers and offline database required')
    if db.execute("""SELECT 1 FROM tasks WHERE type IN ('face','face_embed','person_cluster','person_recluster','person_label_propagate')
        AND state IN ('pending','running') AND id<>? LIMIT 1""", (executing or -1,)).fetchone():
        raise PlanRejected('Other face work requires separate review')
    owner = db.execute('''SELECT m.revision,m.expires_at,a.password_hash FROM access_memberships m
        JOIN access_accounts a ON a.id=m.account_id JOIN access_operators o ON o.account_id=a.id
        JOIN access_libraries l ON l.id=m.library_id WHERE m.library_id=? AND m.account_id=?
        AND m.role='owner' AND m.status='approved' AND a.state='active' AND l.state='active'
        AND (m.expires_at IS NULL OR m.expires_at>?)''', (p['library_id'], p['operator_account_id'], state.access._now())).fetchone()
    if not owner:
        raise PlanRejected('Current owner and operator required')
    deadline = time.monotonic() + 10
    db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    try:
        owned, refs, candidates = assignment_selection(lambda sql, **params: db.execute(sql, params).fetchall(), p, target['kind'])
    finally:
        db.set_progress_handler(None, 0)
    ids = {row[0] for row in owned}
    refs = [tuple(row) for row in refs if row[2] in ids]
    candidates = [tuple(row) for row in candidates if row[2] is None or row[2] in ids]
    if not candidates:
        raise PlanRejected('No eligible candidates in this bounded selection')
    for row in refs + candidates:
        if not isinstance(row[5], str) or len(row[5]) > 4096 or not isinstance(row[6], str) or not re.fullmatch('[0-9a-f]{64}', row[6]):
            raise PlanRejected('Qualified vector metadata required')
    return {'candidate_ids': [str(row[0]) for row in candidates], 'reference_count': len(refs),
            'cohort_state': state._mac('face-job-cohort', [[tuple(r) for r in owned], refs, candidates]),
            'owner_state': state._mac('face-job-owner', list(owner)),
            'new_people_possible': target['kind'] != 'person_label_propagate',
            'inference_started': False, 'media_writes': False, 'caption_changes': False}


def enqueue(state, target):
    cursor = state.access.db.execute("""INSERT INTO tasks(type,payload_json,state,priority,retry_count,cancel_requested,scheduled_at)
        VALUES (?,?,'pending',180,0,0,NULL)""", (target['kind'], _json(target['payload']).decode()))
    return int(cursor.lastrowid)


def seal_receipt(state, receipt, envelope, task_id):
    receipt.update(task_id=task_id, authenticated_plan=envelope)
    receipt['enqueue_seal'] = state._mac('authenticated-face-enqueue', receipt)


def verify_queued(state, *, plan_id, digest, task_id, database_identity):
    row = state.access.db.execute('SELECT receipt FROM access_provisioning_receipts WHERE plan_id=? AND plan_digest=?',
                                  (plan_id, digest)).fetchone()
    if not row or len(row[0]) > 2_000_000:
        raise PlanRejected('Exact authenticated enqueue receipt required')
    receipt = json.loads(row[0]); unsigned = dict(receipt); seal = unsigned.pop('enqueue_seal', None)
    if not isinstance(seal, str) or not hmac.compare_digest(seal, state._mac('authenticated-face-enqueue', unsigned)):
        raise PlanRejected('Enqueue receipt changed')
    if (receipt['operation'] != OPERATION or receipt['task_id'] != task_id
            or receipt['plan_id'] != plan_id or receipt['plan_digest'] != digest
            or receipt['database_identity'] != list(database_identity)):
        raise PlanRejected('Enqueue target changed')
    envelope = receipt['authenticated_plan']
    if envelope['plan']['plan_id'] != plan_id or hashlib.sha256(_json(envelope)).hexdigest() != digest:
        raise PlanRejected('Enqueue plan changed')
    state._executing_face_task = task_id
    state._validate_in_transaction(envelope)
    task = state.access.db.execute('SELECT type,payload_json,state,cancel_requested,scheduled_at FROM tasks WHERE id=?', (task_id,)).fetchone()
    target = envelope['plan']['target']
    if (not task or task[0] != target['kind'] or json.loads(task[1]) != target['payload']
            or task[2] != 'pending' or task[3] or task[4] is not None):
        raise PlanRejected('Exact pending task required')
    if state.access.db.execute('SELECT 1 FROM access_audit WHERE action=?', ('face.batch.' + str(task_id),)).fetchone():
        raise PlanRejected('Batch already committed')
    return envelope
