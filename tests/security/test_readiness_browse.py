"""Synthetic catalog-wide admission filtering, no decoder or live library."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
import test_on_demand_delivery as delivery


class ReadinessBrowseTests(unittest.TestCase):
    def setUp(self):
        self.e = delivery.DeliveryTests(); self.e.setUp(); self.addCleanup(self.e.doCleanups)
        missing = {'state':'unavailable','reason':'not_prepared'}
        # Ready entries deliberately beyond page one in the original catalog.
        extras = [dict(id=i,kind='video',label='Pending',width=320,height=180,
                       previews={'grid':missing,'display':missing},video=missing) for i in range(180,102,-1)]
        self.e.catalog['assets'] = extras + self.e.catalog['assets']
        raw = json.dumps(self.e.catalog).encode()
        (self.e.root/'catalog.json').write_bytes(raw)
        self.e.catsha = hashlib.sha256(raw).hexdigest()
        self.e.control.write_text(json.dumps(dict(version=2,revision=9,enabled=True,catalog_sha256=self.e.catsha)))
        self.e.install()

    def get(self, query='', **kwargs):
        return self.e.client.get('/home/v3/catalog?browse=1'+query, **kwargs)

    def test_frozen_examples_match_actual_producer(self):
        from pathlib import Path
        expected = json.loads((Path(__file__).parent/'fixtures/browse-v1.json').read_text())
        self.assertEqual(examples(), expected)

    def test_ready_only_selects_across_all_pages_without_decoding(self):
        with patch('subprocess.Popen', side_effect=AssertionError('No decoder during browsing')):
            result = self.get('&availability=ready').json()
        self.assertEqual(result['total'],2)
        self.assertEqual([a['id'] for a in result['items']],[102,101])
        self.assertEqual(result['browse']['matching_total'],80)
        self.assertEqual(result['browse']['ready_total'],2)
        self.assertFalse(self.e.cache.root.exists())

    def test_ready_first_paginates_once_without_duplicates(self):
        first=self.get('&order=ready_first&page_size=50').json()
        second=self.get('&order=ready_first&page_size=50&page=2&revision=9').json()
        ids=[a['id'] for a in first['items']+second['items']]
        self.assertEqual(ids[:4],[102,101,180,179]); self.assertEqual(len(ids),80)
        self.assertEqual(len(set(ids)),80); self.assertTrue(first['has_more']); self.assertFalse(second['has_more'])

    def test_media_intersection_and_original_permission(self):
        self.assertEqual(self.get('&availability=ready&media=video').json()['total'],1)
        self.e.install(allow=False)
        response=self.get('&availability=ready&media=video').json()
        self.assertEqual(response['total'],0); self.assertEqual(response['browse']['matching_total'],79)
        # On-demand photos need library admission, not an original-byte grant.
        self.assertEqual(self.get('&availability=ready&media=photo').json()['total'],1)
        self.assertEqual(self.e.client.get('/home/v3/assets/102/video?revision=9').status_code,404)

    def test_ready_prepared_video_is_not_dependent_on_original_permission(self):
        self.e.sources.load()
        a=copy.deepcopy(self.e.catalog['assets'][0]); a['video']={'state':'ready'}
        self.e.sources.originals_allowed=False
        self.assertTrue(self.e.sources.ready(a))
        a['video']={'state':'unavailable','reason':'not_prepared'}
        a['previews']['display']={'state':'ready'}
        self.assertFalse(self.e.sources.ready(a))

    def test_invalid_selection_revision_peer_and_legacy_shape(self):
        for query in ('&availability=yes','&order=latest','&media=image','&browse=1','&revision=8','&page=2'):
            self.assertIn(self.get(query).status_code,(400,409),query)
        self.assertEqual(self.e.client.get('/home/v3/catalog?availability=ready').status_code,400)
        self.assertEqual(self.get(headers={'Authorization':'Bearer forbidden'}).status_code,403)
        self.assertNotIn('browse',self.e.client.get('/home/v3/catalog').json())
        self.assertEqual(self.e.client.get('/home/v3/catalog').json()['items'][0]['id'],180)
        control=json.loads(self.e.control.read_text());control['enabled']=False;self.e.control.write_text(json.dumps(control))
        self.assertEqual(self.get('&availability=ready').status_code,403)

def examples():
    test=ReadinessBrowseTests();test.setUp()
    try:
        cases=[]
        for page,rev,availability,order,media in (
                (1,None,'all','catalog','all'), (1,None,'ready','catalog','all'),
                (1,None,'all','ready_first','all'), (2,9,'all','ready_first','all'),
                (1,None,'ready','catalog','video'), (1,None,'ready','catalog','photo')):
            query=f'&page={page}&availability={availability}&order={order}&media={media}'
            if rev is not None: query+=f'&revision={rev}'
            response=test.get(query)
            assert response.status_code==200
            cases.append(dict(page=page,revision=rev,availability=availability,order=order,media=media,response=response.json()))
        return cases
    finally: test.doCleanups()

if __name__=='__main__': unittest.main()
