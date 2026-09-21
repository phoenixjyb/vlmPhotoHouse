"""Generated large/long media only. No live config, models, database or ports."""
from contextlib import closing
from dataclasses import asdict, replace
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_home_preparer as fixture
import prepare_home_catalog as prep
import prepare_home_library as library
import home_media_worker as worker
from home_preparation_resources import Guard, JobStopped
from app.home_catalog import Configuration, create_home_catalog, CHUNK_BYTES
from fastapi.testclient import TestClient
Image = fixture.Image


@unittest.skipUnless(Image is not None and shutil.which('ffmpeg') and shutil.which('ffprobe'), 'CPU fixture tools required')
class MediaProfileTests(unittest.TestCase):
    def setUp(self):
        fixture.PreparerTests.setUp(self)
        self.profile = replace(prep.PROFILES['library-sdr-v1'], reserve_bytes=1)
        self.output = self.root/'attempt'; self.output.mkdir()

    def guard(self, path=None):
        return Guard(path or self.output, 1, observe=lambda child: (8*1024**3,1024))

    def prepare(self, source=None, kind='photo', budget=None, guard=None):
        return prep.prepare_one(source or self.photo, kind, self.output, self.ffmpeg,
                                self.ffprobe, budget or self.profile, guard or self.guard())

    def test_named_profile_bounds_are_pinned_and_stay_inside_wire_limits(self):
        b=self.profile
        self.assertEqual((b.input_bytes,b.duration_seconds,b.jpeg_source_pixels,b.decoded_pixels),
                         (8*1024**3,900,256000000,16000000))
        self.assertEqual(library.profile(b),asdict(b))
        for changes in ({'decoded_pixels':40000001},{'jpeg_source_pixels':256000001},
                        {'hash_seconds':b.asset_seconds+1},{'jpeg_source_pixels':-1}):
            with self.assertRaises(ValueError): library.profile(replace(b,**changes))
        self.assertIn('scripts/home_media_worker.py',library.code_pin())

    def test_phone_quality_is_opt_in_and_pins_bounded_encoder_settings(self):
        phone=prep.VIDEO_QUALITIES['phone-sdr-v1']
        self.assertEqual(prep.video_encoder_args(), ['-c:v','libx264','-threads','1','-preset','fast','-crf','23','-profile:v','high','-level:v','4.1'])
        args=prep.video_encoder_args(quality=phone)
        self.assertIn('-b:v',args);self.assertEqual(args[args.index('-b:v')+1],'2M')
        self.assertEqual(args[args.index('-maxrate')+1],'3M')
        self.assertEqual(prep.VIDEO_QUALITIES['phone-sdr-v1'],prep.quality_config(asdict(phone)))

    def test_phone_quality_real_tiny_encode_is_720p_max_and_validator_compatible(self):
        source=self.sources/'phone-source.mp4';output=self.root/'phone-attempt';output.mkdir()
        subprocess.run([str(self.ffmpeg),'-v','error','-nostdin','-f','lavfi','-i','testsrc=size=1920x1080:rate=12',
                        '-t','1','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(source)],check=True,timeout=30)
        result=prep.prepare_one(source,'video',output,self.ffmpeg,self.ffprobe,self.profile,
                                self.guard(output),quality=prep.VIDEO_QUALITIES['phone-sdr-v1'])
        self.assertLessEqual(result['video']['width'],1280);self.assertLessEqual(result['video']['height'],720)
        prep.verify_ready(output,result,self.profile,self.guard(output),prep.VIDEO_QUALITIES['phone-sdr-v1'])

    def test_hash_above_old_512_mib_cap_and_chunk_manifest_match_independent_oracle(self):
        large=self.sources/'sparse-synthetic.bin';size=512*1024**2+17
        with large.open('wb') as stream: stream.truncate(size)
        before=large.stat().st_mtime_ns
        value=prep.file_fingerprint(large,self.profile.input_bytes,seconds=30,guard=self.guard(),chunks=True)
        digest=hashlib.sha256();chunks=[]
        with large.open('rb') as stream:
            while data:=stream.read(CHUNK_BYTES): digest.update(data);chunks.append(hashlib.sha256(data).hexdigest())
        self.assertEqual(value,{'sha256':digest.hexdigest(),'bytes':size,'chunks':chunks})
        self.assertEqual(large.stat().st_mtime_ns,before)
        with self.assertRaises(prep.PreparationError): prep.file_hash(large,prep.Budget().input_bytes)

    def test_hash_deadline_terminates_owned_worker_and_preserves_source(self):
        observed=[];original=prep.subprocess.Popen
        def spawn(*args,**kwargs):
            child=original(*args,**kwargs);observed.append(child);return child
        started=time.monotonic()
        with patch.object(prep.subprocess,'Popen',side_effect=spawn):
            with self.assertRaises(prep.PreparationError) as caught:
                prep.file_hash(self.photo,self.profile.input_bytes,seconds=.001,guard=self.guard())
        self.assertEqual(caught.exception.reason,'hash_timeout')
        self.assertLess(time.monotonic()-started,3)
        self.assertTrue(observed);self.assertTrue(all(p.poll() is not None for p in observed))
        self.assertEqual(prep.file_hash(self.photo,self.profile.input_bytes),self.before[self.photo])

    def test_operator_stop_during_hash_is_resumable_and_not_a_media_error(self):
        seen=[]
        def stop(child): seen.append(child);raise JobStopped('operator_stop')
        with self.assertRaises(JobStopped): prep.file_hash(self.photo,self.profile.input_bytes,guard=stop)
        self.assertIsNotNone(seen[0].poll())
        self.assertEqual(prep.file_hash(self.photo,self.profile.input_bytes,guard=self.guard()),self.before[self.photo])

    def test_image_header_and_decode_are_owned_children_and_memory_stop_is_enforced(self):
        seen=[]
        def observe(child):
            if child: seen.append(child)
            return 8*1024**3,2*1024**3 if child else 1024
        guard=Guard(self.output,1,observe=observe)
        with self.assertRaises(JobStopped): prep.photo_info(self.photo,self.output,self.profile,guard)
        self.assertTrue(seen);self.assertIsNotNone(seen[0].poll())
        self.assertFalse((self.output/'display.jpg').exists())
        result=self.prepare();prep.verify_ready(self.output,result,self.profile,self.guard())

    def test_large_baseline_jpeg_is_subsampled_before_decode_with_orientation_and_icc(self):
        from PIL import ImageCms
        source=self.sources/'synthetic-48mp.jpg'
        with Image.new('RGB',(8000,6000),(245,10,10)) as image:
            image.paste((10,10,245),(4000,0,8000,6000))
            exif=Image.Exif();exif[274]=6;exif[270]='PRIVATE_SYNTHETIC_DESCRIPTION'
            image.save(source,quality=95,exif=exif,icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
        original_hash=prep.file_hash(source,self.profile.input_bytes)
        # The shared Mac can have <4GiB available; its earlier default-floor run
        # correctly stopped. Windows qualification uses the real 4GiB floor.
        floor=4*1024**3 if sys.platform=='win32' else 256*1024**2
        guard=Guard(self.output,1,minimum_ram=floor)
        result=self.prepare(source,guard=guard)
        if os.environ.get('PH_PROFILE_EVIDENCE'):
            evidence=Path(os.environ['PH_PROFILE_EVIDENCE']);evidence.mkdir(parents=True,exist_ok=True)
            (evidence/'large-jpeg.json').write_text(json.dumps({'source_pixels':48000000,
                'resources':guard.summary(),'test_minimum_ram_bytes':floor,'seconds':result['seconds']}))
        plan=json.loads((self.output/'photo.decode.json').read_text())
        self.assertEqual(plan['source_size'],[8000,6000]);self.assertEqual(plan['decoded_size'],[4000,3000])
        self.assertEqual(plan['subsampling'],2)
        for name in ('grid','display'):
            path=self.output/f'{name}.jpg';self.assertNotIn(b'PRIVATE_SYNTHETIC',path.read_bytes())
            with Image.open(path) as image:
                self.assertEqual(image.mode,'RGB');self.assertEqual(dict(image.getexif()),{})
                self.assertNotIn('icc_profile',image.info)
                self.assertAlmostEqual(image.width/image.height,.75,delta=.01)
                self.assertGreater(image.getpixel((image.width//2,image.height//4))[0],210)
                self.assertGreater(image.getpixel((image.width//2,3*image.height//4))[2],210)
        self.assertLess(guard.summary()['observed_peak_rss'],1024**3)
        self.assertGreater(guard.summary()['samples'],0)
        self.assertEqual(prep.file_hash(source,self.profile.input_bytes),original_hash)
        prep.verify_ready(self.output,result,self.profile,self.guard())

    def test_200mp_synthetic_header_plans_bounded_decode_without_claiming_full_decode(self):
        # Alter only a small synthetic JPEG header. This tests dimension planning,
        # not decoding a valid 200MP image; real giant-JPEG qualification is separate.
        raw=bytearray(self.photo.read_bytes());marker=raw.index(b'\xff\xc0')
        raw[marker+5:marker+7]=(10000).to_bytes(2,'big')
        raw[marker+7:marker+9]=(20000).to_bytes(2,'big')
        source=self.sources/'header-only.jpg';source.write_bytes(raw)
        plan=prep.photo_info(source,self.output,self.profile,self.guard())
        self.assertEqual(plan['source_size'],[20000,10000]);self.assertEqual(plan['decoded_size'],[5000,2500])
        self.assertEqual(plan['subsampling'],4)
        self.assertEqual(prep.photo_info(source,self.output,self.budget,self.guard())['reason'],'pixel_budget')

    def test_large_progressive_jpeg_and_large_png_are_deferred_without_full_decode(self):
        profile=replace(self.profile,decoded_pixels=1000000)
        progressive=self.sources/'progressive.jpg';png=self.sources/'oversize.png'
        with Image.new('RGB',(2000,1500),'green') as image:
            image.save(progressive,progressive=True);image.save(png)
        self.assertEqual(prep.photo_info(progressive,self.output,profile,self.guard())['reason'],'progressive_jpeg_profile')
        self.assertEqual(prep.photo_info(png,self.output,profile,self.guard())['reason'],'decoded_pixel_budget')
        self.assertFalse((self.output/'display.jpg').exists())

    def test_mpo_and_hdr_remain_explicit_profile_deferrals(self):
        with self.assertRaises(worker.Deferred) as caught:
            worker.configure_image(SimpleNamespace(size=(100,100),format='MPO',n_frames=8),asdict(self.profile))
        self.assertEqual(str(caught.exception),'photo_format_profile')
        value=prep.probe(self.ffprobe,self.video,self.output,self.profile)
        next(s for s in value['streams'] if s['codec_type']=='video')['color_transfer']='smpte2084'
        with patch.object(prep,'probe',return_value=value):
            self.assertEqual(library.precheck(self.video,'video',self.profile,self.output,self.ffprobe,self.guard()),'hdr_tonemap_profile')

    def test_decoder_cannot_fall_back_to_full_size_when_draft_is_ineffective(self):
        fake=SimpleNamespace(size=(8000,6000),width=8000,height=6000,format='JPEG',mode='RGB',info={},n_frames=1,draft=lambda *a:None)
        with self.assertRaises(worker.Deferred) as caught: worker.configure_image(fake,asdict(self.profile))
        self.assertEqual(str(caught.exception),'decoded_pixel_budget')

    def test_all_eight_exif_orientations_keep_color_quadrants_after_subsampling(self):
        colors=((245,10,10),(10,245,10),(10,10,245),(245,245,10))
        expected=((0,1,2,3),(1,0,3,2),(3,2,1,0),(2,3,0,1),
                  (0,2,1,3),(2,0,3,1),(3,1,2,0),(1,3,0,2))
        budget=replace(self.profile,decoded_pixels=100000)
        for orientation,quadrants in enumerate(expected,1):
            with self.subTest(orientation=orientation):
                source=self.sources/f'orientation-{orientation}.jpg'
                with Image.new('RGB',(1200,800)) as image:
                    for box,color in zip(((0,0,600,400),(600,0,1200,400),(0,400,600,800),(600,400,1200,800)),colors):image.paste(color,box)
                    exif=Image.Exif();exif[274]=orientation;image.save(source,quality=98,exif=exif)
                output=self.root/f'orientation-{orientation}';output.mkdir()
                prep.photo_info(source,output,budget,self.guard(output),output=output)
                with Image.open(output/'display.jpg') as image:
                    self.assertEqual(image.size,(200,300) if orientation>=5 else (300,200))
                    for point,index in zip(((1,1),(3,1),(1,3),(3,3)),quadrants):
                        actual=image.getpixel((point[0]*image.width//4,point[1]*image.height//4))
                        for value,wanted in zip(actual,colors[index]):self.assertAlmostEqual(value,wanted,delta=8)

    def test_empty_source_is_accounted_as_error_without_attempting_video_probe(self):
        source=self.sources/'empty.mp4';source.touch()
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('UPDATE assets SET path=? WHERE id=102',(str(source),))
        job=self.root/'library';library.create(self.db,self.sources,job,self.ffmpeg,self.ffprobe,self.base,2,self.profile)
        with patch.object(prep,'probe',side_effect=AssertionError('No probing an empty source')):
            state=library.run(job,guard=self.guard(job))
        self.assertEqual(state['counts'],{'error':1,'ready':1});self.assertEqual(state['reasons'],{'source_empty':1})
        self.assertFalse(state['verified_complete'])

    def test_resume_and_publish_use_the_reviewed_hash_deadline(self):
        job=self.root/'library';library.create(self.db,self.sources,job,self.ffmpeg,self.ffprobe,self.base,2,self.profile)
        library.run(job,guard=self.guard(job));original=prep.file_hash;observed=[]
        def record(path,*args,**kwargs):
            if path in (self.photo,self.video):observed.append(kwargs.get('seconds'))
            return original(path,*args,**kwargs)
        with patch.object(prep,'file_hash',side_effect=record),patch.object(prep,'prepare_one',side_effect=AssertionError('No duplicate conversion')):
            self.assertTrue(library.run(job,guard=self.guard(job))['verified_complete'])
            library.publish(job,self.root/'publication',guard=self.guard(job))
        self.assertEqual(observed,[900,900,900,900])

    def qualification(self,job,ids):
        config=json.loads((job/'job.json').read_text())
        plan=self.root/'qualification.json'
        plan.write_text(json.dumps({'revision':config['revision'],'base_sha256':config['base_sha256'],'asset_ids':ids}))
        return plan

    def test_reviewed_qualification_selects_cases_then_full_run_reuses_them(self):
        job=self.root/'library';library.create(self.db,self.sources,job,self.ffmpeg,self.ffprobe,self.base,2,self.profile)
        plan=self.qualification(job,[101])
        state=library.run(job,guard=self.guard(job),qualification=plan)
        self.assertEqual(state['run_status'],'qualification_complete');self.assertEqual(state['counts'],{'pending':1,'ready':1})
        self.assertFalse(state['verified_complete']);self.assertEqual(state['qualification']['asset_ids'],[101])
        original=prep.prepare_one;converted=[]
        def record(source,*args,**kwargs):converted.append(source);return original(source,*args,**kwargs)
        with patch.object(prep,'prepare_one',side_effect=record):
            self.assertTrue(library.run(job,guard=self.guard(job))['verified_complete'])
        self.assertEqual(converted,[self.video])

    def test_qualification_plan_is_bounded_and_bound_to_the_full_snapshot(self):
        job=self.root/'library';library.create(self.db,self.sources,job,self.ffmpeg,self.ffprobe,self.base,2,self.profile)
        path=self.qualification(job,[101]);base=json.loads(path.read_text())
        for changes in ({'revision':3},{'base_sha256':'0'*64},{'asset_ids':[999]},
                        {'asset_ids':[101,101]},{'asset_ids':[]},{'asset_ids':list(range(17))},
                        {'unreviewed':True},{'asset_ids':[True]}):
            with self.subTest(changes=changes):
                path.write_text(json.dumps(dict(base,**changes)))
                with self.assertRaises(ValueError):library.run(job,guard=self.guard(job),qualification=path)
                self.assertEqual(library.status(job)['counts'],{'pending':2})

    def test_qualification_even_of_all_items_does_not_claim_full_run_verification(self):
        job=self.root/'library';library.create(self.db,self.sources,job,self.ffmpeg,self.ffprobe,self.base,2,self.profile)
        plan=self.qualification(job,[101,102]);state=library.run(job,guard=self.guard(job),qualification=plan)
        self.assertTrue(state['all_ready']);self.assertFalse(state['verified_complete'])
        with patch.object(prep,'prepare_one',side_effect=AssertionError('No duplicate qualification encoding')):
            self.assertTrue(library.run(job,guard=self.guard(job))['verified_complete'])

    def test_corrupt_icc_profile_never_silently_drops_color_conversion(self):
        source=self.sources/'bad-icc.jpg'
        with Image.new('RGB',(80,40),'red') as image: image.save(source,icc_profile=b'not an ICC profile')
        with self.assertRaises(prep.PreparationError): self.prepare(source)
        self.assertFalse((self.output/'display.jpg').exists())

    def test_long_video_duration_validation_rejects_seconds_of_missing_tail(self):
        # Use a normalized output to retain valid stream metadata in the oracle.
        result=self.prepare(self.video,'video')
        normalized=prep.probe(self.ffprobe,self.output/'video.mp4',self.output,self.profile)
        normalized['format']['duration']='123'
        with self.assertRaises(prep.PreparationError): prep.normalized_probe(normalized,125)

    def test_decode_deadline_after_encoding_never_returns_ready(self):
        original=prep.run_process
        def run(args,directory,budget,*rest,**kwargs):
            if '-xerror' in args and '-f' in args and 'null' in args:
                return original([sys.executable,'-c','import time;time.sleep(30)'],directory,
                                replace(budget,process_seconds=.05),*rest,**kwargs)
            return original(args,directory,budget,*rest,**kwargs)
        with patch.object(prep,'run_process',side_effect=run):
            with self.assertRaises(prep.PreparationError): self.prepare(self.video,'video')
        self.assertFalse((self.output/'video.chunks.json').exists())

    def test_real_multi_minute_multi_chunk_synthetic_video_prepare_resume_and_ranges(self):
        source=self.sources/'synthetic-125s.mp4'
        subprocess.run([str(self.ffmpeg),'-v','error','-nostdin','-filter_threads','1','-filter_complex_threads','1','-f','lavfi','-i',
            'color=c=gray:s=320x180:r=12,noise=alls=50:allf=t+u:all_seed=7',
            '-t','125','-c:v','libx264','-threads','1','-preset','ultrafast','-crf','18',
            '-pix_fmt','yuv420p',str(source)],check=True,timeout=90)
        self.assertEqual(library.precheck(source,'video',self.budget,self.output,self.ffprobe,self.guard()),'duration_budget')
        with closing(sqlite3.connect(self.db)) as c,c: c.execute('UPDATE assets SET path=? WHERE id=102',(str(source),))
        job=self.root/'library';library.create(self.db,self.sources,job,self.ffmpeg,self.ffprobe,self.base,2,self.profile)
        guard=self.guard(job);state=library.run(job,guard=guard);self.assertTrue(state['verified_complete'],state)
        with closing(library.connect(job,True)) as c:
            item=c.execute('SELECT * FROM items WHERE id=102').fetchone();result=json.loads(item['result']);directory=job/item['directory']
        self.assertGreater(result['video']['duration_ms'],120000)
        self.assertGreater(result['video']['bytes'],CHUNK_BYTES)
        if os.environ.get('PH_PROFILE_EVIDENCE'):
            evidence=Path(os.environ['PH_PROFILE_EVIDENCE']);evidence.mkdir(parents=True,exist_ok=True)
            (evidence/'long-video.json').write_text(json.dumps({'source_seconds':125,
                'result':result['video'],'seconds':result['seconds']}))
        with patch.object(prep,'prepare_one',side_effect=AssertionError('No re-encoding verified long media')):
            self.assertTrue(library.run(job,guard=guard)['verified_complete'])
        output=self.root/'publication';library.publish(job,output,guard=guard)
        control=json.loads((output/'control.json').read_text());self.assertFalse(control['enabled'])
        control['enabled']=True;prep.atomic_json(output/'control.json',control)  # Synthetic in-process ASGI only.
        config=Configuration(output/'control.json',output/'prepared','https://home.photohouse.test:18444',('192.168.40.0/24',))
        with TestClient(create_home_catalog(config),base_url=config.origin,client=('192.168.40.1',1)) as client:
            assets=client.get('/home/v2/catalog').json()['items'];video=next(a for a in assets if a['id']==102)['video']
            url=video['url'];length=result['video']['bytes']
            for start,end in ((0,31),(CHUNK_BYTES-16,CHUNK_BYTES+16),(length-32,length-1)):
                response=client.get(url,headers={'Range':f'bytes={start}-{end}'})
                self.assertEqual(response.status_code,206)
                with (directory/'video.mp4').open('rb') as f:f.seek(start);expected=f.read(end-start+1)
                self.assertEqual(response.content,expected)
            self.assertEqual(client.get(url,headers={'Range':f'bytes={length}-'}).status_code,416)


if __name__=='__main__': unittest.main()
