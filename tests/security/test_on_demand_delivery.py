"""Synthetic original bytes, actual isolated decoder, no sockets or live database."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from fastapi.testclient import TestClient
from app.home_catalog import Configuration, Publication
from app.home_originals import SourceIndex, create_home_originals
from app.photo_delivery import PhotoCache, source_pin
from app.home_feed import Refused
from build_home_source_index import build, inspect_source


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
        self.originals=self.root/'originals';self.originals.mkdir();self.media=self.root/'prepared';self.media.mkdir()
        self.photo=self.originals/'photo.jpg';self.raw=(ROOT/'tests/security/fixtures/home-8x8.jpg').read_bytes();self.photo.write_bytes(self.raw)
        self.video=self.originals/'video.mp4';self.video.write_bytes((ROOT/'tests/security/fixtures/home-video.mp4').read_bytes())
        missing={'state':'unavailable','reason':'not_prepared'}
        self.catalog={'version':2,'revision':9,'library_id':'synthetic','title':'Family', 'assets':[
            {'id':102,'kind':'video','label':'Video','width':320,'height':180,'previews':{'grid':missing,'display':missing},'video':missing},
            {'id':101,'kind':'photo','label':'Photo','width':8,'height':8,'previews':{'grid':missing,'display':missing},'video':None}]}
        data=json.dumps(self.catalog).encode();(self.root/'catalog.json').write_bytes(data);self.catsha=hashlib.sha256(data).hexdigest()
        self.control=self.root/'control.json';self.control.write_text(json.dumps(dict(version=2,revision=9,enabled=True,catalog_sha256=self.catsha)))
        self.config=Configuration(self.control,self.media,'https://photos.example.test',('192.168.40.0/24',))
        self.entries=[dict(id=101,**inspect_source(self.photo,(self.originals,),'photo')),
            dict(id=102,path=str(self.video),identity=list(source_pin(self.video,(self.originals,))),kind='video',mime='video/mp4',width=320,height=180,duration_ms=500,audio_codec='aac')]
        self.cache=PhotoCache(self.root/'cache',guard_factory=lambda root:lambda *a,**kw:None)
        self.install()
    def install(self,allow=True):
        self.index=self.root/'sources.json';raw=json.dumps(dict(version=1,catalog_sha256=self.catsha,assets=self.entries)).encode();self.index.write_bytes(raw)
        self.sources=SourceIndex(Publication(self.config),self.index,hashlib.sha256(raw).hexdigest(),(self.originals,),originals_allowed=allow)
        self.app=create_home_originals(self.config,self.sources,self.cache)
        self.client=TestClient(self.app,base_url=self.config.origin,client=('192.168.40.20',1));self.addCleanup(self.client.close)
    def test_catalog_admits_unprepared_photo_without_decoder_or_filesystem_scan(self):
        with patch('subprocess.Popen',side_effect=AssertionError('Catalog must not decode')):
            result=self.client.get('/home/v3/catalog').json()
        self.assertEqual(result,json.loads((ROOT/'tests/security/fixtures/catalog-v3.json').read_bytes()))
        photo=result['items'][1]
        self.assertEqual(result['total'],2);self.assertEqual(photo['previews']['grid']['state'],'on_demand')
        self.assertEqual(photo['original']['bytes'],len(self.raw));self.assertNotIn('path',str(result));self.assertFalse(self.cache.root.exists())
    def test_original_is_byte_identical_and_range_seekable(self):
        url='/home/v3/assets/101/original?revision=9'
        self.assertEqual(self.client.get(url).content,self.raw)
        res=self.client.get(url,headers={'Range':'bytes=2-8'});self.assertEqual(res.status_code,206);self.assertEqual(res.content,self.raw[2:9])
        self.assertEqual(self.client.head(url).headers['content-length'],str(len(self.raw)))
    def test_preview_created_only_when_requested_and_cache_reused(self):
        url='/home/v3/assets/101/preview?variant=grid&revision=9'
        res=self.client.get(url);self.assertEqual(res.status_code,200,res.text[:100])
        self.assertEqual(self.photo.read_bytes(),self.raw);self.assertEqual(len(list(self.cache.root.glob('*.jpg'))),1)
        with patch('subprocess.Popen',side_effect=AssertionError('Cached hit must not decode')):
            self.assertEqual(self.client.get(url).content,res.content)
        self.assertEqual(res.headers['cache-control'],'no-store')
    def test_disable_and_source_replacement_fail_closed(self):
        self.client.get('/home/v3/catalog')
        self.photo.write_bytes(self.raw+b'changed')
        self.assertEqual(self.client.get('/home/v3/assets/101/original?revision=9').status_code,409)
        control=json.loads(self.control.read_text());control['enabled']=False;self.control.write_text(json.dumps(control))
        self.assertEqual(self.client.get('/home/v3/catalog').status_code,403)
    def test_no_implicit_original_grant_or_prepared_video_bypass(self):
        self.install(allow=False)
        photo=self.client.get('/home/v3/catalog').json()['items'][1]
        self.assertIsNone(photo['original']);self.assertFalse(photo['originals_allowed'])
        self.assertEqual(self.client.get('/home/v3/assets/101/original?revision=9').status_code,404)
        self.assertEqual(self.client.get('/home/v3/assets/102/video?revision=9').status_code,404)
    def test_direct_video_uses_ranges_without_transcoding(self):
        url='/home/v3/assets/102/video?revision=9';raw=self.video.read_bytes()
        with patch('subprocess.Popen',side_effect=AssertionError('Direct video must not encode')):
            for header,expected in [('bytes=0-7',raw[:8]),('bytes=-8',raw[-8:]),('bytes=8-',raw[8:])]:
                res=self.client.get(url,headers={'Range':header});self.assertEqual(res.status_code,206);self.assertEqual(res.content,expected)
        self.assertEqual(self.client.get(url,headers={'Range':'bytes=0-1,3-4'}).status_code,416)
    def test_revoked_peer_credentials_wrong_revision_and_foreign_id(self):
        self.assertEqual(self.client.get('/home/v3/catalog',headers={'Authorization':'Bearer forbidden'}).status_code,403)
        self.assertEqual(self.client.get('/home/v3/assets/101/original?revision=8').status_code,409)
        self.assertEqual(self.client.get('/home/v3/assets/999/original?revision=9').status_code,404)
        other=TestClient(self.app,base_url=self.config.origin,client=('203.0.113.1',1));self.addCleanup(other.close)
        self.assertEqual(other.get('/home/v3/catalog').status_code,403)
    def test_symlink_cannot_escape_even_with_selected_id(self):
        target=self.root/'outside.jpg';target.write_bytes(self.raw);self.photo.unlink();self.photo.symlink_to(target)
        self.assertIn(self.client.get('/home/v3/assets/101/original?revision=9').status_code,(404,409,503))
    def test_busy_renderer_does_not_start_another_worker(self):
        self.cache.slot.acquire()
        try:self.assertEqual(self.client.get('/home/v3/assets/101/preview?variant=grid&revision=9').status_code,429)
        finally:self.cache.slot.release()
    def test_index_reads_selected_database_rows_without_converting_or_writing_db(self):
        db=self.root/'db.sqlite'
        with sqlite3.connect(db) as c:
            c.execute('create table assets(id integer,path text,status text)')
            c.executemany('insert into assets values(?,?,?)',[(101,str(self.photo),'active'),(102,str(self.video),'active'),(999,str(self.photo),'active')])
        before=db.read_bytes();output=self.root/'new-index.json'
        with patch('subprocess.Popen',side_effect=AssertionError('Photo index must not convert')):
            result=build(db,self.root/'catalog.json',(self.originals,),output)
        self.assertEqual(result['indexed'],1);self.assertEqual(db.read_bytes(),before)
        with self.assertRaises(FileExistsError):build(db,self.root/'catalog.json',(self.originals,),output)
    def test_foreign_cache_folder_is_never_adopted_or_cleaned(self):
        self.cache.root.mkdir();foreign=self.cache.root/'family.jpg';foreign.write_bytes(self.raw)
        response=self.client.get('/home/v3/assets/101/preview?variant=grid&revision=9')
        self.assertEqual(response.status_code,503);self.assertEqual(foreign.read_bytes(),self.raw)
    def test_corrupt_owned_cache_is_regenerated_and_pressure_never_starts_worker(self):
        url='/home/v3/assets/101/preview?variant=grid&revision=9'
        expected=self.client.get(url).content
        next(self.cache.root.glob('*.jpg')).write_bytes(b'broken')
        self.assertEqual(self.client.get(url).content,expected)
        def stop(*a,**kw):raise Refused(503,'resource_pressure')
        self.cache.guard_factory=lambda root:stop
        with patch('subprocess.Popen',side_effect=AssertionError('Guard must precede worker')):
            self.assertEqual(self.client.get('/home/v3/assets/101/preview?variant=display&revision=9').status_code,503)
    def test_video_probe_rejects_hevc_rotation_and_uncertain_profiles(self):
        import subprocess
        good={'streams':[{'codec_type':'video','codec_name':'h264','profile':'High','level':41,'pix_fmt':'yuv420p','width':1280,'height':720,'avg_frame_rate':'30/1'}], 'format':{'format_name':'mov,mp4,m4a,3gp,3g2,mj2','duration':'61'}}
        for field,value in [('codec_name','hevc'),('level',51),('pix_fmt','yuv420p10le'),('side_data_list',[{'rotation':90}])]:
            bad=json.loads(json.dumps(good));bad['streams'][0][field]=value
            with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(bad).encode(),b'')):
                self.assertIsNone(inspect_source(self.video,(self.originals,),'video',Path('/synthetic/ffprobe')))
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(good).encode(),b'')):
            self.assertEqual(inspect_source(self.video,(self.originals,),'video',Path('/synthetic/ffprobe'))['duration_ms'],61000)
    def test_source_index_cannot_broaden_selected_catalog(self):
        self.entries[0]['id']=999;self.install()
        self.assertEqual(self.client.get('/home/v3/catalog').status_code,503)
    def test_png_original_and_normalized_jpeg_display(self):
        from PIL import Image
        png=self.originals/'image.png';Image.new('RGBA',(15,30),(10,20,30,150)).save(png)
        self.entries[0]=dict(id=101,**inspect_source(png,(self.originals,),'photo'));self.install()
        res=self.client.get('/home/v3/assets/101/original?revision=9');self.assertEqual(res.headers['content-type'],'image/png');self.assertEqual(res.content,png.read_bytes())
        res=self.client.get('/home/v3/assets/101/preview?variant=display&revision=9');self.assertEqual(res.status_code,200)
        PhotoCache.validate(res.content,'display')

if __name__=='__main__':unittest.main()
