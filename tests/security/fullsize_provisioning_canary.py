"""New-copy-only operator qualification. Uses fictional credentials, never a service.

Requires an already quarantined, migrated, offline source and an existing private
work directory. Retains copies; never opens network, media or the live database.
"""
from contextlib import closing, redirect_stdout, ExitStack
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from unittest.mock import patch

source_root, source_path, work = (Path(arg).resolve(strict=True) for arg in sys.argv[1:4])
sys.path[:0] = [str(source_root/'backend'), str(source_root/'scripts')]
import provision_access as cli
from app.access.runtime import ExistingDatabase
from app.access.recovery import _assert_quarantined, _quarantine_access_state

target = work/'owner-canary.sqlite'
def call(*args):
    output = io.StringIO()
    with redirect_stdout(output):
        assert cli.main(list(map(str, args))) == 0, 'Operator qualification failed'
    return json.loads(output.getvalue())

with ExitStack() as guards:
    for name in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen', 'os.system'):
        guards.enter_context(patch(name, side_effect=AssertionError('External I/O forbidden')))
    with ExistingDatabase(source_path, read_only=True)() as source:
        source.execute('PRAGMA query_only=ON'); source.execute('BEGIN')
        assert source.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
        assert not any(Path(str(source_path)+suffix).exists() for suffix in ('-wal','-shm','-journal'))
        _assert_quarantined(source, source.execute('SELECT secret FROM access_admission_key WHERE id=1').fetchone()[0])
        with target.open('xb'):
            pass
        with closing(sqlite3.connect(target)) as db:
            source.backup(db)
    request, plan = work/'synthetic-owner-request.json', work/'synthetic-owner-plan.json'
    with request.open('x') as f:
        json.dump({'phone_login': '+12025550199', 'library_id': 'synthetic-owner-qualification'}, f)
    planned = call('plan-owner', '--database', target, '--request', request, '--out', plan)
    args = ['--database', target, '--plan', plan, '--backup', source_path,
            '--reviewed-plan-digest', planned['plan_digest'],
            '--authority-reference', 'synthetic-owner-qualification',
            '--restore-reference', 'fullsize-copy-only-qualification']
    try:
        reviewed = call('review', *args, '--restore-out', work/'review-restore.sqlite')
        with patch('getpass.getpass', return_value='Synthetic qualification passphrase only!'):
            applied = call('apply', *args, '--restore-out', work/'apply-restore.sqlite',
                           '--review-digest', reviewed['review_digest'])
        receipt = call('receipt', '--database', target, '--plan-id', planned['plan_id'],
                       '--reviewed-plan-digest', planned['plan_digest'])
        assert applied['applied'] and receipt['receipt_found']
        with ExistingDatabase(target, read_only=True)() as db:
            assert db.execute('SELECT count(*) FROM access_accounts WHERE state="active"').fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM access_sessions').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM access_asset_libraries').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM access_memberships WHERE originals=1').fetchone()[0] == 0
    finally:
        with ExistingDatabase(target)() as db:
            db.execute('BEGIN IMMEDIATE'); key = _quarantine_access_state(db)
            _assert_quarantined(db, key); db.commit()
    print(json.dumps({'owner_canary': 'pass', 'disk_reviews': 2, 'receipt_found': True,
                      'real_owner_created': False, 'source_modified': False,
                      'synthetic_owner_quarantined': True, 'activated': False}))
