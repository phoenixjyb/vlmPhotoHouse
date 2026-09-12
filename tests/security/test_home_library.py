"""Full-snapshot coordinator tests use only generated media and synthetic SQLite."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import copy
import json
import shutil
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import test_home_preparer as fixture
import prepare_home_catalog as prep
import prepare_home_library as library
from home_preparation_resources import Guard,JobStopped,memory
import build_home_catalog
Image=fixture.Image


@unittest.skipUnless(Image is not None and shutil.which('ffmpeg') and shutil.which('ffprobe'),'CPU fixture tools required')
class LibraryTests(unittest.TestCase):
    def setUp(self):
        fixture.PreparerTests.setUp(self)
        self.job=self.root/'full-library';self.budget=replace(self.budget,reserve_bytes=1)

    def guard(self,workspace=None):
        return Guard(workspace or self.job,1,observe=lambda process:(8*1024**3,1024))

    def create(self,seed=None,revision=2,previous=None,workspace=None,budget=None):
        return library.create(self.db,self.sources,workspace or self.job,self.ffmpeg,self.ffprobe,
                              previous or self.base,revision,budget or self.budget,seed)

    def run_job(self,**kwargs):
        return library.run(self.job,guard=kwargs.pop('guard',self.guard()),**kwargs)

    def legacy(self):
        fixture.PreparerTests.run_prep(self,(101,102))
        return library.seed_description(self.workspace,prep.file_hash(self.workspace/'journal.json',64*1024**2),'legacy')

    def item(self,aid):
        with closing(library.connect(self.job,True)) as c:return dict(c.execute('SELECT * FROM items WHERE id=?',(aid,)).fetchone())

    def test_automatically_traverses_more_than_sixteen_and_resume_never_reconverts(self):
        with closing(sqlite3.connect(self.db)) as c,c:
            c.executemany('INSERT INTO assets VALUES(?,?,?,?,?,?)',[(i,str(self.photo),'image/jpeg',80,40,'active') for i in range(103,122)])
        self.create();result=self.run_job()
        self.assertEqual(result['total'],21);self.assertEqual(result['ready'],21);self.assertTrue(result['all_ready'])
        with patch.object(prep,'prepare_one',side_effect=AssertionError('No duplicate conversion')):
            self.assertTrue(self.run_job()['all_ready'])
        self.assertEqual(self.item(101)['attempts'],1)

    def test_receipt_recovers_interruption_before_ready_transaction_without_reconversion(self):
        self.create()
        with patch.object(library,'complete',side_effect=KeyboardInterrupt):
            result=self.run_job()
        self.assertEqual(result['run_status'],'interrupted');self.assertEqual(self.item(102)['status'],'working')
        original=prep.prepare_one;converted=[]
        def track(source,*args,**kwargs):converted.append(source);return original(source,*args,**kwargs)
        with patch.object(prep,'prepare_one',side_effect=track):self.assertTrue(self.run_job()['all_ready'])
        self.assertEqual(converted,[self.photo]);self.assertEqual(self.item(102)['attempts'],1)

    def test_unverified_interrupted_attempt_is_retained_and_not_adopted(self):
        self.create()
        def interrupted(source,kind,directory,*args,**kwargs):
            (directory/'video.mp4').write_bytes(b'unverified');raise KeyboardInterrupt
        with patch.object(prep,'prepare_one',side_effect=interrupted):self.run_job()
        old=self.job/self.item(102)['directory'];self.assertTrue(self.run_job()['all_ready'])
        self.assertEqual((old/'video.mp4').read_bytes(),b'unverified');self.assertEqual(self.item(102)['attempts'],2)

    def test_pinned_legacy_and_library_carry_forward_into_new_immutable_revision(self):
        seed=self.legacy();self.create(seed)
        with patch.object(prep,'prepare_one',side_effect=AssertionError('No conversion during verified carry')):
            self.assertTrue(self.run_job()['all_ready'])
        self.assertEqual(json.loads(self.item(101)['origin'])['kind'],'carry')
        output=self.root/'publication';result=library.publish(self.job,output,guard=self.guard())
        self.assertEqual(result['revision'],2);self.assertFalse(result['enabled'])
        with self.assertRaises(ValueError):self.run_job()
        with self.assertRaises(ValueError):library.publish(self.job,self.root/'different',guard=self.guard())
        seed2=library.seed_description(self.job,prep.file_hash(self.job/'state.sqlite',256*1024**2),'library')
        next_job=self.root/'revision3';self.create(seed2,3,output,next_job)
        with patch.object(prep,'prepare_one',side_effect=AssertionError('No duplicate conversion in next revision')):
            self.assertTrue(library.run(next_job,guard=self.guard(next_job))['all_ready'])
        self.assertEqual(json.loads((output/'control.json').read_text())['revision'],2)

    def test_carry_rejects_tampered_pin_and_wrong_source_provenance(self):
        seed=self.legacy()
        with self.assertRaises(ValueError):library.seed_description(self.workspace,'0'*64,'legacy')
        state=json.loads((self.workspace/'journal.json').read_text());state['fingerprint']['source_root']=str(self.root/'other')
        prep.atomic_json(self.workspace/'journal.json',state)
        seed=library.seed_description(self.workspace,prep.file_hash(self.workspace/'journal.json',64*1024**2),'legacy')
        with self.assertRaises(ValueError):self.create(seed)

    def test_corrupt_seed_derivative_never_becomes_ready(self):
        seed=self.legacy();state=json.loads((self.workspace/'journal.json').read_text())
        (self.workspace/state['items']['101']['directory']/'grid.jpg').write_bytes(b'corrupt')
        self.create(seed)
        with patch.object(prep,'prepare_one',side_effect=AssertionError('Do not silently bypass bad seed')):
            result=self.run_job()
        self.assertEqual(result['ready'],1);self.assertEqual(result['counts']['error'],1)
        self.assertFalse(result['all_ready']);self.assertTrue(result['queue_drained'])

    def test_changed_original_is_reprepared_instead_of_reusing_seed(self):
        seed=self.legacy();Image.new('RGB',(80,40),'green').save(self.photo)
        self.create(seed);original=prep.prepare_one;converted=[]
        def track(source,*args,**kwargs):converted.append(source);return original(source,*args,**kwargs)
        with patch.object(prep,'prepare_one',side_effect=track):self.assertTrue(self.run_job()['all_ready'])
        self.assertEqual(converted,[self.photo]);self.assertEqual(json.loads(self.item(101)['origin'])['kind'],'prepared')

    def test_hidden_source_is_not_carried_and_visibility_drift_blocks_publication(self):
        seed=self.legacy();self.create(seed)
        with closing(sqlite3.connect(self.db)) as c,c:c.execute("UPDATE assets SET status='hidden' WHERE id=101")
        original=prep.file_hash
        def hash_guard(path,*args):
            if path==self.photo:raise AssertionError('Hidden original must not be read')
            return original(path,*args)
        with patch.object(prep,'file_hash',side_effect=hash_guard):result=self.run_job()
        self.assertEqual(result['counts']['excluded'],1);self.assertEqual(result['ready'],1)
        output=self.root/'publication'
        with self.assertRaisesRegex(ValueError,'scope_changed'):library.publish(self.job,output,True,guard=self.guard())
        self.assertFalse(output.exists())

    def test_wrong_revision_and_changed_job_implementation_fail_closed(self):
        with self.assertRaises(ValueError):self.create(revision=1)
        self.create()
        with patch.object(library,'code_pin',return_value={}):
            with self.assertRaises(ValueError):self.run_job()
        state=json.loads((self.job/'job.json').read_text());state['revision']=9;prep.atomic_json(self.job/'job.json',state)
        with self.assertRaises(ValueError):self.run_job()

    def test_resource_pressure_stops_queue_without_marking_media_unsupported(self):
        self.create();guard=Guard(self.job,1,observe=lambda process:(0,1024))
        result=self.run_job(guard=guard)
        self.assertEqual(result['run_status'],'memory_pressure');self.assertEqual(result['counts'],{'pending':2})
        (self.job/'stop.flag').write_text('stop')
        self.assertEqual(self.run_job()['run_status'],'operator_stop');(self.job/'stop.flag').unlink()
        with patch.object(shutil,'disk_usage',return_value=shutil._ntuple_diskusage(1,1,0)):
            self.assertEqual(self.run_job()['run_status'],'disk_pressure')
        self.assertTrue(self.run_job()['all_ready'])

    def test_guard_interrupt_kills_only_its_owned_child(self):
        seen=[]
        def stop(child):seen.append(child);raise JobStopped('synthetic_pressure')
        started=time.monotonic()
        with self.assertRaises(JobStopped):
            prep.run_process([sys.executable,'-c','import time;time.sleep(30)'],self.root,self.budget,guard=stop)
        self.assertLess(time.monotonic()-started,3);self.assertIsNotNone(seen[0].poll())

    def test_native_memory_observation_reports_current_process(self):
        available,rss=memory()
        self.assertGreater(available,0);self.assertGreater(rss,0)

    def test_memory_stop_during_probe_remains_resumable_work(self):
        self.create()
        guard=Guard(self.job,1,observe=lambda child:(8*1024**3,2*1024**3 if child else 1024))
        result=self.run_job(guard=guard)
        self.assertEqual(result['run_status'],'owned_memory_limit')
        self.assertEqual(self.item(102)['status'],'working');self.assertFalse(result['verified_complete'])
        self.assertTrue(self.run_job()['verified_complete'])

    def test_valid_long_video_is_deferred_by_budget_not_declared_bad_media(self):
        longer=self.sources/'longer.mp4'
        subprocess.run([str(self.ffmpeg),'-v','error','-nostdin','-stream_loop','7','-i',str(self.video),
                        '-c','copy',str(longer)],check=True,timeout=10)
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('UPDATE assets SET path=? WHERE id=102',(str(longer),))
        self.create(budget=replace(self.budget,duration_seconds=2));result=self.run_job()
        self.assertEqual(result['reasons'],{'duration_budget':1});self.assertEqual(result['ready'],1)
        self.assertFalse(result['verified_complete']);self.assertTrue(longer.is_file())

    def test_hdr_requires_a_tonemap_profile_without_unreviewed_conversion(self):
        self.create();probe=prep.probe(self.ffprobe,self.video,self.root,self.budget)
        video=next(s for s in probe['streams'] if s['codec_type']=='video')
        video.update(color_transfer='smpte2084',pix_fmt='yuv420p10le')
        with patch.object(prep,'probe',return_value=probe):result=self.run_job()
        self.assertEqual(result['reasons'],{'hdr_tonemap_profile':1});self.assertFalse(result['all_ready'])

    def test_profile_deferral_and_errors_are_not_full_coverage(self):
        self.create(budget=replace(self.budget,pixels=100))
        result=self.run_job();self.assertEqual(result['counts']['deferred'],2);self.assertFalse(result['all_ready'])
        with self.assertRaisesRegex(ValueError,'library_not_all_ready'):
            library.publish(self.job,self.root/'refused',guard=self.guard())
        out=self.root/'partial';library.publish(self.job,out,allow_partial=True,guard=self.guard())
        cat=json.loads((out/'catalog.json').read_text())
        self.assertTrue(all(a['previews']['grid']=={'state':'unavailable','reason':'not_prepared'} for a in cat['assets']))

    def test_interrupted_publication_resumes_verified_copies_without_conversion(self):
        self.create();self.run_job();out=self.root/'publication';original=library.copy_file;copied=[]
        def stop(source,target,guard):
            original(source,target,guard);copied.append(target)
            if len(copied)==1:raise KeyboardInterrupt
        with patch.object(library,'copy_file',side_effect=stop):
            with self.assertRaises(KeyboardInterrupt):library.publish(self.job,out,guard=self.guard())
        self.assertFalse((out/'control.json').exists());first=copied[0];stamp=first.stat().st_mtime_ns
        with patch.object(prep,'prepare_one',side_effect=AssertionError('No reconversion during publish')):
            result=library.publish(self.job,out,guard=self.guard())
        self.assertFalse(result['enabled']);self.assertEqual(first.stat().st_mtime_ns,stamp)

    def test_new_visible_asset_and_changed_original_block_stale_publish(self):
        self.create();self.run_job()
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?)',(103,str(self.photo),'image/jpeg',80,40,'active'))
        with self.assertRaisesRegex(ValueError,'scope_changed'):library.publish(self.job,self.root/'new',guard=self.guard())
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('DELETE FROM assets WHERE id=103')
        Image.new('RGB',(80,40),'green').save(self.photo)
        with self.assertRaisesRegex(ValueError,'source_changed'):library.publish(self.job,self.root/'new',guard=self.guard())

    def test_pressure_mid_copy_retains_unverified_temporary_and_resumes_without_encoding(self):
        self.create();self.run_job();out=self.root/'publication';normal=self.guard()
        def stop(*args,**kwargs):
            if not kwargs.get('force'):raise JobStopped('copy_pressure')
            normal(*args,**kwargs)
        stop.reserve=1;stop.summary=normal.summary
        with self.assertRaises(JobStopped):library.publish(self.job,out,guard=stop)
        self.assertFalse((out/'control.json').exists());self.assertTrue(list(out.rglob('.copy-*')))
        with patch.object(prep,'prepare_one',side_effect=AssertionError('No duplicate encoding')):
            self.assertEqual(library.publish(self.job,out,guard=self.guard())['ready'],2)

    def test_resume_never_overwrites_an_externally_enabled_control(self):
        self.create();self.run_job();out=self.root/'publication'
        with patch.object(library,'copy_file',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):library.publish(self.job,out,guard=self.guard())
        owner=json.loads((out/'build-owner.json').read_text())
        control={'version':2,'enabled':True,'revision':2,'catalog_sha256':owner['catalog_sha256']}
        prep.atomic_json(out/'control.json',control)
        with self.assertRaisesRegex(ValueError,'control_changed'):library.publish(self.job,out,guard=self.guard())
        self.assertEqual(json.loads((out/'control.json').read_text()),control)

    def test_run_limit_is_a_resumable_operator_cap_not_a_batch_selection_requirement(self):
        self.create();result=self.run_job(max_items=1)
        self.assertEqual(result['ready'],1);self.assertEqual(result['run_status'],'qualification_item_limit')
        self.assertTrue(self.run_job()['all_ready'])
        with self.assertRaises(ValueError):self.run_job(max_items=-1)

    def test_publication_disk_shortage_leaves_control_absent(self):
        self.create();self.run_job();out=self.root/'publication'
        original=shutil.disk_usage
        def disk(path):
            if Path(path)==out.parent:return shutil._ntuple_diskusage(100,99,1)
            return original(path)
        with patch.object(shutil,'disk_usage',side_effect=disk):
            with self.assertRaises(JobStopped):library.publish(self.job,out,guard=self.guard())
        self.assertFalse((out/'control.json').exists())


if __name__=='__main__':unittest.main()
