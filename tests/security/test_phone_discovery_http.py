"""Candidate HTTP contract on synthetic SQLite and in-process ASGI only."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from fastapi.testclient import TestClient
from starlette.requests import Request
from app.access import discovery as d
from app.access.discovery_provider import MemoryIndexProvider
from app.access.discovery_transport import DiscoveryRuntime, body, MAX_BODY
from app.access.transport import AccessRuntime, COOKIE, csrf_token, TransportError
from app.access.service import AccessService
from app.phone_discovery_candidate import create_candidate, CandidateBoundary
from app.main import create_app
from phone_discovery_fixture import create,reviewed,TOKEN,SECOND,OTHER,NOW,MAXIMUM

ORIGIN='https://photohouse.example.test'
BASE='/libraries/family-a/discovery/v1'


class Fixture:
    def __init__(self,path):
        self.path=path
        with sqlite3.connect(path) as db:
            create(db);self.index=reviewed(AccessService(db,clock=lambda:NOW))
        self.provider=MemoryIndexProvider((self.index,))
        self.access=AccessRuntime(self.connection,ORIGIN,clock=lambda:NOW)
        self.budget=d.ReadBudget()
        self.runtime=DiscoveryRuntime(self.access,self.provider,self.budget)
        self.app=create_candidate(discovery_runtime=self.runtime)
    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=.25)
        db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA query_only=ON')
        try:yield db
        finally:db.close()
    def update(self,sql):
        with sqlite3.connect(self.path) as db:db.execute(sql)


class PhoneDiscoveryHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.fixture=Fixture(Path(self.temp.name)/'synthetic.sqlite')
        self.client=TestClient(self.fixture.app,base_url=ORIGIN);self.addCleanup(self.client.close)
        self.auth={'Authorization':'Bearer '+TOKEN}
    def get(self,params=None,headers=None):return self.client.get(BASE+'/facets',params=params,headers=self.auth if headers is None else headers)
    def payload(self,**changes):
        result={'binding':self.get().json()['binding'],'filters':{},'page':1,'page_size':50,'fingerprint':None};result.update(changes);return result
    def post(self,payload=None,headers=None):return self.client.post(BASE+'/search',json=self.payload() if payload is None else payload,headers=self.auth if headers is None else headers)
    def private(self,response,status):
        self.assertEqual(response.status_code,status,response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(response.headers['cross-origin-resource-policy'],'same-origin')
        if status!=200:self.assertEqual(set(response.json()),{'error','detail'})

    def test_facets_and_search_string_ids_and_coverage(self):
        facets=self.get();self.private(facets,200);self.assertEqual(facets.json()['version'],1)
        self.assertEqual(facets.json()['pinned_person_ids'],['302','301'])
        search=self.post();self.private(search,200)
        self.assertEqual([x['id'] for x in search.json()['items']],[str(MAXIMUM),'103','102','101'])
        self.assertFalse(search.json()['originals_allowed'])
        self.assertNotIn('/home/',search.text);self.assertNotIn('not-a-real-path',search.text)

    def test_missing_foreign_expired_revoked_denied_before_provider_or_bad_body(self):
        with patch.object(self.fixture.provider,'get',side_effect=AssertionError('Provider read before policy')):
            for headers in ({},{'Authorization':'Bearer '+OTHER},{'Authorization':'Bearer '+('z'*43)}):
                self.private(self.client.post(BASE+'/search',content=b'not-json',headers=headers),401)
            for sql in ("UPDATE access_sessions SET revoked=1",):
                self.fixture.update(sql);self.private(self.get(),401)

    def test_unknown_library_and_membership_states(self):
        with patch.object(self.fixture.provider,'get',side_effect=AssertionError('No provider read')):
            self.private(self.client.get('/libraries/unknown/discovery/v1/facets',headers=self.auth),401)
            self.fixture.update("UPDATE access_memberships SET status='requested' WHERE account_id='one'")
            self.private(self.get(),401)

    def test_native_cookie_ambiguity_origin_and_duplicate_auth(self):
        for extra in ({'Origin':ORIGIN},{'Cookie':COOKIE+'='+TOKEN},{'Sec-Fetch-Site':'cross-site'}):
            r=self.get(headers=dict(self.auth,**extra));self.assertIn(r.status_code,(401,403))
        self.private(self.get(headers=[('Authorization','Bearer '+TOKEN),('Authorization','Bearer '+SECOND)]),400)
        self.private(self.get(headers={'Authorization':'Basic '+TOKEN}),401)

    def test_web_same_origin_cookie_and_csrf(self):
        web={'Cookie':COOKIE+'='+TOKEN,'Origin':ORIGIN}
        self.private(self.get(headers=web),200)
        payload=self.payload()
        self.private(self.post(payload,headers=web),403)
        self.private(self.post(payload,headers=dict(web,**{'X-CSRF-Token':csrf_token(TOKEN)})),200)
        self.private(self.get(headers={'Cookie':COOKIE+'='+TOKEN}),403)
        self.private(self.get(headers=dict(web,Origin='https://foreign.example.test')),403)

    def test_changed_binding_fingerprint_and_session(self):
        initial=self.post().json()
        self.private(self.post(self.payload(page=2,fingerprint='0'*64)),409)
        self.private(self.post(self.payload(binding=initial['binding']),headers={'Authorization':'Bearer '+SECOND}),409)
        self.private(self.post(self.payload(binding='0'*64)),409)
        self.fixture.update("UPDATE assets SET status='hidden' WHERE id=101")
        self.private(self.get(),409)

    def test_paginated_search_fingerprint_normalization(self):
        first=self.post(self.payload(page_size=1,filters={'people':{'ids':['302','301'],'match':'any'}})).json()
        second=self.post(self.payload(page=2,page_size=1,fingerprint=first['fingerprint'],filters={'people':{'ids':['301','302'],'match':'any'}}))
        self.private(second,200);self.assertEqual(second.json()['items'][0]['id'],'101')
        self.private(self.post(self.payload(page=2)),400)

    def test_query_duplicate_unknown_invalid_limits_and_missing_binding(self):
        for query in ('page=1&page=2','token=secret','page=0','page=5001','page_size=101','page=true','page=2','facet=%FF','facet=%xy','facet=people&','facet=unknown'):
            with self.subTest(query=query):self.private(self.client.get(BASE+'/facets?'+query,headers=self.auth),400)
        self.private(self.get({'page':2,'binding':self.get().json()['binding']}),200)

    def test_json_duplicates_nonfinite_surrogates_encoding_and_depth(self):
        for raw in ('{"binding":null,"binding":"duplicate"}', '{"x":NaN}', '{"x":"\\ud800"}', '['*100+'0'+']'*100):
            self.private(self.client.post(BASE+'/search',content=raw,headers=dict(self.auth,**{'Content-Type':'application/json'})),400)
        self.private(self.client.post(BASE+'/search',content=b'\xff',headers=dict(self.auth,**{'Content-Type':'application/json'})),400)
        self.private(self.client.post(BASE+'/search',json=self.payload(),headers=dict(self.auth,**{'Content-Encoding':'gzip'})),400)

    def test_body_limits_and_strict_envelope(self):
        self.private(self.client.post(BASE+'/search',content=b'x'*(MAX_BODY+1),headers=dict(self.auth,**{'Content-Type':'application/json'})),413)
        for changes in ({'unknown':1},{'page':True},{'page_size':101},{'filters':{'people':{'ids':[301],'match':'any'}}},{'filters':{'people':{'ids':['9223372036854775808'],'match':'any'}}},{'filters':{'themes':['x']}}):
            self.private(self.post(self.payload(**changes)),400)
        self.private(self.client.post(BASE+'/search?extra=x',json=self.payload(),headers=self.auth),400)

    def test_service_errors_generic_busy_and_budget(self):
        with patch.object(self.fixture.provider,'get',side_effect=RuntimeError('PRIVATE database path token')):
            r=self.get();self.private(r,503);self.assertNotIn('PRIVATE',r.text)
        self.fixture.budget.slots.acquire();self.fixture.budget.slots.acquire()
        try:
            r=self.get();self.private(r,429);self.assertEqual(r.headers['retry-after'],'2')
        finally:self.fixture.budget.slots.release();self.fixture.budget.slots.release()
        with patch.object(self.fixture.provider,'get',return_value=None):self.private(self.get(),503)
        self.fixture.budget.response_bytes=10;self.private(self.get(),503)

    def test_methods_shadowed_handlers_default_app_and_runtime_disabled(self):
        for method,path in [('HEAD','facets'),('POST','facets'),('GET','search'),('OPTIONS','search')]:
            r=self.client.request(method,BASE+'/'+path,headers=self.auth);self.assertEqual(r.status_code,403)
        default=TestClient(create_app(access_runtime=self.fixture.access),base_url=ORIGIN)
        self.addCleanup(default.close)
        # The default app mounts the reviewed routes but holds no reviewed index
        # runtime, so it refuses instead of serving candidate data.
        denied=default.get(BASE+'/facets',headers=self.auth)
        self.assertEqual(denied.status_code,503)
        self.assertEqual(set(denied.json()),{'error','detail'})
        self.assertEqual(denied.json()['error'],'discovery_unavailable')
        route=next(r for r in self.fixture.app.routes if r.path==BASE.replace('family-a','{library_id}')+'/facets')
        old=route.endpoint;route.endpoint=lambda:None
        try:self.assertEqual(self.get().status_code,403)
        finally:route.endpoint=old
        self.fixture.app.state.discovery_runtime=None;self.private(self.get(),503)

    def test_origin_host_https_and_trailing_slash(self):
        self.private(self.get(headers=dict(self.auth,Host='foreign.example.test')),400)
        self.private(self.client.get('http://photohouse.example.test'+BASE+'/facets',headers=self.auth),400)
        self.assertEqual(self.client.get(BASE+'/facets/',headers=self.auth).status_code,403)

    def test_disconnect_releases_budget(self):
        from app.access.discovery_transport import invoke
        class Disconnected:
            async def is_disconnected(self):return True
        def slow(operation,token,library,cancelled,values):
            import time
            while not cancelled():time.sleep(.001)
            raise d.DiscoveryCancelled()
        async def exercise():
            with patch.object(DiscoveryRuntime,'call',side_effect=slow):
                with self.assertRaises(d.DiscoveryCancelled):
                    await invoke(Disconnected(),self.fixture.runtime,'facets',TOKEN,'family-a',{})
        asyncio.run(exercise())

    def test_membership_rechecked_after_body_receipt(self):
        payload=self.payload()
        from app.access import discovery_transport as transport
        original=transport.body
        async def revoke_then_read(request):
            self.fixture.update("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
            return await original(request)
        with patch.object(transport,'body',side_effect=revoke_then_read), patch.object(self.fixture.provider,'get',side_effect=AssertionError('No provider after revocation')):
            self.private(self.post(payload),401)

    def test_untrusted_dimension_metadata_is_null_not_native_overflow(self):
        self.fixture.update("UPDATE assets SET width=9223372036854775807,height=-1,duration_sec=-2 WHERE id=101")
        with self.fixture.connection() as db:
            index=reviewed(AccessService(db,clock=lambda:NOW))
        with patch.object(self.fixture.provider,'get',return_value=index):
            response=self.post();self.private(response,200)
            asset=next(a for a in response.json()['items'] if a['id']=='101')
            self.assertIsNone(asset['width']);self.assertIsNone(asset['height']);self.assertIsNone(asset['duration_sec'])

    def test_newline_ids_binding_and_fingerprint_are_not_canonical(self):
        initial=self.post().json()
        for suffix in ('\n','\r\n','\t','\u2028'):
            with self.subTest(suffix=repr(suffix)):
                self.private(self.post(self.payload(filters={'people':{'ids':['301'+suffix],'match':'any'}})),400)
                self.private(self.post(self.payload(binding=initial['binding']+suffix)),400)
                self.private(self.post(self.payload(fingerprint=initial['fingerprint']+suffix)),400)
                self.private(self.get({'binding':initial['binding']+suffix}),400)

    def test_stream_limit_mismatch_and_body_deadline(self):
        async def attempt(chunks,headers,delay=0):
            async def receive():
                if delay:await asyncio.sleep(delay)
                return {'type':'http.request','body':chunks.pop(0),'more_body':bool(chunks)}
            req=Request({'type':'http','method':'POST','headers':headers,'query_string':b''},receive)
            return await body(req)
        headers=[(b'content-type',b'application/json')]
        with self.assertRaises(TransportError) as e:asyncio.run(attempt([b'x'*MAX_BODY,b'x'],headers))
        self.assertEqual(e.exception.status,413)
        with self.assertRaises(d.DiscoveryInvalid):asyncio.run(attempt([b'{}'],headers+[(b'content-length',b'10')]))
        with patch('app.access.discovery_transport.BODY_SECONDS',.01):
            with self.assertRaises(TransportError) as e:asyncio.run(attempt([b'{}'],headers,.1))
        self.assertEqual(e.exception.status,408)


if __name__=='__main__':unittest.main()
