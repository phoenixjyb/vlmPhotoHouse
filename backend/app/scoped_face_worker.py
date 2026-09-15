"""Bounded library-owned face assignment; no inference, startup DDL or file writes.

Only explicitly selected versioned artifacts are read. Manual labels are anchors,
never candidates. A failed batch rolls back even if the queue commits its error.
"""
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import time
import uuid

from sqlalchemy import text


class AssignmentRefused(ValueError):
    """Sanitized permanent refusal; no paths, names or vectors in queue errors."""


KINDS = {'person_cluster', 'person_recluster', 'person_label_propagate'}
REQUIRED = {'library_id', 'operator_account_id', 'embedding_model', 'embedding_version',
            'embedding_dim', 'embedding_alignment', 'embedding_status'}
OPTIONAL = {'max_faces', 'score_threshold', 'margin', 'min_ref_faces', 'person_ids'}
TABLES = {'face_assignment_events', 'face_embedding_artifacts', 'person_embedding_artifacts',
          'access_person_libraries', 'access_asset_libraries', 'access_accounts',
          'access_libraries', 'access_memberships', 'access_operators', 'access_audit',
          'persons', 'face_detections', 'assets', 'tasks'}


def _payload(value, kind):
    if not isinstance(value, dict) or not REQUIRED <= value.keys() or value.keys() - REQUIRED - OPTIONAL:
        raise AssignmentRefused('Explicit scoped assignment payload required')
    p = dict(value)
    if not isinstance(p['library_id'], str) or not re.fullmatch('[a-z0-9][a-z0-9_-]{2,63}', p['library_id']):
        raise AssignmentRefused('Invalid library scope')
    try:
        if str(uuid.UUID(p['operator_account_id'])) != p['operator_account_id']:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise AssignmentRefused('Explicit operator required') from None
    for key, maximum in (('embedding_model', 128), ('embedding_version', 96)):
        if not isinstance(p[key], str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,' + str(maximum) + '}', p[key]):
            raise AssignmentRefused('Invalid embedding identity')
    if p['embedding_model'].lower().startswith('unknown'):
        raise AssignmentRefused('Unknown legacy vector provenance is not qualified')
    alignment = p['embedding_alignment']
    if alignment is not None and (not isinstance(alignment, str) or not re.fullmatch('[A-Za-z0-9_.-]{1,64}', alignment)):
        raise AssignmentRefused('Invalid embedding alignment')
    if p['embedding_status'] not in ('active', 'legacy'):
        raise AssignmentRefused('Shadow artifacts cannot assign people')
    for key, default, maximum in (('embedding_dim', None, 4096), ('max_faces', 100, 500), ('min_ref_faces', 2, 50)):
        p.setdefault(key, default)
        if type(p[key]) is not int or not 1 <= p[key] <= maximum:
            raise AssignmentRefused('Invalid assignment bound')
    for key, default in (('score_threshold', .82), ('margin', .015)):
        p.setdefault(key, default)
        if type(p[key]) not in (int, float) or not math.isfinite(p[key]) or not 0 <= p[key] <= 1:
            raise AssignmentRefused('Invalid matching threshold')
    ids = p.setdefault('person_ids', [])
    if not isinstance(ids, list) or len(ids) > 100 or any(type(i) is not int or not 0 < i < 2**63 for i in ids) or len(set(ids)) != len(ids):
        raise AssignmentRefused('Invalid target people')
    if (kind == 'person_label_propagate') != bool(ids):
        raise AssignmentRefused('Only propagation requires explicit target people')
    return p


def _unit(values):
    if not all(math.isfinite(v) for v in values):
        raise AssignmentRefused('Invalid face vector')
    norm = math.sqrt(sum(v * v for v in values))
    if not math.isfinite(norm) or norm < 1e-12:
        raise AssignmentRefused('Invalid face vector')
    return tuple(v / norm for v in values)


def _vector(root, path, checksum, dimension):
    """Read a small, checksum-bound numeric NPY without pickle or model imports."""
    if not isinstance(path, str) or not 0 < len(path) <= 4096 or not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum):
        raise AssignmentRefused('Unqualified vector artifact')
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        if '..' in candidate.parts or candidate.resolve(strict=True) != candidate or not candidate.is_relative_to(root):
            raise AssignmentRefused('Vector outside reviewed root')
        with candidate.open('rb') as stream:
            data = stream.read(65537)
        if len(data) > 65536 or hashlib.sha256(data).hexdigest() != checksum:
            raise AssignmentRefused('Vector artifact changed')
        if data[:6] != b'\x93NUMPY' or data[6:8] not in (b'\x01\x00', b'\x02\x00'):
            raise AssignmentRefused('Unsupported vector encoding')
        prefix = 10 if data[6] == 1 else 12
        size = int.from_bytes(data[8:prefix], 'little')
        if not 0 < size <= 4096:
            raise AssignmentRefused('Invalid vector header')
        header = ast.literal_eval(data[prefix:prefix + size].decode('ascii'))
        if (not isinstance(header, dict) or set(header) != {'descr', 'fortran_order', 'shape'}
                or header['shape'] != (dimension,) or header['fortran_order'] is not False
                or header['descr'] not in ('<f4', '<f8', '>f4', '>f8')):
            raise AssignmentRefused('Vector identity mismatch')
        fmt = header['descr'][0] + str(dimension) + ('f' if header['descr'][2] == '4' else 'd')
        return _unit(struct.unpack(fmt, data[prefix + size:]))
    except (OSError, ValueError, SyntaxError, struct.error, UnicodeError, RecursionError):
        raise AssignmentRefused('Vector artifact unavailable or invalid') from None


def run_scoped_assignment(session, task, *, embedding_root, clock=time.time, commit=True):
    if task.type not in KINDS:
        raise AssignmentRefused('Unsupported assignment job')
    p = _payload(task.payload_json, task.type)
    if session.new or session.dirty or session.deleted:
        raise AssignmentRefused('Clean claimed-task session required')
    try:
        root = Path(embedding_root)
        if not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir():
            raise ValueError()
    except (OSError, TypeError, ValueError):
        raise AssignmentRefused('Explicit direct vector root required') from None
    connection = session.connection()
    if connection.dialect.name != 'sqlite':
        raise AssignmentRefused('Qualified SQLite worker required')
    raw = connection.connection.driver_connection
    # SQLAlchemy's logical transaction may not have begun a SQLite transaction.
    # Start before SAVEPOINT so release cannot commit a partial outer operation.
    if not raw.in_transaction:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
    deadline = time.monotonic() + 10
    raw.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    try:
        with session.begin_nested():
            result = _run(session, task, p, root, clock, deadline)
        if commit:
            session.commit()
        session.expire_all()
        return result
    except AssignmentRefused:
        raise
    except Exception:
        raise AssignmentRefused('Scoped assignment failed; batch rolled back') from None
    finally:
        raw.set_progress_handler(None, 0)


def assignment_selection(rows, p, kind):
    """Same bounded metadata selection for private planning and execution."""
    # Reject whole shared identities, not merely the foreign faces of their pool.
    owned_rows = rows('''SELECT o.person_id,o.revision,o.creator_id FROM access_person_libraries o
        WHERE o.library_id=:library AND NOT EXISTS (
            SELECT 1 FROM face_detections f LEFT JOIN access_asset_libraries s ON s.asset_id=f.asset_id
            WHERE f.person_id=o.person_id AND (s.library_id IS NULL OR s.library_id<>:library))
        ORDER BY o.person_id LIMIT 1001''', library=p['library_id'])
    owned = {row[0] for row in owned_rows}
    if len(owned) > 1000 or not set(p['person_ids']) <= owned:
        raise AssignmentRefused('Target ownership or people budget invalid')
    # Loading a legacy Person.embedding_path would reintroduce a global centroid.
    base = '''SELECT f.id,f.asset_id,f.person_id,f.label_source,f.label_score,e.storage_path,e.vector_checksum,a.hash_sha256
        FROM face_detections f JOIN assets a ON a.id=f.asset_id
        JOIN access_asset_libraries s ON s.asset_id=a.id
        JOIN face_embedding_artifacts e ON e.face_id=f.id
        WHERE s.library_id=:library AND (a.status IS NULL OR a.status='active')
        AND e.model=:model AND e.model_version=:version AND e.dim=:dim
        AND e.alignment IS :alignment AND e.status=:status '''
    params = dict(library=p['library_id'], model=p['embedding_model'], version=p['embedding_version'],
                  dim=p['embedding_dim'], alignment=p['embedding_alignment'], status=p['embedding_status'])
    refs = rows(base + " AND f.label_source='manual' AND f.person_id IS NOT NULL ORDER BY f.id LIMIT 2001", **params)
    if len(refs) > 2000:
        raise AssignmentRefused('Reference budget exceeded')
    candidates = rows(base + " AND (f.label_source IS NULL OR f.label_source<>'manual') "
        + (" AND (f.person_id IS NULL OR f.label_source='dnn') " if kind == 'person_recluster' else ' AND f.person_id IS NULL ')
        + ' ORDER BY f.id LIMIT :limit', limit=p['max_faces'], **params)
    return owned_rows, refs, candidates


def _run(session, task, p, root, clock, deadline):
    def budget():
        if time.monotonic() > deadline:
            raise AssignmentRefused('Assignment batch budget exceeded')

    def execute(sql, **params):
        budget()
        return session.execute(text(sql), params)

    tables = set(execute("SELECT name FROM sqlite_master WHERE type='table'").scalars())
    if not TABLES <= tables or execute('SELECT version_num FROM alembic_version').all() != [('d8e5b2f7a904',)]:
        raise AssignmentRefused('Migrated assignment schema required')
    if execute('PRAGMA foreign_keys').scalar() != 1:
        raise AssignmentRefused('Foreign keys must be enabled')
    # This write reservation serializes the entire bounded match/mutation batch.
    row = execute("SELECT state,cancel_requested,type,payload_json FROM tasks WHERE id=:id", id=task.id).first()
    if not row or row[0] != 'running' or row[2] != task.type or _payload(json.loads(row[3]), row[2]) != p:
        raise AssignmentRefused('Claimed task required')
    batch_action = 'face.batch.' + str(task.id)
    if execute('SELECT 1 FROM access_audit WHERE action=:action LIMIT 1', action=batch_action).first():
        raise AssignmentRefused('Batch already committed; inspect existing audit')
    if row[1]:
        execute("UPDATE tasks SET state='canceled' WHERE id=:id", id=task.id)
        return {'assigned': 0, 'canceled': True}
    execute("UPDATE tasks SET progress_current=progress_current WHERE id=:id", id=task.id)

    def authority():
        if not execute('''SELECT 1 FROM access_memberships m JOIN access_accounts a ON a.id=m.account_id
            JOIN access_operators o ON o.account_id=a.id JOIN access_libraries l ON l.id=m.library_id
            WHERE m.account_id=:actor AND m.library_id=:library AND m.role='owner' AND m.status='approved'
            AND a.state='active' AND l.state='active' AND (m.expires_at IS NULL OR m.expires_at>:now)''',
            actor=p['operator_account_id'], library=p['library_id'], now=int(clock())).first():
            raise AssignmentRefused('Current library owner and operator required')
    authority()
    owned_rows, refs, candidates = assignment_selection(lambda sql, **params: execute(sql, **params).all(), p, task.type)
    owned = {row[0] for row in owned_rows}
    sums, counts = {}, {}
    for ref in refs:
        budget()
        pid = ref[2]
        if pid not in owned:
            continue
        vector = _vector(root, ref[5], ref[6], p['embedding_dim'])
        sums[pid] = [a + b for a, b in zip(sums.get(pid, [0.] * len(vector)), vector)]
        counts[pid] = counts.get(pid, 0) + 1
    centroids = {pid: _unit(values) for pid, values in sums.items() if counts[pid] >= p['min_ref_faces']}
    assigned, created, affected = 0, 0, set()
    for face in candidates:
        budget()
        fid, asset, previous, source, old_score = face[:5]
        if previous is not None and previous not in owned:
            continue
        vector = _vector(root, face[5], face[6], p['embedding_dim'])
        scores = []
        for pid, centroid in centroids.items():
            budget()
            scores.append((sum(a * b for a, b in zip(vector, centroid)), pid))
        scores.sort(reverse=True)
        best = scores[0] if scores else None
        second = scores[1][0] if len(scores) > 1 else -1.
        matched = best and best[0] >= p['score_threshold'] and best[0] - second >= p['margin']
        if task.type == 'person_label_propagate' and (not matched or best[1] not in p['person_ids']):
            continue
        if matched:
            score, pid = best
        else:
            pid = execute('INSERT INTO persons(face_count) VALUES (0)').lastrowid
            execute('''INSERT INTO access_person_libraries(person_id,library_id,creator_id,revision)
                VALUES (:pid,:library,:actor,1)''', pid=pid, library=p['library_id'], actor=p['operator_account_id'])
            owned.add(pid); centroids[pid] = vector; created += 1; score = 1.
        if previous == pid and source == 'dnn':
            continue
        changed = execute('''UPDATE face_detections SET person_id=:pid,label_source='dnn',label_score=:score
            WHERE id=:id AND person_id IS :previous AND label_source IS :source
            AND (label_source IS NULL OR label_source<>'manual')''', pid=pid, score=score, id=fid, previous=previous, source=source)
        if changed.rowcount != 1:
            raise AssignmentRefused('Face assignment changed')
        execute('''INSERT INTO face_assignment_events(face_id,asset_id,old_person_id,new_person_id,
            old_label_source,new_label_source,old_label_score,new_label_score,source,reason,task_id,actor)
            VALUES (:face,:asset,:old,:new,:source,'dnn',:old_score,:score,'dnn',:reason,:task,:actor)''',
            face=fid, asset=asset, old=previous, new=pid, source=source, old_score=old_score, score=score,
            reason='worker.scoped.' + task.type, task=task.id, actor=p['operator_account_id'])
        assigned += 1; affected.add(pid)
        if previous is not None:
            affected.add(previous)
    for pid in sorted(affected):
        execute('''UPDATE persons SET face_count=(SELECT count(*) FROM face_detections WHERE person_id=:pid),
            embedding_path=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=:pid''', pid=pid)
        execute("UPDATE person_embedding_artifacts SET status='stale' WHERE person_id=:pid", pid=pid)
        execute('UPDATE access_person_libraries SET revision=revision+1 WHERE person_id=:pid', pid=pid)
    authority()
    execute('''UPDATE tasks SET progress_current=:n,progress_total=:n WHERE id=:id''', n=len(candidates), id=task.id)
    execute('''INSERT INTO access_audit(actor_account,action,library_id,target_account,occurred_at)
        VALUES (:actor,:action,:library,NULL,:now)''', actor=p['operator_account_id'],
        action=batch_action, library=p['library_id'], now=int(clock()))
    return {'assigned': assigned, 'new_persons': created, 'scanned': len(candidates), 'library_id': p['library_id']}
