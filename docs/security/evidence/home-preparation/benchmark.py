"""Synthetic 12MP-photo/1080p-video preparation measurement; no serving or real media."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'backend')]
from PIL import Image
import PIL
import build_home_catalog
import prepare_home_catalog as prep
from app.home_catalog import Configuration,create_home_catalog,CHUNK_BYTES
from fastapi.testclient import TestClient

if os.name!='nt':
    try:os.nice(10)
    except OSError:pass
ffmpeg=Path(shutil.which('ffmpeg')).resolve();ffprobe=Path(shutil.which('ffprobe')).resolve()
with tempfile.TemporaryDirectory(prefix='home-preparation-measure-') as tmp:
    root=Path(tmp).resolve();originals=root/'originals';originals.mkdir()
    photo=originals/'synthetic-photo.jpg';video=originals/'synthetic-video.mp4'
    image=Image.effect_noise((4000,3000),70).convert('RGB')
    exif=Image.Exif();exif[274]=6;exif[270]='SYNTHETIC_ONLY';image.save(photo,quality=90,exif=exif);image.close()
    subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-f','lavfi','-i','testsrc2=size=1920x1080:rate=30',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','6','-c:v','libx264','-threads','1','-filter_threads','1',
                    '-preset','fast','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(video)],check=True,timeout=60)
    db=root/'synthetic.sqlite'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE assets(id INTEGER PRIMARY KEY,path TEXT,mime TEXT,width INTEGER,height INTEGER,status TEXT)')
        c.executemany('INSERT INTO assets VALUES(?,?,?,?,?,?)',[(101,str(photo),'image/jpeg',4000,3000,'active'),(102,str(video),'video/mp4',1920,1080,'active')])
    before={str(p.name):hashlib.sha256(p.read_bytes()).hexdigest() for p in (db,photo,video)}
    base=root/'base';build_home_catalog.export(db,base,1)
    try:
        import resource
        cpu_before=resource.getrusage(resource.RUSAGE_CHILDREN)
    except ImportError:cpu_before=None
    started=time.monotonic()
    state=prep.run(db,originals,base/'catalog.json',root/'workspace',[101,102],ffmpeg,ffprobe)
    elapsed=time.monotonic()-started
    cpu=None
    if cpu_before:
        cpu_after=resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu={'user_seconds':round(cpu_after.ru_utime-cpu_before.ru_utime,3),
             'system_seconds':round(cpu_after.ru_stime-cpu_before.ru_stime,3),
             'maxrss_raw_including_fixture_generation':cpu_after.ru_maxrss,
             'maxrss_units':'bytes on Darwin, KiB on Linux; not an isolated preparation peak'}
    assert all(i['state']=='ready' for i in state['items'].values()),state['items']
    result=prep.publish(root/'workspace',root/'publication')
    assert not result['enabled'] and result['ready']==2
    publication=root/'publication';control=publication/'control.json'
    config=Configuration(control,publication/'prepared','https://home.photohouse.test:18444',('192.168.40.0/24',))
    with TestClient(create_home_catalog(config),base_url=config.origin,client=('192.168.40.20',1)) as client:
        assert client.get('/home/v2/catalog').status_code==403
    state_control=json.loads(control.read_text());state_control['enabled']=True
    control.write_text(json.dumps(state_control))  # Synthetic ASGI-only admission, never a listener.
    with TestClient(create_home_catalog(config),base_url=config.origin,client=('192.168.40.20',1)) as client:
        body=client.get('/home/v2/catalog').json();url=body['items'][0]['video']['url']
        data=(publication/'prepared/video/102.mp4').read_bytes()
        lo,hi=CHUNK_BYTES-16,CHUNK_BYTES+47
        response=client.get(url,headers={'Range':f'bytes={lo}-{hi}'})
        assert response.status_code==206 and response.content==data[lo:hi+1]
        assert client.head(url).headers['content-length']==str(len(data))
        assert client.get(body['items'][1]['previews']['display']['url']).status_code==200
    state_control['enabled']=False;control.write_text(json.dumps(state_control))
    assert before=={str(p.name):hashlib.sha256(p.read_bytes()).hexdigest() for p in (db,photo,video)}
    started=time.monotonic();again=prep.run(db,originals,base/'catalog.json',root/'workspace',[101,102],ffmpeg,ffprobe)
    resume=time.monotonic()-started;assert again==state
    rows=[]
    for aid,item in state['items'].items():
        r=item['result'];rows.append({'synthetic_id':int(aid),'preparation_seconds':r['seconds'],
            'grid':r['previews']['grid'],'display':r['previews']['display'],'video':r['video']})
    print(json.dumps({'synthetic_only':True,'platform':platform.system(),'machine':platform.machine(),'python':platform.python_version(),
        'pillow':PIL.__version__,'ffmpeg':subprocess.check_output([str(ffmpeg),'-version'],text=True).splitlines()[0],
        'inputs':{'photo_pixels':[4000,3000],'photo_bytes':photo.stat().st_size,'video_pixels':[1920,1080],'video_seconds':6,'video_bytes':video.stat().st_size},
        'elapsed_prepare_seconds':round(elapsed,3),'verified_resume_seconds':round(resume,3),'child_usage':cpu,'items':rows,
        'workspace_bytes':sum(p.stat().st_size for p in (root/'workspace').rglob('*') if p.is_file()),
        'publication_bytes':sum(p.stat().st_size for p in (root/'publication').rglob('*') if p.is_file()),
        'source_and_database_hashes_unchanged':True,'published_enabled':False,'windows_canary_run':False,'listeners':False,
        'prepared_publication_asgi':{'initial_disabled':True,'catalog':True,'valid_mp4_range_across_4mib_boundary':True,'video_head':True,'photo_display':True,'disabled_restored':True}}))
