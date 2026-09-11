"""Anonymous selected LAN feed, synthetic files and ASGI only; no listeners."""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from starlette.routing import Route
from starlette.websockets import WebSocketDisconnect
from app import home_feed as home
from app.main import create_app
import home_feed_app


class HomeFeedTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='photohouse-home-feed-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.media=self.root/'prepared';self.media.mkdir()
        self.path=self.root/'selection.json'
        self.jpeg=(ROOT/'tests/security/fixtures/home-8x8.jpg').read_bytes()
        meta={'width':8,'height':8,'bytes':len(self.jpeg),'sha256':hashlib.sha256(self.jpeg).hexdigest()}
        self.value={'version':1,'enabled':True,'revision':1,'feed_id':'synthetic-home',
            'title':'Synthetic TV / 合成电视','assets':[{'id':101,'caption':'EN: A color square.\nZH-CN: 色块。',
            'previews':{'grid':dict(meta),'display':dict(meta)}}]}
        for variant in home.LIMITS:
            (self.media/variant).mkdir();(self.media/variant/'101.jpg').write_bytes(self.jpeg)
        self.publish()
        self.config=home.Configuration(self.path,self.media,'https://home.photohouse.test:18444',('192.168.40.0/24',))
        self.app=home.create_home_feed(self.config)
        self.client=TestClient(self.app,base_url=self.config.origin,client=('192.168.40.20',12345))
        self.addCleanup(self.client.close)
        for target in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system','sqlite3.connect'):
            guard=patch(target,side_effect=AssertionError('External state forbidden'));guard.start();self.addCleanup(guard.stop)

    def publish(self):
        pending=self.root/'selection.new';pending.write_text(json.dumps(self.value));pending.replace(self.path)

    def url(self,variant='display',revision=1,asset=101):
        return f'/home/v1/assets/{asset}/preview?variant={variant}&revision={revision}'

    def test_anonymous_lan_manifest_and_exact_jpeg_head_succeed_without_credentials(self):
        response=self.client.get('/home/v1/feed');self.assertEqual(response.status_code,200)
        body=response.json();self.assertFalse(body['items'][0]['originals_allowed']);self.assertFalse(body['has_more'])
        self.assertNotIn(str(self.root),response.text)
        for variant in home.LIMITS:
            result=self.client.get(body['items'][0]['previews'][variant]['url'])
            self.assertEqual((result.status_code,result.content),(200,self.jpeg))
            self.assertEqual(result.headers['cache-control'],'no-store')
            self.assertEqual(result.headers['accept-ranges'],'none')
        result=self.client.head(self.url());self.assertEqual(result.status_code,200)
        self.assertEqual(result.content,b'');self.assertEqual(int(result.headers['content-length']),len(self.jpeg))

    def test_public_other_lan_loopback_and_missing_peers_are_denied_before_storage(self):
        for peer in (('203.0.113.20',123),('192.168.41.20',123),('127.0.0.1',123),('::1',123),None):
            with self.subTest(peer=peer),TestClient(self.app,base_url=self.config.origin,client=peer) as client:
                with patch.object(home,'bounded_read',side_effect=AssertionError('No storage on denied peer')):
                    result=client.get('/home/v1/feed',headers={'X-Forwarded-For':'192.168.40.20','X-Real-IP':'192.168.40.20'})
                    self.assertEqual(result.status_code,403)

    def test_wrong_host_cleartext_cross_site_and_accidental_personal_credentials_refused(self):
        for headers in ({'Host':'evil.test'},{'Origin':'https://evil.test'},
                        {'Sec-Fetch-Site':'cross-site'},{'Authorization':'Bearer synthetic'},
                        {'Cookie':'__Host-ph_session=synthetic'}):
            with self.subTest(headers=headers),patch.object(home,'bounded_read',side_effect=AssertionError('No storage')):
                self.assertEqual(self.client.get('/home/v1/feed',headers=headers).status_code,403)
        with TestClient(self.app,base_url='http://home.photohouse.test:18444',client=('192.168.40.20',1)) as client:
            self.assertEqual(client.get('/home/v1/feed',headers={'X-Forwarded-Proto':'https'}).status_code,403)

    def test_original_account_operational_unknown_and_wrong_method_paths_closed(self):
        for path in ('/assets','/assets/101/media?library=anything','/auth/session','/health','/metrics',
                     '/search','/albums','/voice','/openapi.json','/docs','/home/v1/assets/101/original','/home/v1/feed/'):
            with self.subTest(path=path),patch.object(home,'bounded_read',side_effect=AssertionError('No storage')):
                self.assertEqual(self.client.get(path).status_code,403)
        self.assertEqual(self.client.post('/home/v1/feed',json={}).status_code,403)
        self.assertEqual(self.client.head('/home/v1/feed').content,b'')
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('/home/v1/feed'):
                self.fail('Websocket unexpectedly accepted')

    def test_public_surface_stays_separate_from_closed_phone_application(self):
        with TestClient(create_app(),base_url=self.config.origin) as client:
            self.assertEqual(client.get('/home/v1/feed').status_code,403)
            self.assertEqual(client.get('/auth/session').status_code,503)

    def test_new_shadow_handler_cannot_inherit_feed_permission(self):
        async def shadow(request):return JSONResponse({'unsafe':True})
        self.app.router.routes.insert(0,Route('/home/v1/feed',shadow,methods=['GET']))
        self.assertEqual(self.client.get('/home/v1/feed').status_code,403)

    def test_pagination_is_bounded_and_queries_are_exact(self):
        self.value['assets'].append(dict(self.value['assets'][0],id=102));self.publish()
        first=self.client.get('/home/v1/feed?page_size=1').json();self.assertTrue(first['has_more'])
        second=self.client.get('/home/v1/feed?page_size=1&page=2').json();self.assertEqual(second['items'][0]['id'],102)
        self.assertEqual(self.client.get('/home/v1/feed?page=3').json()['items'],[])
        for query in ('page=0','page=01','page=2001','page_size=101','page=1&page=2','library=private','token=synthetic'):
            self.assertEqual(self.client.get('/home/v1/feed?'+query).status_code,400)
        self.assertEqual(self.client.get('/home/v1/feed?x='+'x'*1025).status_code,403)

    def test_disable_revision_change_and_selection_removal_apply_on_next_request(self):
        self.assertEqual(self.client.get(self.url()).status_code,200)
        self.value['enabled']=False;self.publish()
        for path in ('/home/v1/feed',self.url()):
            result=self.client.get(path);self.assertEqual((result.status_code,result.json()['error']),(403,'feed_disabled'))
        self.value['enabled']=True;self.value['revision']=2;self.value['assets']=[];self.publish()
        self.assertEqual(self.client.get(self.url()).status_code,409)
        self.assertEqual(self.client.get(self.url(revision=2)).status_code,404)
        self.assertEqual(self.client.get('/home/v1/feed').json()['total'],0)

    def test_missing_or_corrupt_manifest_has_no_cached_snapshot_or_fallback(self):
        self.client.get('/home/v1/feed');self.path.unlink()
        self.assertEqual(self.client.get('/home/v1/feed').status_code,503)
        for value in (b'{',b'x'*(home.MAX_MANIFEST+1),b'{"enabled":true,"enabled":false}',b'\xff'):
            self.path.write_bytes(value);self.assertEqual(self.client.get('/home/v1/feed').status_code,503)

    def test_manifest_shape_dimensions_budget_ids_and_private_fields_fail_closed(self):
        original=copy.deepcopy(self.value)
        invalid=[dict(original,version=True),dict(original,enabled=1),dict(original,revision=0),dict(original,password='synthetic')]
        for field,value in (('width',4097),('height',True),('bytes',12*1024*1024+1),('sha256','no')):
            changed=copy.deepcopy(original);changed['assets'][0]['previews']['display'][field]=value;invalid.append(changed)
        changed=copy.deepcopy(original);changed['assets'][0]['previews']['display'].update(width=4096,height=4096);invalid.append(changed)
        changed=copy.deepcopy(original);changed['assets'][0]['original_path']='private';invalid.append(changed)
        changed=copy.deepcopy(original);changed['assets'].append(changed['assets'][0]);invalid.append(changed)
        for value in invalid:
            self.value=value;self.publish();self.assertEqual(self.client.get('/home/v1/feed').status_code,503)
        self.value=original;self.value['assets'][0]['previews']['display'].update(width=3840,height=2160)
        self.publish();self.assertEqual(self.client.get('/home/v1/feed').status_code,200)
        # Declaration alone is not an actual 4K derivative: the real JPEG is 8x8.
        self.assertEqual(self.client.get(self.url()).status_code,503)

    def test_missing_changed_aliased_and_outside_previews_never_fall_back(self):
        path=self.media/'display/101.jpg';path.unlink()
        self.assertEqual(self.client.get(self.url()).status_code,404)
        path.write_bytes(self.jpeg[:-1]+b'x');self.assertEqual(self.client.get(self.url()).status_code,503)
        path.unlink();outside=self.root/'outside.jpg';outside.write_bytes(self.jpeg);path.symlink_to(outside)
        self.assertEqual(self.client.get(self.url()).status_code,503)
        self.assertEqual(self.client.get(self.url(asset=999)).status_code,404)
        for suffix in ('&path=../outside.jpg','&variant=grid','&size=4096'):
            self.assertEqual(self.client.get(self.url()+suffix).status_code,400)

    def test_range_and_mismatched_revision_fail_before_jpeg_reads(self):
        actual=home.bounded_read
        def guarded(path,*args):
            if path!=self.path:raise AssertionError('No JPEG should open')
            return actual(path,*args)
        with patch.object(home,'bounded_read',side_effect=guarded):
            self.assertEqual(self.client.get(self.url(),headers={'Range':'bytes=0-10'}).status_code,400)
            self.assertEqual(self.client.head(self.url(),headers={'If-Range':'synthetic'}).status_code,400)
            self.assertEqual(self.client.get(self.url(revision=2)).status_code,409)

    def test_jpeg_metadata_and_oversized_declared_dimensions_are_rejected(self):
        self.assertEqual(home.jpeg_dimensions(self.jpeg),(8,8))
        for value in (b'not jpeg',self.jpeg+b'trailing',self.jpeg[:2]+b'\xff\xe1\x00\x06Exif'+self.jpeg[2:]):
            with self.assertRaises(home.Refused):home.jpeg_dimensions(value)
        aliased=self.root/'manifest-alias';aliased.symlink_to(self.path)
        with self.assertRaises(home.Refused):home.bounded_read(aliased,home.MAX_MANIFEST)

    def test_overload_returns_bounded_retry_without_storage(self):
        semaphore=Mock();semaphore.acquire.return_value=False
        with patch.object(home.threading,'BoundedSemaphore',return_value=semaphore):
            app=home.create_home_feed(self.config)
        with TestClient(app,base_url=self.config.origin,client=('192.168.40.20',1)) as client:
            response=client.get('/home/v1/feed');self.assertEqual(response.status_code,429)
            self.assertEqual(response.headers['retry-after'],'2');semaphore.release.assert_not_called()

    def test_actual_generated_4k_derivative_is_served_without_original_permission(self):
        data=(ROOT/'tests/security/fixtures/home-3840x2160.jpg').read_bytes()
        self.assertEqual(home.jpeg_dimensions(data),(3840,2160))
        meta=dict(width=3840,height=2160,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        self.value['assets'][0]['previews']['display']=meta;self.publish()
        (self.media/'display/101.jpg').write_bytes(data)
        response=self.client.get(self.url());self.assertEqual((response.status_code,response.content),(200,data))
        self.assertFalse(self.client.get('/home/v1/feed').json()['items'][0]['originals_allowed'])

    def test_frozen_contract_example_matches_live_synthetic_feed_and_route_set(self):
        contract=json.loads((ROOT/'docs/security/home-feed-contract-v1.json').read_text())
        self.value=json.loads((ROOT/'docs/security/home-feed-manifest.example.json').read_text());self.publish()
        (self.media/'display/101.jpg').write_bytes((ROOT/'tests/security/fixtures/home-3840x2160.jpg').read_bytes())
        self.assertEqual(self.client.get('/home/v1/feed').json(),contract['feed_response_example'])
        expected={(r['method'],r['path']) for r in contract['routes']}
        actual={(method,r.path) for r in self.app.routes for method in r.methods}
        self.assertEqual(actual,expected)
        self.assertEqual(self.client.get(self.url()).status_code,200)

    def test_config_requires_explicit_narrow_private_networks_and_canonical_origin(self):
        for network in ('0.0.0.0/0','10.0.0.0/8','192.168.40.1/24','127.0.0.0/24','203.0.113.0/24','fd00::/64'):
            with self.assertRaises(ValueError):home.Configuration(self.path,self.media,self.config.origin,(network,))
        for origin in ('http://home.test','https://127.0.0.1','https://home.test:0','https://home.test:443','https://home.test/'):
            with self.assertRaises(ValueError):home.Configuration(self.path,self.media,origin,self.config.allowed_networks)
        with patch.object(home,'bounded_read',side_effect=AssertionError('No file read during construction')):
            home.create_home_feed(self.config)

    def test_launcher_syntax_only_and_mocked_serve_do_not_widen_network(self):
        path=self.root/'config.json'
        value={'version':1,'manifest':str(self.path),'media_root':str(self.media),'origin':self.config.origin,
            'allowed_networks':list(self.config.allowed_networks),'bind_host':'192.168.40.10','port':18444,
            'tls_certificate':str(self.root/'cert.pem'),'tls_private_key':str(self.root/'key.pem')}
        path.write_text(json.dumps(value));out=io.StringIO()
        with redirect_stdout(out):self.assertEqual(home_feed_app.main(['--config',str(path),'--check-config']),0)
        self.assertFalse(json.loads(out.getvalue())['listener_started'])
        config,options=home_feed_app.load_config(path);server=Mock();home_feed_app.serve(config,options,server)
        self.assertFalse(server.call_args.kwargs['proxy_headers']);self.assertEqual(server.call_args.kwargs['workers'],1)
        for update in ({'bind_host':'0.0.0.0'},{'port':443},{'tls_private_key':str(self.media/'private.key')},{'unknown':True}):
            path.write_text(json.dumps(value|update))
            with redirect_stderr(io.StringIO()):self.assertEqual(home_feed_app.main(['--config',str(path),'--serve']),2)
