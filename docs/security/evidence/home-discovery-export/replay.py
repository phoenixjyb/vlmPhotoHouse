#!/usr/bin/env python3
"""Fresh synthetic review/export and disabled/enabled ASGI, without listening."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root',type=Path,required=True)
args=parser.parse_args();root=args.source_root.resolve(strict=True)
sys.path[:0]=[str(root/'scripts'),str(root/'backend')]
import export_home_discovery as exp
from build_home_discovery_export_fixture import create
from app.home_discovery import Configuration,create_home_discovery
from fastapi.testclient import TestClient

checks=[]
with tempfile.TemporaryDirectory(prefix='discovery-export-replay-') as temporary, ExitStack() as stack:
    for target in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system'):
        stack.enter_context(patch(target,side_effect=AssertionError('External state forbidden')))
    f=create(Path(temporary).resolve()/'fixture'); db=f/'snapshot.sqlite'; candidate=f/'candidate';request=f/'request.json'
    before={p.relative_to(f).as_posix():exp.sha(p.read_bytes()) for p in f.rglob('*') if p.is_file()}
    receipt=exp.review(db,candidate,request,f/'review.json')
    # Test-only approval over the fixture created above, never an existing input.
    approval={'version':1,'plan_sha256':receipt['plan_sha256'],**{k:True for k in ('approve_selection','approve_roster','approve_assignments','approve_regions','approve_metadata')}}
    (f/'synthetic-approval.json').write_bytes(exp.packed(approval))
    output=exp.publish(db,candidate,request,f/'review.json',f/'synthetic-approval.json',f/'published')
    assert output['enabled'] is False
    checks.append('explicit_review_produces_disabled_bundle')
    assert all(exp.sha((f/name).read_bytes())==digest for name,digest in before.items())
    checks.append('snapshot_request_candidate_unchanged')
    publication=f/'published'; control_path=publication/'control.json'; disabled=control_path.read_bytes()
    assert all(exp.sha((publication/name).read_bytes())==digest for name,digest in output['output_hashes'].items())
    checks.append('all_output_hashes_verified')
    config=Configuration(control_path,publication/'prepared','https://home.photohouse.test:18444',('192.168.40.0/24',))
    app=create_home_discovery(config,publication/'discovery.json',output['output_hashes']['discovery.json'])
    with TestClient(app,base_url=config.origin,client=('192.168.40.20',1)) as client:
        for path in ('/home/v2/catalog','/home/discovery/v1/facets'):
            assert client.get(path).status_code==403
        checks.append('catalog_and_discovery_disabled')
        control=json.loads(disabled);control['enabled']=True;control_path.write_bytes(exp.packed(control))
        catalog=client.get('/home/v2/catalog').json()
        facets=client.get('/home/discovery/v1/facets').json()
        assert facets['library']==catalog['library'] and facets['catalog_revision']==catalog['revision']
        assert facets['pinned_person_ids']==[202,201] and facets['capabilities']['filters']['people']['assets_with_values']==2
        checks.append('library_revisions_pins_and_reviewed_people_coverage')
        def query(filters):return client.post('/home/discovery/v1/search',json={'revision':7,'page':1,'page_size':50,'filters':filters})
        response=query({'people':{'ids':[201,202],'match':'all'},'caption':'family','tags':{'ids':[301,302],'match':'all'},'locations':[401],'date':{'from':'2025-12-01','to':'2025-12-01'},'media':['photo']})
        assert response.status_code==200 and [a['id'] for a in response.json()['items']]==[103]
        checks.append('all_combined_filters')
        assert query({'people':{'ids':[201],'match':'any'},'caption':'sample child'}).json()['items']==[]
        checks.append('dnn_and_caption_do_not_become_reviewed_identity')
        assert query({'media':['video']}).json()['total']==2
        assert query({'date':{'from':'2025-01-01','to':'2026-12-31'},'media':['video']}).json()['total']==1
        checks.append('missing_date_is_unknown_not_a_match')
        assert client.get('/home/v2/assets/101/preview?variant=display&revision=1').status_code==200
        checks.append('verified_prepared_photo')
        video=client.get('/home/v2/assets/102/video?revision=1',headers={'Range':'bytes=0-7'})
        assert video.status_code==206 and video.content==(root/'tests/security/fixtures/home-video.mp4').read_bytes()[:8]
        checks.append('verified_prepared_video_range')
        assert client.get('/assets/101/original').status_code==403
        checks.append('legacy_original_denied')
        control_path.write_bytes(disabled)
        assert client.get('/home/discovery/v1/facets').status_code==403 and client.get('/home/v2/catalog').status_code==403
        checks.append('shared_disable_restored')
    assert all(exp.sha((publication/name).read_bytes())==digest for name,digest in output['output_hashes'].items())
    checks.append('final_bundle_disabled_hashes_restored')
    print(json.dumps({'status':'PASS_SYNTHETIC_EXPORT_AND_ASGI_ONLY','check_count':len(checks),'checks':checks,
                      'coverage':output['coverage'],'plan_sha256':output['plan_sha256'],'output_hashes':output['output_hashes'],
                      'listener_started':False,'real_data_accessed':False,'final_enabled':False},indent=2,sort_keys=True))
