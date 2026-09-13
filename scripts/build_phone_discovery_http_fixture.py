"""Produce candidate wire examples using synthetic SQLite and in-process ASGI."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/security'))
from test_phone_discovery_http import Fixture,TestClient,ORIGIN,BASE,TOKEN,SECOND


def build():
    with tempfile.TemporaryDirectory(prefix='phone-discovery-http-') as directory:
        fixture=Fixture(Path(directory)/'synthetic.sqlite')
        with TestClient(fixture.app,base_url=ORIGIN) as client:
            auth={'Authorization':'Bearer '+TOKEN};cases=[]
            def record(name,method,path,body=None,headers=None):
                response=client.request(method,path,json=body,headers=auth if headers is None else headers)
                cases.append({'name':name,'request':{'method':method,'path':path,'json':body},
                    'status':response.status_code,'headers':{k:response.headers[k] for k in ('cache-control','pragma','referrer-policy','cross-origin-resource-policy')},'body':response.json()})
                return response.json()
            facet=record('people-first','GET',BASE+'/facets?page_size=1')
            record('people-next','GET',BASE+'/facets?page_size=1&page=2&binding='+facet['binding'])
            record('tags','GET',BASE+'/facets?facet=tags')
            record('locations','GET',BASE+'/facets?facet=locations')
            payload={'binding':facet['binding'],'filters':{},'page':1,'page_size':1,'fingerprint':None}
            first=record('all-media-first','POST',BASE+'/search',payload)
            record('all-media-next','POST',BASE+'/search',dict(payload,page=2,fingerprint=first['fingerprint']))
            record('all-filters','POST',BASE+'/search',dict(payload,filters={'people':{'ids':['301','302'],'match':'all'},'date':{'from':'2025-12-01','to':'2025-12-01'},'caption':'family','tags':{'ids':['501'],'match':'any'},'locations':['601'],'media':['image']}))
            record('missing-auth','GET',BASE+'/facets',headers={})
            record('unknown-library','GET','/libraries/unknown/discovery/v1/facets')
            record('stale-binding','POST',BASE+'/search',dict(payload,binding='0'*64))
            record('stale-fingerprint','POST',BASE+'/search',dict(payload,page=2,fingerprint='0'*64))
            record('missing-fingerprint','POST',BASE+'/search',dict(payload,page=2))
            record('invalid-id','POST',BASE+'/search',dict(payload,filters={'people':{'ids':[301],'match':'any'}}))
            fixture.update("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
            record('revoked-before-stale','POST',BASE+'/search',dict(payload,binding='0'*64))
            return {'synthetic_only':True,'contract':'protected-discovery-http-candidate-1','examples':cases}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=build()
    with args.output.open('x') as output:json.dump(result,output,indent=2,ensure_ascii=False);output.write('\n')
    print(json.dumps({'synthetic_only':True,'examples':len(result['examples'])}))


if __name__=='__main__':main()
