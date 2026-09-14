"""Synthetic queue and encoder failure contracts; no GPU required."""
from contextlib import closing
import json
import unittest
from unittest.mock import patch
import test_home_library as fixture
import prepare_home_catalog as prep
import prepare_home_library as lib

class EncoderBatchTests(unittest.TestCase):
    setUp=fixture.LibraryTests.setUp
    guard=fixture.LibraryTests.guard
    item=fixture.LibraryTests.item
    create=fixture.LibraryTests.create
    run_job=fixture.LibraryTests.run_job

    def test_video_queue_resume_does_not_prepare_photos_or_reencode_ready_video(self):
        self.create()
        result=self.run_job(kind='video')
        self.assertEqual(result['run_status'],'video_queue_drained')
        self.assertFalse(result['queue_drained'])
        self.assertEqual(self.item(101)['status'],'pending')
        self.assertEqual(self.item(102)['status'],'ready')
        with patch.object(prep,'prepare_one',side_effect=AssertionError('duplicate encoding')):
            self.assertEqual(self.run_job(kind='video')['ready'],1)
        self.assertTrue(self.run_job()['verified_complete'])

    def test_gpu_encode_failure_stops_queue_without_silent_cpu_fallback(self):
        lib.create(self.db,self.sources,self.job,self.ffmpeg,self.ffprobe,self.base,2,
                   self.budget,encoder='h264_nvenc',gpu=1)
        job=lib.load_job(self.job)
        self.assertEqual(job['encoder'],{'name':'h264_nvenc','gpu':1})
        real=prep.run_process;calls=[]
        def run(args,*a,**kw):
            if 'h264_nvenc' in args:
                calls.append(args);raise prep.PreparationError()
            return real(args,*a,**kw)
        with patch.object(prep,'run_process',side_effect=run):
            result=self.run_job(kind='video')
        self.assertEqual(result['run_status'],'nvenc_encode_failed')
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][calls[0].index('-gpu')+1],'1')
        self.assertEqual(self.item(102)['status'],'working')
        self.assertEqual(self.item(101)['status'],'pending')
        self.assertEqual(result['ready'],0)

    def test_encoder_settings_are_pinned_and_invalid_selection_cannot_create_job(self):
        for encoder,gpu in [('auto',0),('h264_nvenc',True),('h264_nvenc',-1),('libx264',1)]:
            with self.assertRaises(ValueError):
                lib.create(self.db,self.sources,self.job,self.ffmpeg,self.ffprobe,self.base,2,
                           self.budget,encoder=encoder,gpu=gpu)
            self.assertFalse(self.job.exists())
        self.create()
        p=self.job/'job.json';data=json.loads(p.read_text());data['encoder']['name']='h264_nvenc';p.write_text(json.dumps(data))
        with self.assertRaises(ValueError):lib.load_job(self.job)

    def test_invalid_kind_cannot_modify_checkpoint(self):
        self.create();before=(self.job/'state.sqlite').read_bytes()
        with self.assertRaises(ValueError):self.run_job(kind='everything')
        self.assertEqual((self.job/'state.sqlite').read_bytes(),before)

if __name__=='__main__':unittest.main()
