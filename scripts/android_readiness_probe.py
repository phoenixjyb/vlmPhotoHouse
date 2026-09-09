#!/usr/bin/env python3
"""Source/ASGI-only readiness evidence; no host, listener or real-data discovery.

Use the existing backend root .venv Python. --mobile-root is a source checkout.
--candidate explicitly reviews the two caption-budget source changes without
changing the consumer pin. Optional caption output contains synthetic JSON only.
Exit 1 is deliberate when a valid server payload exceeds the Android JSON budget.
It is a reported compatibility finding, not a skipped or expected-passing test.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PIN = '1e394f789ff1f7cef6d9930bb541186684f5a9a0'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mobile-root', required=True, type=Path)
    parser.add_argument('--candidate', action='store_true')
    parser.add_argument('--caption-output', type=Path)
    args = parser.parse_args()
    mobile = args.mobile_root.resolve()
    manifest = json.loads((mobile/'contracts/v1/manifest.json').read_text())
    assert manifest['backend_commit'] == PIN
    changed = {}
    for name, expected in manifest['backend_sources'].items():
        actual = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        if actual != expected:
            assert args.candidate and name in {
                'backend/app/access/library.py', 'tests/security/test_library_reads.py'
            }, 'Unreviewed backend source drift'
            changed[name] = actual
    backend_head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    subprocess.run(['git','merge-base','--is-ancestor',PIN,backend_head],cwd=ROOT,check=True)
    app_changes = subprocess.check_output(['git','diff','--name-only',PIN,'--','backend/app'],
        cwd=ROOT,text=True).splitlines()
    assert set(app_changes) <= ({'backend/app/access/library.py'} if args.candidate else set()), 'Unreviewed application drift'
    source_dirty = bool(subprocess.check_output(['git','diff','HEAD','--name-only','--',
        *manifest['backend_sources']],cwd=ROOT,text=True).strip())
    for name, expected in manifest['files'].items():
        assert hashlib.sha256((mobile/'contracts/v1'/name).read_bytes()).hexdigest() == expected, 'Contract drift'
    adapter = mobile/'android/live-core/src/main/kotlin/dev/photohouse/connected/core/HttpsPhotoHouseApi.kt'
    source = adapter.read_text()
    json_limit = int(re.search(r'const val JSON_LIMIT = (\d+)', source)[1])
    mobile_head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=mobile,text=True).strip()
    artifact = mobile/'android/connected/build/outputs/apk/debug/connected-debug.apk'
    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest() if artifact.is_file() else None
    report = {'task':'PH-BACKEND-ANDROID-READINESS-01','backend_commit':backend_head,
        'consumer_pinned_backend_commit':PIN, 'candidate_review':args.candidate,
        'checked_source_worktree_dirty':source_dirty,
        'candidate_source_checksums':changed,
        'mobile_handoff_head':mobile_head,'contract_version':manifest['contract_version'],
        'unchanged_source_checksums_verified':len(manifest['backend_sources'])-len(changed),
        'contract_checksums_verified':len(manifest['files']),
        'local_connected_apk_sha256':artifact_hash,
        'deployed':'unknown','https_origin':None,'live_database_checked':False,
        'physical_device_checked':False,'listeners_opened':False,
        'android_json_limit_bytes':json_limit}
    sys.path[:0] = [str(ROOT/'backend'),str(ROOT/'tests/security')]
    if args.caption_output:
        args.caption_output.mkdir(parents=True, exist_ok=False)
    caption_cases = []
    def capture(name, response):
        if args.caption_output:
            (args.caption_output/(name+'.json')).write_bytes(response.content)
        body = response.json()
        caption_cases.append({'name':name, 'bytes':len(response.content),
            'items':len(body['items']), 'has_more':body['has_more'],
            'truncated':any(item['truncated'] for item in body['items'])})
    with ExitStack() as guards:
        for target in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system'):
            guards.enter_context(patch(target,side_effect=AssertionError('External I/O forbidden')))
        import test_library_reads as fixture
        from app.access.runtime import RuntimeConfiguration, REQUIRED_REVISION
        from app.main import create_app
        from fastapi.testclient import TestClient
        from test_access_foundation import NOW
        fixture.LibraryReadTests.setUpClass()
        try:
            db = fixture.LibraryReadTests.template
            database = Path(db.execute('PRAGMA database_list').fetchone()[2])
            app = RuntimeConfiguration(database=database,web_origin='https://photohouse.test',
                original_roots=(database.parent/'unused-originals',),
                derived_root=database.parent/'unused-derived').build_app(clock=lambda:NOW)
            report['required_migration_revision'] = REQUIRED_REVISION
            headers = {'Authorization':'Bearer '+fixture.LibraryReadTests.member_token}
            with TestClient(create_app(),base_url='https://photohouse.test') as closed:
                result=closed.get('/auth/session',headers=headers)
                assert result.status_code == 503
                report['unconfigured_entry_point_status'] = result.status_code
            with TestClient(app,base_url='https://photohouse.test') as client:
                small=client.get('/assets/101/captions?library=family-a',headers=headers)
                assert small.status_code==200 and len(small.content)<json_limit
                report['small_caption_status']=small.status_code
                report['small_caption_bytes']=len(small.content)
                capture('small', small)
                db.execute('DELETE FROM captions WHERE asset_id=101')
                db.executemany('''INSERT INTO captions(id,asset_id,text,model,user_edited,superseded)
                    VALUES (?,101,?,'synthetic',0,0)''',
                    [(10000+i,'\U0001f7e6'*8192) for i in range(20)])
                db.commit()
                large=client.get('/assets/101/captions?library=family-a',headers=headers)
                assert large.status_code==200 and 0 < len(large.json()['items']) <= 20
                assert all(len(item['text'])==8192 for item in large.json()['items'])
                assert large.json()['has_more'] == (len(large.json()['items']) < 20)
                report['maximum_caption_status']=large.status_code
                report['maximum_caption_bytes']=len(large.content)
                report['caption_budget_compatible']=len(large.content)<=json_limit
                capture('unicode', large)
                if args.candidate:
                    def seed(texts):
                        db.execute('DELETE FROM captions WHERE asset_id=101')
                        db.executemany('''INSERT INTO captions(id,asset_id,text,model,user_edited,superseded)
                            VALUES (?,101,?,'synthetic',0,0)''',
                            [(10000+i,text) for i,text in enumerate(texts)])
                        db.commit()
                    for name,texts in [('escaped',['\x01'*8192]*20),
                                       ('truncated',['\U0001f7e6'*9000]*21), ('empty',[])]:
                        seed(texts)
                        response=client.get('/assets/101/captions?library=family-a',headers=headers)
                        assert response.status_code==200 and len(response.content)<=json_limit
                        capture(name,response)
                    seed(['']+['x'*8192]*3+['\x01'*8192]*10)
                    response=client.get('/assets/101/captions?library=family-a',headers=headers)
                    remaining=json_limit-len(response.content)
                    assert 0 < remaining < 8192
                    db.execute('UPDATE captions SET text=? WHERE id=10000',('x'*remaining,)); db.commit()
                    exact=client.get('/assets/101/captions?library=family-a',headers=headers)
                    assert exact.status_code==200 and len(exact.content)==json_limit
                    capture('exact',exact)
                    if args.caption_output:
                        # Valid JSON with trailing whitespace, one byte over the
                        # budget: negative client test independent of the fix.
                        (args.caption_output/'oversized.json').write_bytes(exact.content+b' ')
                # The direct-TLS proposal must not rely on spoofed forwarding.
                forged=client.get('/auth/session',headers=headers|{'Host':'untrusted.test','X-Forwarded-Host':'photohouse.test','X-Forwarded-Proto':'https'})
                assert forged.status_code==400
                report['forged_host_status']=forged.status_code
                with TestClient(app,base_url='http://photohouse.test') as insecure:
                    response=insecure.get('/auth/session',headers=headers|{'X-Forwarded-Proto':'https'})
                    assert response.status_code==400
                    report['http_with_forwarded_https_status']=response.status_code
            report['physical_phone_gate']='NO_GO_UNTIL_STAGING_AND_AUDIENCE_VERIFIED'
        finally:
            fixture.LibraryReadTests.tearDownClass()
    report['caption_cases'] = caption_cases
    print(json.dumps(report,indent=2))
    return 0 if report['caption_budget_compatible'] else 1


if __name__=='__main__':
    raise SystemExit(main())
