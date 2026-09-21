"""Local bilingual place lookup: compatibility, auth, paging and artifact validation."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from app.access import discovery as d
from app.access.discovery_provider import NamedPlace, ReviewedPlace, MemoryIndexProvider
from app.access.discovery_index import index as parse_index, accepted, DiscoveryIndexRefused
from app.access.discovery_transport import DiscoveryRuntime
from app.phone_discovery_candidate import create_candidate
from test_phone_discovery_http import Fixture, ORIGIN, BASE
from phone_discovery_fixture import TOKEN
import prepare_access_places as producer

class PlaceNameSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.fixture=Fixture(Path(self.tmp.name)/'synthetic.sqlite')
        self.index=replace(self.fixture.index,places=(
            NamedPlace('family-a','601','示例甲 / Example A',('北京','Beijing','Běijīng','Peking')),
            NamedPlace('family-a','602','示例乙 / Example B',('朝阳','Chaoyang')),
            NamedPlace('family-a','603','示例丙 / Example C',('朝阳','Chaoyang')),
        ))
        runtime=DiscoveryRuntime(self.fixture.access,MemoryIndexProvider((self.index,)),d.ReadBudget())
        self.client=TestClient(create_candidate(discovery_runtime=runtime),base_url=ORIGIN);self.addCleanup(self.client.close)
        self.auth={'Authorization':'Bearer '+TOKEN}
    def get(self,q=None,**params):
        values={'facet':'locations',**params}
        if q is not None: values['q']=q
        return self.client.get(BASE+'/facets',params=values,headers=self.auth)
    def test_names_aliases_unicode_and_case(self):
        for q in ('北京','beijing','ＢＥＩＪＩＮＧ','  Běijīng  ','peking'):
            with self.subTest(q=q):
                r=self.get(q);self.assertEqual(r.status_code,200,r.text)
                self.assertEqual([p['id'] for p in r.json()['items']],['601'])
                self.assertNotIn('aliases',r.json()['items'][0]);self.assertEqual(r.headers['cache-control'],'no-store')
        self.assertEqual(self.get('unknown').json()['total'],0)
        self.assertEqual(self.get('').json(),self.get().json())
    def test_ambiguity_paging_and_selection_search(self):
        first=self.get('朝阳',page_size=1).json();self.assertEqual(first['total'],2)
        second=self.get('Chaoyang',page_size=1,page=2,binding=first['binding']).json()
        self.assertEqual([first['items'][0]['id'],second['items'][0]['id']],['602','603'])
        beijing=self.get('beijing').json()
        r=self.client.post(BASE+'/search',headers=self.auth,json={'binding':beijing['binding'],'filters':{'locations':['601'],'media':['image']},'page':1,'page_size':24,'fingerprint':None})
        self.assertEqual(r.status_code,200,r.text);self.assertGreater(r.json()['total'],0)
    def test_invalid_query_and_facet(self):
        for params in ({'q':'北'*43},{'q':'x','facet':'people'},{'q':'x','facet':'tags'}):
            r=self.get(**params);self.assertEqual(r.status_code,400,r.text)
        r=self.client.get(BASE+'/facets?facet=locations&q=a&q=b',headers=self.auth);self.assertEqual(r.status_code,400)
    def test_revocation_and_stale_binding(self):
        binding=self.get('beijing').json()['binding']
        self.fixture.update("UPDATE assets SET taken_at='2026-02-01' WHERE id=101")
        self.assertEqual(self.get('beijing',binding=binding).status_code,409)
        self.assertEqual(self.client.get(BASE+'/facets?facet=locations&q=beijing').status_code,401)
        self.fixture.update("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        self.assertEqual(self.get('beijing').status_code,401)
    def test_legacy_and_named_artifact_serialization(self):
        self.assertNotIn('aliases',asdict(ReviewedPlace('family-a','1','Old')))
        parsed=parse_index(d.packed(asdict(self.index)),100000);self.assertEqual(parsed,self.index)
        accepted(parsed,d.ReadBudget())
        for aliases in (['x']*9,['x','x'],[True],['北'*43]):
            value=asdict(self.index);value['places'][0]['aliases']=aliases
            with self.assertRaises((DiscoveryIndexRefused,d.DiscoveryInvalid)):
                accepted(parse_index(d.packed(value),100000),d.ReadBudget())
    def test_public_starter_catalogue(self):
        root=Path(__file__).resolve().parents[2]
        regions=producer.regions(json.loads((root/'docs/security/place-catalogue-china-starter.json').read_text()))
        self.assertEqual(len(regions),9)
        self.assertTrue(all('Approx.' in r['label'] for r in regions))
        self.assertEqual(sum('Chaoyang' in r['aliases'] for r in regions),2)
