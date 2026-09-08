"""Audit and apply bounded, history-preserving bilingual Qwen3 caption refreshes.

Audit is read-only except for a new plan. Apply requires an idle normal queue,
an explicit limit and a new receipt. It uses the existing Windows HTTP model;
it does not restart the API, alter schedules, or load any embedding models.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.request


def fingerprint(captions):
    return hashlib.sha256(json.dumps(sorted(captions), ensure_ascii=True).encode()).hexdigest()


def reason_for(captions):
    # All historical user edits are protected, including superseded edits.
    if any(c[3] for c in captions):
        return None
    current = [c for c in captions if not c[4] and c[1].strip()]
    if not current:
        return 'missing'
    for _, text, model, _, _ in current:
        if model.startswith('qwen3-vl-http|bilingual'):
            match = re.fullmatch(r'\s*EN:\s*(.+?)\s*\n\s*\n\s*ZH-CN:\s*(.+?)\s*', text, re.S)
            if match and re.search(r'[\u4e00-\u9fff]', match[2]):
                # Selection heuristic for legacy one-liners, NOT an output limit.
                english = match[1]
                if len(english.split()) >= 30 or len(re.findall(r'[.!?](?:\s|$)', english)) >= 2:
                    return None
    return 'replace_old_or_short'


def caption_rows(con, asset_id):
    return con.execute('select id,text,model,user_edited,superseded from captions where asset_id=?', (asset_id,)).fetchall()


def audit(database):
    grouped = defaultdict(list)
    with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True)) as con:
        con.execute('begin')
        for row in con.execute('select asset_id,id,text,model,user_edited,superseded from captions'):
            grouped[row[0]].append(row[1:])
        assets = con.execute("select id,path,mime,file_size from assets where status='active' order by id").fetchall()
        unreadable = {r[0] for r in con.execute("select json_extract(payload_json,'$.asset_id') from tasks where type='face' and state='failed'")}
    selected, excluded = [], Counter()
    for aid, path, mime, size in assets:
        why = reason_for(grouped[aid])
        if why is None:
            excluded['current_or_user_edited'] += 1
            continue
        p = Path(path)
        if p.name.startswith('._') or aid in unreadable:
            excluded['unreadable_or_sidecar'] += 1
            continue
        try:
            st = p.stat()
            if not p.is_file() or (size is not None and size != st.st_size):
                raise ValueError('size mismatch')
        except (OSError, ValueError):
            excluded['missing_or_changed'] += 1
            continue
        selected.append({'asset_id': aid, 'path': path, 'mime': mime, 'reason': why,
                         'signature': [st.st_size, st.st_mtime_ns],
                         'caption_fingerprint': fingerprint(grouped[aid])})
    return {'schema': 1, 'database': str(database.resolve()), 'created_at': datetime.now().isoformat(),
            'candidates': selected, 'excluded': dict(excluded),
            'summary': dict(Counter((i['mime'] or 'unknown').split('/')[0]+':'+i['reason'] for i in selected))}


def emit(log, event):
    log.write(json.dumps(event, ensure_ascii=True)+'\n')
    log.flush()
    os.fsync(log.fileno())
    print(json.dumps(event, ensure_ascii=True), flush=True)


def apply(plan, data_root, receipt, limit, asset_ids=None):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from app.db import Asset, Caption, Task
    from app.tasks import TaskExecutor

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:8102/health', timeout=10) as response:
        health = json.load(response)
    if health.get('active_provider') != 'qwen3-vl' or not health.get('model_cache_ready'):
        raise RuntimeError('Expected the ready loopback Qwen3-VL service')
    database = Path(plan['database'])
    engine = create_engine('sqlite:///'+database.as_posix(), connect_args={'timeout': 30})
    sessions = sessionmaker(bind=engine)
    # Only caption methods are used: do not initialize general/face embeddings.
    executor = TaskExecutor.__new__(TaskExecutor)
    lock = data_root/'caption-refresh.lock'
    candidates = [i for i in plan['candidates'] if asset_ids is None or i['asset_id'] in asset_ids]
    if asset_ids is not None and {i['asset_id'] for i in candidates} != asset_ids:
        raise ValueError('Explicit IDs must all be eligible in the saved plan')
    counts = Counter()
    consecutive_failures = 0
    lock_handle = lock.open('x')
    try:
        lock_handle.write(str(os.getpid()))
        lock_handle.flush()
        with receipt.open('x', encoding='utf-8') as log:
            for item in candidates:
                if counts['attempted'] >= limit:
                    break
                aid = item['asset_id']
                with sessions() as session:
                    session.execute(text('BEGIN IMMEDIATE'))
                    if session.query(Task).filter(Task.state.in_(['pending', 'running'])).count():
                        session.rollback()
                        counts['stopped_busy'] += 1
                        emit(log, {'event': 'stopped', 'reason': 'normal_queue_not_idle'})
                        break
                    asset = session.get(Asset, aid)
                    caps = session.query(Caption).filter(Caption.asset_id == aid).all()
                    rows = [(c.id,c.text,c.model,c.user_edited,c.superseded) for c in caps]
                    path = Path(item['path'])
                    try:
                        stat = path.stat()
                        unchanged = [stat.st_size,stat.st_mtime_ns] == item['signature']
                    except OSError:
                        unchanged = False
                    if (not asset or asset.status != 'active' or asset.path != item['path'] or not unchanged
                            or fingerprint(rows) != item['caption_fingerprint'] or reason_for(rows) is None):
                        session.rollback()
                        counts['skipped_changed'] += 1
                        emit(log, {'event': 'skipped_changed', 'asset_id': aid})
                        continue
                    task = Task(type='caption', state='running', priority=110, started_at=datetime.utcnow(),
                                payload_json={'asset_id': aid, 'force': True, 'replace_generated': True,
                                              'refresh_batch': receipt.name})
                    session.add(task)
                    session.commit()
                    tid = task.id
                    counts['attempted'] += 1
                    emit(log, {'event': 'started', 'asset_id': aid, 'task_id': tid})
                    try:
                        result = executor._handle_caption(session, task)
                        task = session.get(Task, tid)
                        if result is None or result.user_edited:
                            task.state = 'canceled'
                            counts['protected'] += 1
                        else:
                            task.state = 'finished'
                            counts['refreshed'] += 1
                        consecutive_failures = 0
                        task.finished_at = datetime.utcnow()
                        session.commit()
                        emit(log, {'event': task.state, 'asset_id': aid, 'task_id': tid,
                                   'caption_id': result.id if result else None})
                    except Exception as exc:
                        session.rollback()
                        task = session.get(Task, tid)
                        task.state = 'failed'
                        task.last_error = str(exc)[:4000]
                        task.finished_at = datetime.utcnow()
                        session.commit()
                        counts['failed'] += 1
                        consecutive_failures += 1
                        emit(log, {'event': 'failed', 'asset_id': aid, 'task_id': tid,
                                   'error_type': type(exc).__name__})
                        if isinstance(exc, (ConnectionError, OSError)) or consecutive_failures >= 3:
                            emit(log, {'event': 'stopped', 'reason': 'failure_guard'})
                            break
            emit(log, {'event': 'complete', **counts})
    finally:
        lock_handle.close()
        lock.unlink()
        engine.dispose()
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--asset-ids', help='Comma-separated exact canary IDs')
    args = parser.parse_args()
    if not args.apply:
        plan = audit(args.database)
        with args.plan.open('x', encoding='utf-8') as out:
            json.dump(plan, out, ensure_ascii=True, indent=2)
        print(json.dumps({'summary': plan['summary'], 'excluded': plan['excluded'], 'total': len(plan['candidates'])}))
        return
    if not args.receipt or not args.data_root or not args.limit or not 1 <= args.limit <= 100:
        parser.error('Apply requires --receipt, --data-root and --limit 1..100')
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    if Path(plan['database']).resolve() != args.database.resolve():
        raise ValueError('Plan database mismatch')
    os.environ.update(DATABASE_URL='sqlite:///'+args.database.resolve().as_posix(),
                      VLM_DATA_ROOT=str(args.data_root), DERIVED_PATH=str(args.data_root/'derived'),
                      CAPTION_PROVIDER='http', CAPTION_SERVICE_URL='http://127.0.0.1:8102',
                      CAPTION_EXTERNAL_DIR='', CAPTION_WORD_LIMIT='0', CAPTION_ENABLE_STUB_FALLBACK='false',
                      CAPTION_AUTO_TAG_ENABLE='false', ENABLE_INLINE_WORKER='false')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
    from app.caption_policy import DEFAULT_DETAILED_CAPTION_PROMPT
    os.environ['CAPTION_PROMPT'] = DEFAULT_DETAILED_CAPTION_PROMPT
    ids = {int(i) for i in args.asset_ids.split(',')} if args.asset_ids else None
    counts = apply(plan, args.data_root, args.receipt, args.limit, ids)
    if counts['failed']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
