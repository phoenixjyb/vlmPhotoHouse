"""Synthetic discovery/v2 -> actual v3 media composition, without live services."""
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from fastapi.testclient import TestClient
from app.home_catalog import Configuration, Publication
from app.home_originals import SourceIndex
from app.home_discovery_delivery import create_home_discovery_delivery
from app.photo_delivery import PhotoCache, source_pin
from build_home_discovery_fixture import create
from build_home_source_index import inspect_source

class DeliveryDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.pub=self.root/'publication'
        self.discovery_sha=create(self.pub)
        self.config=Configuration(self.pub/'control.json',self.pub/'prepared','https://home.photohouse.test:18444',('192.168.40.0/24',))
        self.originals=self.root/'originals';self.originals.mkdir()
        photo=self.originals/'photo.jpg';photo.write_bytes((ROOT/'tests/security/fixtures/home-8x8.jpg').read_bytes())
        video=self.originals/'video.mp4';video.write_bytes((ROOT/'tests/security/fixtures/home-video.mp4').read_bytes())
        self.photo=photo;self.video=video
        entries=[dict(id=103,**inspect_source(photo,(self.originals,),'photo')),
                 dict(id=104,path=str(video),identity=list(source_pin(video,(self.originals,))),kind='video',mime='video/mp4',width=320,height=180,duration_ms=500,audio_codec='aac')]
        sha=json.loads((self.pub/'control.json').read_text())['catalog_sha256']
        self.source_path=self.root/'sources.json';self.source_path.write_text(json.dumps(dict(version=1,catalog_sha256=sha,assets=entries)))
        self.cache=PhotoCache(self.root/'cache',guard_factory=lambda _:lambda *a,**kw:None)
        self.install()
        for target in ('socket.socket.bind','socket.socket.connect','sqlite3.connect','os.system'):
            guard=patch(target,side_effect=AssertionError('External state forbidden'));guard.start();self.addCleanup(guard.stop)
    def install(self,allow=True):
        self.sources=SourceIndex(Publication(self.config),self.source_path,hashlib.sha256(self.source_path.read_bytes()).hexdigest(),(self.originals,),originals_allowed=allow)
        self.app=create_home_discovery_delivery(self.config,self.sources,self.cache,self.pub/'discovery.json',self.discovery_sha)
        self.client=TestClient(self.app,base_url=self.config.origin,client=('192.168.40.20',1));self.addCleanup(self.client.close)
    def search(self,filters=None,**changes):
        request=dict(revision=7,page=1,page_size=50,filters=filters or {});request.update(changes)
        return self.client.post('/home/discovery/v2/search',json=request)
    def test_search_opens_on_demand_photo_and_preserves_original_policy(self):
        r=self.search({'people':{'ids':[201,202],'match':'all'},'tags':{'ids':[301],'match':'any'}})
        self.assertEqual(r.status_code,200,r.text);body=r.json();self.assertEqual(body['version'],2)
        self.assertEqual([a['id'] for a in body['items']],[103]);a=body['items'][0]
        self.assertEqual(a['previews']['grid']['state'],'on_demand')
        url=a['previews']['grid']['url'];cold=self.client.get(url);self.assertEqual(cold.status_code,200,cold.text[:60])
        self.assertEqual(self.client.get(url).content,cold.content)
        self.assertEqual(self.client.get(a['original']['url']).content,self.photo.read_bytes())
        self.assertNotIn(str(self.root),r.text)
        self.install(allow=False);a=self.search({'media':['photo']}).json()['items'][0]
        self.assertIsNone(a['original']);self.assertFalse(a['originals_allowed'])
        self.assertEqual(a['previews']['grid']['state'],'on_demand')
    def test_prepared_and_direct_video_range_paths(self):
        body=self.search({'media':['video']}).json();self.assertEqual([a['id'] for a in body['items']],[104,102])
        for a in body['items']:
            url=a['video']['url'];self.assertTrue(url.startswith('/home/v3/'))
            self.assertEqual(self.client.head(url).status_code,200)
            r=self.client.get(url,headers={'Range':'bytes=0-15'});self.assertEqual(r.status_code,206);self.assertEqual(len(r.content),16)
        self.assertEqual(body['items'][0]['video']['state'],'direct')
        self.assertEqual(body['items'][1]['video']['state'],'ready')
    def test_facets_and_pagination_use_frozen_semantics(self):
        facet=self.client.get('/home/discovery/v2/facets?page_size=1').json()
        self.assertEqual(facet['version'],2);self.assertEqual(facet['pinned_person_ids'],[202,201])
        self.assertFalse(facet['capabilities']['filters']['themes']['enabled'])
        first=self.search(page_size=2).json();second=self.search(page_size=2,page=2).json()
        self.assertEqual(first['filter_fingerprint'],second['filter_fingerprint'])
        self.assertEqual([a['id'] for a in first['items']+second['items']],[104,103,102,101])
        self.assertEqual(self.search({'caption':'sample child'}).json()['items'][0]['id'],104)
        self.assertEqual(self.search(revision=8).status_code,409)
        self.assertEqual(self.search({'themes':[1]}).status_code,422)
    def test_source_index_change_revokes_metadata_and_shared_disable_revokes_both(self):
        self.assertEqual(self.search().status_code,200)
        self.source_path.write_bytes(self.source_path.read_bytes()+b' ')
        self.assertEqual(self.search().status_code,503)
        self.assertEqual(self.client.get('/home/discovery/v2/facets').status_code,503)
        self.assertEqual(self.client.get('/home/v3/catalog').status_code,503)
    def test_disable_peer_credentials_and_legacy_routes(self):
        self.assertEqual(self.client.get('/home/discovery/v1/facets').status_code,403)
        self.assertEqual(self.client.get('/home/discovery/v2/facets',headers={'Authorization':'Bearer forbidden'}).status_code,403)
        with TestClient(self.app,base_url=self.config.origin,client=('192.168.99.20',1)) as denied:
            self.assertEqual(denied.get('/home/discovery/v2/facets').status_code,403)
        control=json.loads((self.pub/'control.json').read_text());control['enabled']=False
        (self.pub/'control.json').write_text(json.dumps(control))
        self.assertEqual(self.search().status_code,403);self.assertEqual(self.client.get('/home/v3/catalog').status_code,403)
    def test_slow_body_slots_timeout_and_release(self):
        import asyncio
        from starlette.requests import Request
        import app.home_discovery_delivery as delivery
        endpoint=next(r.endpoint for r in self.app.discovery.routes if r.path.endswith('/search'))
        async def check():
            async def receive():
                await asyncio.sleep(10)
                return {'type':'http.request','body':b'', 'more_body':False}
            def request():return Request({'type':'http','method':'POST','path':'/home/discovery/v2/search','query_string':b'', 'headers':[(b'content-type',b'application/json')]},receive)
            with patch.object(delivery,'BODY_SECONDS',0.03):
                a=asyncio.create_task(endpoint(request()));b=asyncio.create_task(endpoint(request()))
                await asyncio.sleep(0.01)
                self.assertEqual((await endpoint(request())).status_code,429)
                self.assertEqual([r.status_code for r in await asyncio.gather(a,b)],[408,408])
        asyncio.run(check())
        self.assertEqual(self.search().status_code,200)

    def test_explicit_launcher_preserves_policy_and_rejects_bad_index(self):
        from home_search_app import main
        from home_feed_app import load_config
        calls=[]
        args=['--config',str(self.root/'config.json'),'--sources',str(self.source_path),
            '--sources-sha256',self.sources.sha256,'--source-root',str(self.originals),
            '--cache',str(self.root/'cache'),'--allow-originals','--discovery-index',str(self.pub/'discovery.json'),
            '--discovery-sha256',self.discovery_sha,'--serve']
        options={'access_log':False,'proxy_headers':False,'host':'192.168.40.1','port':18444}
        with patch('home_search_app.load_config',return_value=(self.config,options)):
            self.assertEqual(main(args,server_run=lambda app,**kw:calls.append((app,kw))),0)
            self.assertEqual(calls[0][1],options)
            self.assertEqual(len(calls),1)
            args[-2]='0'*64
            self.assertEqual(main(args,server_run=lambda *a,**kw:self.fail('Bad pin served')),2)

    def test_committed_examples_match_actual_producer(self):
        expected=json.loads((ROOT/'docs/security/home-discovery-delivery-examples-v2.json').read_text())
        for field in ('people','tags','locations'):
            self.assertEqual(self.client.get('/home/discovery/v2/facets?facet='+field).json(),expected['facets_'+field])
        self.assertEqual(self.client.post('/home/discovery/v2/search',json=expected['search_request']).json(),expected['search_response'])

    def test_mismatched_media_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            create_home_discovery_delivery(replace(self.config,allowed_networks=('192.168.99.0/24',)),self.sources,self.cache,self.pub/'discovery.json',self.discovery_sha)

if __name__=='__main__':unittest.main()
