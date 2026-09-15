import json,hashlib,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts'),str(ROOT/'tests/security')]
import test_home_tag_discovery as base
from app.home_calendar import create_home_calendar,CalendarIndex
from fastapi.testclient import TestClient

class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.f=base.TagDiscoveryTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        f=self.f.f
        self.app=create_home_calendar(f.config,f.sources,f.cache,self.f.path,hashlib.sha256(self.f.path.read_bytes()).hexdigest(),f.pub/'discovery.json',f.discovery_sha)
        self.client=TestClient(self.app,base_url=f.config.origin,client=('192.168.40.20',1));self.addCleanup(self.client.close)
    def get(self,**q):return self.client.get('/home/discovery/v3/calendar',params=dict(revision=7,**q))
    def examples(self):
        return dict(years=self.get().json(),months=self.get(year=2026).json(),days=self.get(year=2026,month=1).json())
    def test_year_month_day_counts_and_cover_are_exact(self):
        e=self.examples();self.assertEqual(e['years']['dated_assets'],3);self.assertEqual(e['years']['undated_assets'],1)
        self.assertEqual([(x['key'],x['count']) for x in e['years']['items']],[('2026',2),('2025',1)])
        self.assertEqual(e['days']['items'][0]['from_date'],'2026-01-02')
        for item in e['years']['items']:
            if item['cover']:
                url=item['cover']['previews']['grid']['url'];self.assertTrue(url.startswith('/home/v3/'))
                self.assertEqual(self.client.get(url).status_code,200)
    def test_revision_query_and_actual_peer_bounds(self):
        for q in ({'month':1},{'year':10000},{'month':13,'year':2026},{'page_size':13},{'page':0}):self.assertEqual(self.get(**q).status_code,400)
        self.assertEqual(self.client.get('/home/discovery/v3/calendar?revision=8').status_code,409)
        self.assertEqual(self.get(year=2001).json()['items'],[])
        self.assertEqual(self.client.get('/home/discovery/v3/calendar?revision=7',headers={'Authorization':'Bearer forbidden'}).status_code,403)
        with TestClient(self.app,base_url=self.f.f.config.origin,client=('192.168.99.1',1)) as c:self.assertEqual(c.get('/home/discovery/v3/calendar?revision=7').status_code,403)
    def test_binding_and_existing_routes_remain_unchanged(self):
        facet=self.f.client.get('/home/discovery/v3/facets').json()
        from app.home_calendar import BINDING_FIELDS
        binding=hashlib.sha256(json.dumps({k:facet[k] for k in BINDING_FIELDS},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(self.get().json()['binding'],binding)
        for path in ('/home/discovery/v2/facets','/home/discovery/v3/facets','/home/v3/catalog?browse=1'):
            self.assertEqual(self.client.get(path).json(),self.f.client.get(path).json())
    def test_index_change_refuses_calendar_without_breaking_legacy(self):
        self.assertEqual(self.get().status_code,200);self.f.path.write_bytes(self.f.path.read_bytes()+b' ')
        self.assertEqual(self.get().status_code,503);self.assertEqual(self.client.get('/home/discovery/v2/facets').status_code,200)
    def test_golden(self):
        self.assertEqual(self.examples(),json.loads((ROOT/'docs/security/home-calendar-examples-v1.json').read_text()))
