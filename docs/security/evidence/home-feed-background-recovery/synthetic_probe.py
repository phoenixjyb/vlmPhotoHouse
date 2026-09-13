from pathlib import Path
import sys,tempfile,json,hashlib
stage=Path(sys.argv[1]);kind=sys.argv[2]
access=stage.parent
source=access/('home-feed-e6b2827-pilot/release-e6b2827/source' if kind=='v1' else 'home-catalog-v2-canary-20260912/source')
sys.path.insert(0,str(stage/'scripts'))
import home_feed_background as launcher
import asyncio
from types import SimpleNamespace
from urllib.parse import urlsplit
class TestClient:
 def __init__(self,app,base_url,client):self.app=app;self.origin=urlsplit(base_url);self.peer=client
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def get(self,path,headers=None):return self.request('GET',path,headers)
 def head(self,path,headers=None):return self.request('HEAD',path,headers)
 def request(self,method,path,headers=None):
  async def invoke():
   url=urlsplit(path);status=None;response_headers={};body=bytearray();messages=0;received=False
   scope={'type':'http','asgi':{'version':'3.0','spec_version':'2.4'},'http_version':'1.1','method':method,'scheme':'https','path':url.path,'raw_path':url.path.encode(),'query_string':url.query.encode(),'root_path':'','server':(self.origin.hostname,self.origin.port),'client':self.peer,'headers':[(k.lower().encode(),v.encode()) for k,v in dict({'host':self.origin.netloc},**(headers or {})).items()]}
   async def receive():
    nonlocal received
    if not received:
     received=True;return {'type':'http.request','body':b'','more_body':False}
    await asyncio.Event().wait()
   async def send(message):
    nonlocal status,response_headers,messages
    messages+=1
    assert messages<=128,'ASGI response message limit'
    if message['type']=='http.response.start':status=message['status'];response_headers={k.decode():v.decode() for k,v in message['headers']}
    if message['type']=='http.response.body':
     body.extend(message.get('body',b''));assert len(body)<=512*1024,'ASGI response byte limit'
   await asyncio.wait_for(self.app(scope,receive,send),10)
   return SimpleNamespace(status_code=status,content=bytes(body),headers=response_headers)
  return asyncio.run(invoke())
sha=lambda b:hashlib.sha256(b).hexdigest()
with tempfile.TemporaryDirectory(prefix='synthetic-feed-recovery-',dir=stage) as temp:
 root=Path(temp);media=root/'prepared';media.mkdir()
 jpeg=(stage/'home-8x8.jpg').read_bytes();mp4=(stage/'home-video.mp4').read_bytes()
 preview={'width':8,'height':8,'bytes':len(jpeg),'sha256':sha(jpeg)}
 for variant in ('grid','display'):
  (media/variant).mkdir();(media/variant/'101.jpg').write_bytes(jpeg)
 if kind=='v1':
  manifest=root/'selection.json';manifest.write_text(json.dumps({'version':1,'enabled':True,'revision':1,'feed_id':'synthetic-home','title':'Synthetic','assets':[{'id':101,'caption':'Synthetic','previews':{v:preview for v in ('grid','display')}}]}))
  feed='/home/v1/feed';photo='/home/v1/assets/101/preview?variant=display&revision=1'
 else:
  manifest=root/'control.json';(media/'video').mkdir();(media/'video/102.mp4').write_bytes(mp4)
  chunks=json.dumps([sha(mp4)]).encode();(media/'video/102.chunks.json').write_bytes(chunks)
  video={'state':'ready','mime':'video/mp4','video_codec':'h264','audio_codec':'aac','width':320,'height':180,'duration_ms':500,'bytes':len(mp4),'sha256':sha(mp4),'chunks_sha256':sha(chunks)}
  missing={'state':'unavailable','reason':'not_prepared'}
  catalog={'version':2,'revision':1,'library_id':'synthetic-library','title':'Synthetic','assets':[{'id':102,'kind':'video','label':'Synthetic video','width':None,'height':None,'previews':{v:missing for v in ('grid','display')},'video':video},{'id':101,'kind':'photo','label':'Synthetic photo','width':8,'height':8,'previews':{v:dict(preview,state='ready') for v in ('grid','display')},'video':None}]}
  raw=json.dumps(catalog).encode();(root/'catalog.json').write_bytes(raw)
  manifest.write_text(json.dumps({'version':2,'enabled':True,'revision':1,'catalog_sha256':sha(raw)}))
  feed='/home/v2/catalog';photo='/home/v2/assets/101/preview?variant=display&revision=1'
 (root/'cert.pem').write_text('synthetic');(root/'key.pem').write_text('synthetic')
 config=root/'config.json';origin='https://home.photohouse.test:18444'
 config.write_text(json.dumps({'version':1,'manifest':str(manifest),'media_root':str(media),'origin':origin,'allowed_networks':['192.168.40.0/24'],'bind_host':'192.168.40.10','port':18444,'tls_certificate':str(root/'cert.pem'),'tls_private_key':str(root/'key.pem')}))
 captured=[]
 assert launcher.serve_existing(source,kind,config,lambda app,**options:captured.append((app,options)))==0
 app,options=captured[0];assert options['access_log'] is False and options['proxy_headers'] is False and options['log_config'] is None
 result={'kind':kind,'synthetic':True,'listener_started':False,'existing_source_factory':True,'checks':[]}
 with TestClient(app,base_url=origin,client=('192.168.40.20',1)) as client:
  response=client.get(feed);assert response.status_code==200;result['checks'].append('feed_or_catalog_200')
  response=client.head(photo);assert response.status_code==200 and not response.content and int(response.headers['content-length'])==len(jpeg);result['checks'].append('photo_head_200')
  response=client.get(photo);assert response.content==jpeg;result['checks'].append('synthetic_photo_exact_bytes')
  for path in ('/assets','/health','/auth/session','/voice'):
   assert client.get(path).status_code==403
  result['checks'].append('closed_routes_403')
  if kind=='v2':
   url='/home/v2/assets/102/video?revision=1';response=client.get(url,headers={'Range':'bytes=0-15'})
   assert response.status_code==206 and response.content==mp4[:16] and response.headers['content-range']==f'bytes 0-15/{len(mp4)}'
   result['checks'].append('synthetic_video_range_206_exact_bytes')
 with TestClient(app,base_url=origin,client=('192.168.41.20',1)) as client:
  assert client.get(feed,headers={'X-Forwarded-For':'192.168.40.20'}).status_code==403
  result['checks'].append('denied_peer_spoof_403')
 print(json.dumps(result))
