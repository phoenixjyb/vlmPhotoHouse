import asyncio
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts'),str(ROOT/'tests/security')]
from fastapi.testclient import TestClient
import test_home_discovery_delivery as base
from app.home_tag_discovery import create_home_tag_discovery,validate_tag_index
from app.home_feed import Refused

class TagDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.f=base.DeliveryDiscoveryTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.index=json.loads((self.f.pub/'discovery.json').read_text());self.index['version']=2
        self.index['tags'] += [dict(id=i,label='Synthetic tag '+str(i),kind='scene') for i in range(1000,7000)]
        self.index['tags'].append(dict(id=8999,label='Lake / 湖',kind='scene'))
        next(r for r in self.index['assets'] if r['id']==103)['tags'].append(dict(id=8999,source='caption'))
        self.path=self.f.root/'tag-index.json';raw=json.dumps(self.index).encode();self.path.write_bytes(raw)
        self.app=create_home_tag_discovery(self.f.config,self.f.sources,self.f.cache,self.path,hashlib.sha256(raw).hexdigest(),self.f.pub/'discovery.json',self.f.discovery_sha)
        self.client=TestClient(self.app,base_url=self.f.config.origin,client=('192.168.40.20',1));self.addCleanup(self.client.close)
    def examples(self):
        result={}
        for f in ('people','tags','locations'):result['facets_'+f]=self.client.get('/home/discovery/v3/facets',params=dict(facet=f,page_size=50)).json()
        result['tags_page2']=self.client.get('/home/discovery/v3/facets',params=dict(facet='tags',page_size=50,page=2,revision=7)).json()
        result['tags_lake']=self.client.get('/home/discovery/v3/facets',params=dict(facet='tags',q='湖',page_size=50,revision=7)).json()
        result['search_request']=dict(revision=7,page=1,page_size=50,filters={'tags':{'ids':[8999],'match':'all'}})
        result['search_response']=self.client.post('/home/discovery/v3/search',json=result['search_request']).json()
        return result
    def test_more_than_5000_tags_query_unicode_and_final_page(self):
        alltags=self.client.get('/home/discovery/v3/facets?facet=tags&page_size=50').json()
        self.assertEqual(alltags['version'],3);self.assertGreater(alltags['total'],5000)
        last=(alltags['total']+49)//50
        end=self.client.get(f'/home/discovery/v3/facets?facet=tags&page_size=50&page={last}&revision=7').json()
        self.assertEqual(end['items'][-1]['id'],8999);self.assertFalse(end['has_more'])
        lake=self.examples()['tags_lake'];self.assertEqual(lake['total'],1);self.assertEqual(lake['query'],'湖')
        park=self.client.get('/home/discovery/v3/facets',params={'facet':'tags','q':'ＰＡＲＫ'}).json()
        self.assertEqual(park['total'],1)
    def test_filtered_asset_result_has_current_media_and_legacy_stays_exact(self):
        x=self.examples();self.assertEqual(x['search_response']['version'],3)
        self.assertEqual([a['id'] for a in x['search_response']['items']],[103])
        self.assertEqual(x['search_response']['items'][0]['previews']['display']['state'],'on_demand')
        old=self.client.get('/home/discovery/v2/facets?facet=tags&page_size=50').json()
        self.assertEqual(old,self.f.client.get('/home/discovery/v2/facets?facet=tags&page_size=50').json())
        self.assertEqual(self.client.get('/home/v3/catalog?browse=1').status_code,200)
    def test_bounds_stale_revisions_and_index_drift(self):
        for params in ({'facet':'tags','q':'a'*129},{'facet':'people','q':'x'},{'facet':'tags','q':' x'}):
            self.assertEqual(self.client.get('/home/discovery/v3/facets',params=params).status_code,400)
        self.assertEqual(self.client.get('/home/discovery/v3/facets?facet=tags&revision=8').status_code,409)
        self.path.write_bytes(self.path.read_bytes()+b' ')
        self.assertEqual(self.client.get('/home/discovery/v3/facets').status_code,503)
        self.assertEqual(self.client.get('/home/discovery/v2/facets').status_code,200)
    def test_large_index_has_explicit_version_roster_and_foreign_tag_bounds(self):
        cat=self.f.sources.load();sha=self.index['catalog_sha256']
        for update in ({'version':1},{'tags':self.index['tags']*2}):
            with self.assertRaises(Refused):validate_tag_index(dict(self.index,**update),cat,sha)
        bad=json.loads(json.dumps(self.index));bad['assets'][0]['tags']=[{'id':123456,'source':'manual'}]
        with self.assertRaises(Refused):validate_tag_index(bad,cat,sha)
    def test_actual_peer_and_credential_boundary(self):
        self.assertEqual(self.client.get('/home/discovery/v3/facets',headers={'Authorization':'Bearer forbidden'}).status_code,403)
        with TestClient(self.app,base_url=self.f.config.origin,client=('192.168.40.99',1)) as allowed:
            self.assertEqual(allowed.get('/home/discovery/v3/facets').status_code,200)
        with TestClient(self.app,base_url=self.f.config.origin,client=('192.168.99.1',1)) as denied:
            self.assertEqual(denied.get('/home/discovery/v3/facets').status_code,403)
    def test_slow_body_slots_timeout_and_release(self):
        import asyncio
        from starlette.requests import Request
        import app.home_tag_discovery as delivery
        endpoint=next(r.endpoint for r in self.app.tags.routes if r.path.endswith('/search'))
        async def check():
            async def receive():
                await asyncio.sleep(10)
                return {'type':'http.request','body':b'', 'more_body':False}
            def request():return Request({'type':'http','method':'POST','path':'/home/discovery/v3/search','query_string':b'', 'headers':[(b'content-type',b'application/json')]},receive)
            with patch.object(delivery,'BODY_SECONDS',0.03):
                a=asyncio.create_task(endpoint(request()));b=asyncio.create_task(endpoint(request()))
                await asyncio.sleep(0.01)
                self.assertEqual((await endpoint(request())).status_code,429)
                self.assertEqual([r.status_code for r in await asyncio.gather(a,b)],[408,408])
        asyncio.run(check())
        self.assertEqual(self.client.post('/home/discovery/v3/search',json=self.examples()['search_request']).status_code,200)

    def test_explicit_launcher_preserves_policy_and_rejects_bad_index(self):
        from home_search_app import main
        from home_feed_app import load_config
        calls=[]
        args=['--config',str(self.f.root/'config.json'),'--sources',str(self.f.source_path),
            '--sources-sha256',self.f.sources.sha256,'--source-root',str(self.f.originals),
            '--cache',str(self.f.root/'cache'),'--allow-originals','--discovery-index',str(self.f.pub/'discovery.json'),
            '--discovery-sha256',self.f.discovery_sha,'--tag-index',str(self.path),
            '--tag-sha256',hashlib.sha256(self.path.read_bytes()).hexdigest(),'--serve']
        options={'access_log':False,'proxy_headers':False,'host':'192.168.40.1','port':18444}
        with patch('home_search_app.load_config',return_value=(self.f.config,options)):
            self.assertEqual(main(args,server_run=lambda app,**kw:calls.append((app,kw))),0)
            self.assertEqual(calls[0][1],options)
            self.assertEqual(len(calls),1)
            args[-2]='0'*64
            self.assertEqual(main(args,server_run=lambda *a,**kw:self.fail('Bad pin served')),2)

    def test_synthetic_examples_match_actual_producer(self):
        expected=ROOT/'docs/security/home-tag-discovery-examples-v3.json'
        self.assertEqual(self.examples(),json.loads(expected.read_text()))
