"""Synthetic metadata/aliases only; frozen media composition and no live indexing."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from starlette.routing import Route
from app import home_discovery as home
from app.home_catalog import create_home_catalog
from app.home_feed import create_home_feed
from app.main import create_app
from build_home_discovery_fixture import create


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='home-discovery-');self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()/'publication';self.sha=create(self.root)
        self.index_path=self.root/'discovery.json';self.index=json.loads(self.index_path.read_text())
        self.config=home.Configuration(self.root/'control.json',self.root/'prepared','https://home.photohouse.test:18444',('192.168.40.0/24',))
        self.app=home.create_home_discovery(self.config,self.index_path,self.sha);self.client=self.client_for(self.app)
        for target in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system','sqlite3.connect'):
            guard=patch(target,side_effect=AssertionError('External state forbidden'));guard.start();self.addCleanup(guard.stop)

    def client_for(self, app,peer=('192.168.40.20',1),url=None):
        client=TestClient(app,base_url=url or self.config.origin,client=peer);self.addCleanup(client.close);return client

    def reload(self):
        raw=json.dumps(self.index).encode();self.index_path.write_bytes(raw)
        self.sha=hashlib.sha256(raw).hexdigest();self.app=home.create_home_discovery(self.config,self.index_path,self.sha);self.client=self.client_for(self.app)

    def query(self,filters=None,**changes):
        body={'revision':7,'page':1,'page_size':50,'filters':filters or {}};body.update(changes)
        return self.client.post('/home/discovery/v1/search',json=body)

    def ids(self,response):
        self.assertEqual(response.status_code,200,response.text)
        return [a['id'] for a in response.json()['items']]

    def test_facets_pins_alias_order_and_honest_coverage(self):
        response=self.client.get('/home/discovery/v1/facets?page_size=1');self.assertEqual(response.status_code,200)
        body=response.json();self.assertEqual(body['pinned_person_ids'],[202,201])
        self.assertEqual([p['id'] for p in body['pinned_people']],[202,201]);self.assertEqual(body['items'][0]['id'],201)
        self.assertEqual(body['pinned_people'][0]['aliases'],['Sample Child','示例儿童'])
        caps=body['capabilities'];self.assertEqual((caps['catalog_assets'],caps['indexed_assets'],caps['index_complete']),(4,4,True))
        self.assertEqual(caps['filters']['caption']['assets_with_values'],3)
        self.assertEqual(caps['metadata_completeness'],'not_inferred');self.assertEqual(caps['tag_generation_completeness'],'unknown')
        self.assertFalse(caps['filters']['themes']['enabled']);self.assertFalse(caps['filters']['topics']['enabled'])
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertNotIn('caption_text',response.text);self.assertNotIn(str(self.root),response.text)

    def test_frozen_examples_and_library_binding_match_actual_composition(self):
        examples=json.loads((ROOT/'docs/security/home-discovery-examples-v1.json').read_text())
        for facet in ('people','tags','locations'):
            body=self.client.get('/home/discovery/v1/facets?facet='+facet+'&page_size=1').json()
            self.assertEqual(body,examples['facets_'+facet])
        response=self.client.post('/home/discovery/v1/search',json=examples['search_request'])
        self.assertEqual(response.json(),examples['search_response'])
        self.assertEqual(response.json()['library'],self.client.get('/home/v2/catalog').json()['library'])
        self.assertEqual(examples['facets_people']['capabilities']['captured_date_bounds'],{'from':'2025-12-01','to':'2026-05-05'})

    def test_matching_budget_and_concurrency_fail_closed(self):
        self.assertEqual(self.query().status_code,200)
        with patch.object(home,'monotonic',side_effect=[0,3]):
            response=self.query();self.assertEqual(response.status_code,503)
            self.assertEqual(response.json()['error'],'search_budget_exceeded')
        class Busy:
            def __init__(self,n):pass
            def acquire(self,**kwargs):return False
        with patch.object(home.threading,'BoundedSemaphore',Busy):
            app=home.create_home_discovery(self.config,self.index_path,self.sha)
        response=self.client_for(app).get('/home/discovery/v1/facets')
        self.assertEqual((response.status_code,response.headers['retry-after']),(429,'2'))

    def test_caption_tag_provenance_never_becomes_person_assignment(self):
        body=self.client.get('/home/discovery/v1/facets?facet=tags').json()
        self.assertEqual(body['items'][0]['provenance_counts']['caption'],2)
        self.assertEqual(body['items'][1]['provenance_counts']['manual'],2)
        self.assertEqual(self.ids(self.query({'caption':'sample child'})),[104])
        self.assertEqual(self.ids(self.query({'people':{'ids':[202],'match':'any'},'caption':'sample child'})),[])

    def test_any_all_and_cross_category_and_semantics(self):
        self.assertEqual(self.ids(self.query({'people':{'ids':[201,202],'match':'any'}})),[104,103,101])
        self.assertEqual(self.ids(self.query({'people':{'ids':[201,202],'match':'all'}})),[103])
        self.assertEqual(self.ids(self.query({'tags':{'ids':[301,302],'match':'all'}})),[103])
        self.assertEqual(self.ids(self.query({'people':{'ids':[201],'match':'all'},'media':['video'],'locations':[401],
                         'date':{'from':'2026-01-01','to':'2026-12-31'},'tags':{'ids':[301],'match':'any'},'caption':'park'})),[104])

    def test_date_inclusive_missing_metadata_and_literal_nfkc_caption(self):
        self.assertEqual(self.ids(self.query({'date':{'from':'2026-01-02','to':'2026-01-02'}})),[101])
        self.assertEqual(self.ids(self.query({'date':{'from':None,'to':'2025-12-01'}})),[103])
        self.assertEqual(self.ids(self.query({'caption':'family'})),[103])
        self.assertEqual(self.ids(self.query({'caption':'% OR 1=1'})),[])
        self.assertEqual(self.ids(self.query({'caption':'park home'})),[]) # Literal phrase, no implicit OR.

    def test_paging_fingerprint_and_revision_bound_media(self):
        first=self.query(page_size=2).json();second=self.query(page=2,page_size=2).json()
        self.assertEqual([a['id'] for a in first['items']],[104,103]);self.assertEqual([a['id'] for a in second['items']],[102,101])
        self.assertEqual(first['filter_fingerprint'],second['filter_fingerprint']);self.assertTrue(first['has_more']);self.assertFalse(second['has_more'])
        self.assertEqual(second['catalog_revision'],1)
        self.assertIn('revision=1',second['items'][0]['video']['url'])
        self.assertNotEqual(first['filter_fingerprint'],self.query({'media':['photo']}).json()['filter_fingerprint'])
        self.assertEqual(self.query(revision=6).status_code,409)
        self.assertEqual(self.query({'people':{'ids':[999],'match':'any'}},revision=6).status_code,409)

    def test_partial_index_still_browses_all_media_and_reports_missing_coverage(self):
        self.index['assets']=[r for r in self.index['assets'] if r['id']!=102];self.reload()
        caps=self.client.get('/home/discovery/v1/facets').json()['capabilities'];self.assertFalse(caps['index_complete'])
        self.assertEqual(caps['indexed_assets'],3)
        self.assertEqual(self.ids(self.query({'media':['video']})),[104,102])
        self.assertEqual(self.ids(self.query({'locations':[401],'media':['video']})),[104])

    def test_invalid_unknown_and_disabled_filters_fail_without_silent_ignoring(self):
        self.assertEqual(self.query({'themes':[1]}).status_code,422)
        self.index['enabled_filters'].remove('caption');self.reload()
        self.assertEqual(self.query({'caption':'park'}).status_code,422)
        for filters in ({'people':{'ids':[],'match':'all'}},{'people':{'ids':[201,201],'match':'any'}},
                        {'people':{'ids':[999],'match':'any'}},{'date':{'from':'2026-02-30','to':None}},
                        {'date':{'from':'2026-03-01','to':'2026-01-01'}},{'date':{'from':None,'to':None}},
                        {'media':[]},{'media':['photo','photo']},{'tags':{'ids':[301],'match':'fuzzy'}}):
            with self.subTest(filters=filters):self.assertEqual(self.query(filters).status_code,400)
        for changes in ({'page':0},{'page_size':101},{'revision':True},{'extra':'x'}):self.assertEqual(self.query(**changes).status_code,400)

    def test_unreviewed_person_and_location_provenance_or_orphan_ids_rejected(self):
        for mutate in (lambda v:v['assets'][0].update(people_provenance='caption'),
                       lambda v:v['assets'][0].update(people_provenance='dnn'),
                       lambda v:v['assets'][0].update(location_provenance='caption'),
                       lambda v:v['assets'][0].update(id=999),lambda v:v['assets'][0].update(person_ids=[999]),
                       lambda v:v.update(pinned_person_ids=[999]),lambda v:v['assets'][0].update(gps_lat=1.0)):
            original=copy.deepcopy(self.index);mutate(self.index);self.reload()
            self.assertEqual(self.client.get('/home/discovery/v1/facets').status_code,503)
            self.index=original

    def test_foreign_catalog_pair_malformed_duplicate_and_mutated_index_fail_closed(self):
        self.index['catalog_revision']=2;self.reload();self.assertEqual(self.query().status_code,503)
        self.index['catalog_revision']=1;self.reload();self.assertEqual(self.query().status_code,200)
        self.index_path.write_text('{}');self.assertEqual(self.query().status_code,503)
        self.reload();raw=self.index_path.read_text().replace('"version": 1','"version": 1, "version": 1')
        self.index_path.write_text(raw);self.sha=hashlib.sha256(raw.encode()).hexdigest()
        client=self.client_for(home.create_home_discovery(self.config,self.index_path,self.sha))
        self.assertEqual(client.get('/home/discovery/v1/facets').status_code,503)

    def test_disabled_publication_revokes_discovery_and_frozen_media(self):
        self.assertEqual(self.query().status_code,200)
        control=self.root/'control.json';value=json.loads(control.read_text());value['enabled']=False;control.write_text(json.dumps(value))
        self.assertEqual(self.query().status_code,403)
        self.assertEqual(self.client.get('/home/v2/catalog').status_code,403)

    def test_post_is_bounded_exact_json_and_no_query_filters(self):
        for kwargs in ({'content':'{}','headers':{'Content-Type':'text/plain'}},{'content':'{bad','headers':{'Content-Type':'application/json'}},
                       {'content':'{"revision":7,"revision":7}','headers':{'Content-Type':'application/json'}}):
            self.assertEqual(self.client.post('/home/discovery/v1/search',**kwargs).status_code,400)
        with patch.object(home,'bounded_read',side_effect=AssertionError('No metadata reads')):
            self.assertEqual(self.client.post('/home/discovery/v1/search',content=b'x'*16385,headers={'Content-Type':'application/json'}).status_code,413)
            self.assertEqual(self.client.post('/home/discovery/v1/search?q=park',json={}).status_code,400)
        self.assertEqual(self.client.get('/home/discovery/v1/search').status_code,403)

    def test_facet_query_limits_revision_and_disabled_pins(self):
        self.assertEqual(self.client.get('/home/discovery/v1/facets?page=2').status_code,400)
        self.assertEqual(self.client.get('/home/discovery/v1/facets?page=2&page_size=1&revision=7').json()['items'][0]['id'],202)
        for query in ('facet=themes','page_size=101','page=1&page=2','revision=8'):
            self.assertEqual(self.client.get('/home/discovery/v1/facets?'+query).status_code,409 if query=='revision=8' else 400)
        self.index['enabled_filters'].remove('people');self.reload()
        body=self.client.get('/home/discovery/v1/facets').json();self.assertEqual(body['items'],[]);self.assertEqual(body['pinned_people'],[])

    def test_peer_host_credentials_unknown_paths_and_shadow_denied_before_storage(self):
        for peer in (('203.0.113.1',1),('127.0.0.1',1),('192.168.41.1',1),None):
            with patch.object(home,'bounded_read',side_effect=AssertionError('No metadata read')):
                self.assertEqual(self.client_for(self.app,peer=peer).get('/home/discovery/v1/facets').status_code,403)
        for headers in ({'Host':'evil.test'},{'Authorization':'Bearer synthetic'},{'Cookie':'test=x'},{'Origin':'https://evil.test'}):
            self.assertEqual(self.client.get('/home/discovery/v1/facets',headers=headers).status_code,403)
        for path in ('/assets','/search','/health','/voice','/home/discovery/v1/original','/home/discovery/v1/facets/'):
            self.assertEqual(self.client.get(path).status_code,403)
        async def shadow(request):return JSONResponse({'unsafe':True})
        self.app.discovery.router.routes.insert(0,Route('/home/discovery/v1/facets',shadow,methods=['GET']))
        self.assertEqual(self.client.get('/home/discovery/v1/facets').status_code,403)

    def test_composition_preserves_v2_media_but_existing_apps_do_not_gain_discovery(self):
        response=self.client.get('/home/v2/catalog');self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/home/v2/assets/102/video?revision=1',headers={'Range':'bytes=0-7'}).content,
                         (ROOT/'tests/security/fixtures/home-video.mp4').read_bytes()[:8])
        self.assertEqual(self.client.get('/home/v2/assets/101/preview?variant=display&revision=1').status_code,200)
        for app in (create_home_catalog(self.config),create_home_feed(self.config),create_app()):
            self.assertEqual(self.client_for(app).get('/home/discovery/v1/facets').status_code,403)


if __name__=='__main__':unittest.main()
