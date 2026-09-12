"""Synthetic-only offline image/video preparation; never use live data or ports."""
import copy
from contextlib import closing
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from native_home_guards import install_windows_asyncio_wakeup

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'backend')]
import prepare_home_catalog as prep
import build_home_catalog
from app.home_catalog import Configuration,create_home_catalog
from fastapi.testclient import TestClient
try:
    from PIL import Image
except ImportError:
    Image=None


@unittest.skipUnless(Image is not None and shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Requires separate Pillow/FFmpeg preparation tooling')
class PreparerTests(unittest.TestCase):
    def setUp(self):
        install_windows_asyncio_wakeup(self)
        tmp=tempfile.TemporaryDirectory(prefix='home-preparer-');self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();self.sources=self.root/'originals';self.sources.mkdir()
        self.db=self.root/'synthetic.sqlite';self.base=self.root/'base';self.workspace=self.root/'workspace'
        self.ffmpeg=Path(shutil.which('ffmpeg')).resolve();self.ffprobe=Path(shutil.which('ffprobe')).resolve()
        self.photo=self.sources/'rotated.jpg';self.video=self.sources/'synthetic.mp4'
        im=Image.new('RGB',(80,40),'red')
        for x in range(40,80):
            for y in range(40):im.putpixel((x,y),(0,0,255))
        exif=Image.Exif();exif[274]=6;exif[270]='SECRET_DESCRIPTION';exif[271]='SECRET_MAKE'
        im.save(self.photo,exif=exif,quality=98)
        shutil.copyfile(ROOT/'tests/security/fixtures/home-video.mp4',self.video)
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('CREATE TABLE assets(id INTEGER PRIMARY KEY,path TEXT,mime TEXT,width INTEGER,height INTEGER,status TEXT)')
            c.executemany('INSERT INTO assets VALUES(?,?,?,?,?,?)',[(101,str(self.photo),'image/jpeg',80,40,'active'),(102,str(self.video),'video/mp4',320,180,'active')])
        build_home_catalog.export(self.db,self.base,1)
        self.before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.db,self.photo,self.video,self.base/'catalog.json',self.base/'control.json')}
        self.budget=prep.Budget(reserve_bytes=0)
        for target in ('socket.socket.bind','socket.socket.connect','os.system'):
            guard=patch(target,side_effect=AssertionError('External network forbidden'));guard.start();self.addCleanup(guard.stop)

    def run_prep(self,ids=(101,),**kwargs):
        return prep.run(self.db,self.sources,self.base/'catalog.json',self.workspace,list(ids),self.ffmpeg,self.ffprobe,budget=kwargs.pop('budget',self.budget),**kwargs)

    def test_exif_orientation_metadata_stripping_and_original_immutability(self):
        state=self.run_prep();item=state['items']['101'];self.assertEqual(item['state'],'ready')
        directory=self.workspace/item['directory']
        for name in ('grid','display'):
            raw=(directory/f'{name}.jpg').read_bytes();self.assertNotIn(b'SECRET',raw)
            with Image.open(directory/f'{name}.jpg') as im:
                self.assertEqual(im.size,(40,80));self.assertEqual(dict(im.getexif()),{})
                self.assertGreater(im.getpixel((20,10))[0],220);self.assertGreater(im.getpixel((20,70))[2],220)
                self.assertEqual(im.mode,'RGB')
        for path,h in self.before.items():self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),h)

    def test_video_normalizes_decodes_previews_and_verified_chunk_hashes(self):
        state=self.run_prep((102,));item=state['items']['102'];self.assertEqual(item['state'],'ready',item)
        directory=self.workspace/item['directory'];prep.verify_ready(directory,item['result'])
        self.assertEqual(item['result']['video']['video_codec'],'h264');self.assertEqual(item['result']['video']['audio_codec'],'aac')
        self.assertEqual(item['result']['previews']['display']['state'],'ready')
        self.assertEqual(hashlib.sha256(self.video.read_bytes()).hexdigest(),self.before[self.video])

    def test_rotated_video_with_subtitles_and_private_tags_becomes_clean_two_track_mp4(self):
        subtitle=self.root/'synthetic.srt';subtitle.write_text('1\n00:00:00,000 --> 00:00:00,400\nSECRET_SUBTITLE\n')
        tagged=self.sources/'tagged.mov'
        subprocess.run([str(self.ffmpeg),'-v','error','-nostdin','-display_rotation','90','-i',str(self.video),'-i',str(subtitle),
                        '-map','0','-map','1','-c','copy','-c:s','mov_text','-metadata','title=SECRET_TITLE',
                        '-metadata:s:v:0','handler_name=SECRET_HANDLER',str(tagged)],check=True,timeout=10)
        original=prep.probe(self.ffprobe,tagged,self.root,self.budget)
        self.assertTrue(any(s.get('side_data_list') for s in original['streams'] if s['codec_type']=='video'))
        with closing(sqlite3.connect(self.db)) as c, c:c.execute('UPDATE assets SET path=?,mime=? WHERE id=102',(str(tagged),'video/quicktime'))
        state=self.run_prep((102,));item=state['items']['102'];self.assertEqual(item['state'],'ready',item)
        directory=self.workspace/item['directory'];data=(directory/'video.mp4').read_bytes()
        self.assertNotIn(b'SECRET',data)
        self.assertEqual((item['result']['video']['width'],item['result']['video']['height']),(180,320))
        value=prep.probe(self.ffprobe,directory/'video.mp4',directory,self.budget)
        self.assertEqual(len(value['streams']),2)

    def test_png_alpha_and_icc_are_normalized_without_metadata(self):
        from PIL import ImageCms,PngImagePlugin
        photo=self.sources/'alpha.png';im=Image.new('RGBA',(20,20),(255,0,0,0))
        im.putpixel((10,10),(255,0,0,255));tags=PngImagePlugin.PngInfo();tags.add_text('description','SECRET_PNG')
        im.save(photo,pnginfo=tags,icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
        with closing(sqlite3.connect(self.db)) as c, c:c.execute('UPDATE assets SET path=?,mime=? WHERE id=101',(str(photo),'image/png'))
        state=self.run_prep();item=state['items']['101'];self.assertEqual(item['state'],'ready',item)
        result=self.workspace/item['directory']/'display.jpg';self.assertNotIn(b'SECRET',result.read_bytes())
        with Image.open(result) as output:
            self.assertNotIn('icc_profile',output.info);self.assertEqual(output.mode,'RGB')
            self.assertTrue(all(v<15 for v in output.getpixel((0,0))))

    def test_output_size_and_duration_caps_never_publish_partial_video(self):
        state=self.run_prep((102,),budget=replace(self.budget,output_bytes=100))
        self.assertEqual(state['items']['102']['state'],'unavailable')
        self.workspace=self.root/'duration-work'
        state=self.run_prep((102,),budget=replace(self.budget,duration_seconds=.1))
        self.assertEqual(state['items']['102'],{'state':'unavailable','reason':'unsupported'})

    def test_chunk_manifest_corruption_blocks_new_publication(self):
        state=self.run_prep((102,));item=state['items']['102'];self.assertEqual(item['state'],'ready')
        (self.workspace/item['directory']/'video.chunks.json').write_text('[]')
        with self.assertRaises(prep.PreparationError):prep.publish(self.workspace,self.root/'publication')
        self.assertFalse((self.root/'publication').exists())

    def test_resume_skips_verified_ready_and_publish_is_new_disabled_full_catalog(self):
        self.run_prep()
        with patch.object(prep,'prepare_one',side_effect=AssertionError('No repeated conversion')):
            self.run_prep()
        output=self.root/'publication';result=prep.publish(self.workspace,output)
        self.assertEqual((result['assets'],result['ready'],result['enabled']),(2,1,False))
        control=json.loads((output/'control.json').read_text());self.assertFalse(control['enabled'])
        config=Configuration(output/'control.json',output/'prepared','https://home.photohouse.test:18444',('192.168.40.0/24',))
        with TestClient(create_home_catalog(config),base_url=config.origin,client=('192.168.40.1',1)) as client:
            self.assertEqual(client.get('/home/v2/catalog').status_code,403)
        control['enabled']=True;(output/'control.json').write_text(json.dumps(control)) # Synthetic ASGI activation only.
        with TestClient(create_home_catalog(config),base_url=config.origin,client=('192.168.40.1',1)) as client:
            response=client.get('/home/v2/catalog');self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['items'][0]['video']['state'],'unavailable')
            url=response.json()['items'][1]['previews']['display']['url'];self.assertEqual(client.get(url).status_code,200)
        with self.assertRaises(prep.PreparationError):prep.publish(self.workspace,output)

    def test_missing_source_failed_checkpoint_and_explicit_retry(self):
        data=self.photo.read_bytes();self.photo.unlink()
        state=self.run_prep();self.assertEqual(state['items']['101'],{'state':'unavailable','reason':'source_missing'})
        self.photo.write_bytes(data)
        self.assertEqual(self.run_prep()['items']['101']['state'],'unavailable')
        self.assertEqual(self.run_prep(retry_failed=True)['items']['101']['state'],'ready')

    def test_corrupt_prepared_bytes_invalidate_resume_and_block_publish(self):
        state=self.run_prep();path=self.workspace/state['items']['101']['directory']/'display.jpg';path.write_bytes(b'bad')
        with self.assertRaises(Exception):prep.publish(self.workspace,self.root/'bad-publication')
        self.assertFalse((self.root/'bad-publication').exists())
        self.assertEqual(self.run_prep()['items']['101']['state'],'unavailable')

    def test_changed_source_does_not_reuse_old_derivatives(self):
        self.run_prep();Image.new('RGB',(80,40),'green').save(self.photo)
        self.assertEqual(self.run_prep()['items']['101']['state'],'unavailable')
        self.assertEqual(self.run_prep(retry_failed=True)['items']['101']['state'],'ready')

    def test_hidden_outside_root_and_symlink_sources_never_decode(self):
        for path,status in [(self.root/'outside.jpg','active'),(self.photo,'hidden')]:
            with closing(sqlite3.connect(self.db)) as c, c:c.execute('UPDATE assets SET path=?,status=? WHERE id=101',(str(path),status))
            with patch.object(prep,'prepare_one',side_effect=AssertionError('No source decode')):
                self.assertEqual(self.run_prep(retry_failed=True)['items']['101']['state'],'unavailable')
        alias=self.sources/'alias.jpg';alias.symlink_to(self.photo)
        with closing(sqlite3.connect(self.db)) as c, c:c.execute('UPDATE assets SET path=?,status=? WHERE id=101',(str(alias),'active'))
        with patch.object(prep,'prepare_one',side_effect=AssertionError('No source decode')):
            self.assertEqual(self.run_prep(retry_failed=True)['items']['101']['state'],'unavailable')

    def test_input_and_pixel_budgets_fail_without_marking_ready(self):
        self.assertEqual(self.run_prep(budget=replace(self.budget,input_bytes=1))['items']['101']['state'],'unavailable')
        other=self.root/'pixel-work';self.workspace=other
        self.assertEqual(self.run_prep(budget=replace(self.budget,pixels=100))['items']['101']['state'],'unavailable')

    def test_interrupted_attempt_is_not_adopted_and_checkpoint_can_resume(self):
        with patch.object(prep,'prepare_one',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.run_prep()
        self.assertEqual(json.loads((self.workspace/'journal.json').read_text())['items'],{})
        self.assertEqual(self.run_prep()['items']['101']['state'],'ready')

    def test_fingerprint_change_and_unknown_workspace_fail_closed(self):
        self.run_prep()
        with self.assertRaises(prep.PreparationError):self.run_prep(budget=replace(self.budget,pixels=999))
        self.workspace=self.root/'foreign';self.workspace.mkdir();(self.workspace/'owned-by-user').write_text('keep')
        with self.assertRaises(prep.PreparationError):self.run_prep()
        self.assertEqual((self.workspace/'owned-by-user').read_text(),'keep')

    def test_timeout_kills_only_owned_child(self):
        started=time.monotonic()
        with self.assertRaises(prep.PreparationError):
            prep.run_process([sys.executable,'-c','import time;time.sleep(30)'],self.root,replace(self.budget,process_seconds=.1))
        self.assertLess(time.monotonic()-started,3)

    def test_disk_and_id_bounds_fail_before_conversion(self):
        with patch.object(prep.shutil,'disk_usage',return_value=shutil._ntuple_diskusage(100,100,0)):
            with self.assertRaises(prep.PreparationError):self.run_prep()
        for ids in ([],[101,101],list(range(1,18)),[999]):
            with self.assertRaises(prep.PreparationError):self.run_prep(ids)

    def test_normalized_probe_rejects_extra_tracks_tags_hdr_and_bad_duration(self):
        item={'streams':[{'codec_type':'video','codec_name':'h264','profile':'High','pix_fmt':'yuv420p','level':41,
                         'avg_frame_rate':'30/1','sample_aspect_ratio':'1:1','width':320,'height':180}],
              'format':{'duration':'1'},'chapters':[]}
        self.assertEqual(prep.normalized_probe(item,1)[1],1)
        for mutate in (lambda x:x['streams'].append({'codec_type':'data'}),
                       lambda x:x['format'].update(tags={'location':'SECRET'}),
                       lambda x:x['streams'][0].update(side_data_list=[{'rotation':90}]),
                       lambda x:x['streams'][0].update(pix_fmt='yuv420p10le'),
                       lambda x:x['format'].update(duration='nan'),
                       lambda x:x['format'].update(duration='5')):
            value=copy.deepcopy(item);mutate(value)
            with self.assertRaises(prep.PreparationError):prep.normalized_probe(value,1)

    def test_publish_never_writes_under_originals_or_follows_checkpoint_paths(self):
        self.run_prep()
        with self.assertRaises(prep.PreparationError):prep.publish(self.workspace,self.sources/'publication')
        journal=json.loads((self.workspace/'journal.json').read_text());journal['items']['101']['directory']='../originals'
        prep.atomic_json(self.workspace/'journal.json',journal)
        with self.assertRaises(prep.PreparationError):prep.publish(self.workspace,self.root/'publication')

    def test_workspace_lock_excludes_second_writer_and_releases_after_exception(self):
        self.workspace.mkdir()
        with self.assertRaises(RuntimeError):
            with prep.workspace_lock(self.workspace):
                with self.assertRaises(OSError):
                    with prep.workspace_lock(self.workspace):self.fail('Second writer acquired lock')
                raise RuntimeError('synthetic interruption')
        with prep.workspace_lock(self.workspace):pass

    def test_interrupted_publication_copy_never_creates_enabled_control(self):
        self.run_prep();output=self.root/'interrupted-publication'
        with patch.object(prep.shutil,'copyfile',side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):prep.publish(self.workspace,output)
        self.assertFalse((output/'control.json').exists())
        self.assertEqual(json.loads((self.workspace/'journal.json').read_text())['items']['101']['state'],'ready')


if __name__=='__main__':unittest.main()
