"""Fresh-process smoke of explicitly extracted synthetic home-feed bundle."""
from pathlib import Path
from contextlib import ExitStack,redirect_stdout
import hashlib,io,json,sys
from unittest.mock import patch
root=Path(sys.argv[1]).resolve(strict=True)
sys.path[:0]=[str(root/'source/backend'),str(root/'source/scripts')]
with ExitStack() as guards:
 for target in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system','sqlite3.connect'):
  guards.enter_context(patch(target,side_effect=AssertionError('External state forbidden')))
 import app.home_feed as feed
 import home_feed_app
 from fastapi.testclient import TestClient
 assert Path(feed.__file__).resolve().is_relative_to(root/'source')
 assert Path(home_feed_app.__file__).resolve().is_relative_to(root/'source')
 config=feed.Configuration(root/'fixture/selection.json',root/'fixture/prepared','https://home.photohouse.test:18444',('192.168.40.0/24',))
 config_path=root/'synthetic-config.json'
 config_path.write_text(json.dumps(dict(version=1,manifest=str(config.manifest),media_root=str(config.media_root),origin=config.origin,allowed_networks=list(config.allowed_networks),bind_host='192.168.40.10',port=18444,tls_certificate=str(root/'not-present-cert.pem'),tls_private_key=str(root/'not-present-key.pem'))))
 with redirect_stdout(io.StringIO()):assert home_feed_app.main(['--config',str(config_path),'--check-config'])==0
 contract=json.loads((root/'source/docs/security/home-feed-contract-v1.json').read_text())
 count=0
 def check(client,path,status,method='GET',headers=None):
  global count
  response=client.request(method,path,headers=headers)
  assert response.status_code==status
  assert response.headers['cache-control']=='no-store'
  count+=1;return response
 app=feed.create_home_feed(config)
 with TestClient(app,base_url=config.origin,client=('192.168.40.20',1234)) as client:
  result=check(client,'/home/v1/feed',200);assert result.json()==contract['feed_response_example']
  item=result.json()['items'][0]
  display=check(client,item['previews']['display']['url'],200)
  assert hashlib.sha256(display.content).hexdigest()==item['previews']['display']['sha256']
  assert feed.jpeg_dimensions(display.content)==(3840,2160)
  head=check(client,item['previews']['grid']['url'],200,method='HEAD');assert not head.content
  check(client,'/auth/session',403)
  check(client,item['previews']['display']['url'],400,headers={'Range':'bytes=0-10'})
  selection=json.loads(config.manifest.read_text());selection['enabled']=False;selection['revision']=2
  pending=root/'fixture/selection.pending';pending.write_text(json.dumps(selection));pending.replace(config.manifest)
  check(client,'/home/v1/feed',403)
  selection['enabled']=True;selection['assets']=[];selection['revision']=3
  pending.write_text(json.dumps(selection));pending.replace(config.manifest)
  assert check(client,'/home/v1/feed',200).json()['total']==0
  check(client,item['previews']['display']['url'],409)
  check(client,'/home/v1/assets/101/preview?variant=display&revision=3',404)
 with TestClient(app,base_url=config.origin,client=('203.0.113.20',1234)) as client:
  check(client,'/home/v1/feed',403,headers={'X-Forwarded-For':'192.168.40.20'})
print(json.dumps(dict(package_smoke='pass',asgi_checks=count,config_syntax_check='pass',actual_4k_fixture=True,listeners_opened=False,host_accessed=False,real_media_accessed=False)))
