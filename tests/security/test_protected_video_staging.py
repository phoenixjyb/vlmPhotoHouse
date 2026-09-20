"""Staging uses tiny synthetic files; no remote service, originals or real data."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import test_protected_video_export as fixtures
import stage_protected_videos as staging
from app.access.prepared_video import PreparedVideos
from app.home_catalog import identity

sha = fixtures.sha


class StagingTests(unittest.TestCase):
    def setUp(self):
        fixtures.ExportTests.setUp(self)
        self.config = self.root/'server.json'
        self.destination = self.root/'protected-copy'
        self.derived = self.root/'derived'; self.derived.mkdir()
        self.cert = self.root/'cert.pem'; self.cert.write_text('synthetic')
        self.key = self.root/'key.pem'; self.key.write_text('synthetic')
        self.config.write_text(json.dumps(dict(format_version=1,database=str(self.database),
            web_origin='https://gallery.example.test:8443',original_roots=[str(self.sources)],
            derived_root=str(self.derived),bind_host='127.0.0.1',port=8443,
            tls_certificate=str(self.cert),tls_private_key=str(self.key))))

    def run_stage(self, **kwargs):
        args = dict(config_path=self.config,workspace=self.workspace,destination=self.destination,
                    output=self.output,asset_ids=[101])
        args.update(kwargs)
        # Isolate disk-space policy from the test runner's available disk.
        with patch.object(staging.shutil, 'disk_usage', return_value=type('Space', (), {'free':100*staging.GIB})()):
            return staging.stage(**args)

    def test_plan_writes_nothing_and_does_not_claim_hash_verification(self):
        before = set(self.root.rglob('*'))
        result = self.run_stage()
        self.assertEqual(before, set(self.root.rglob('*')))
        self.assertEqual(result['asset_ids'], [101])
        self.assertFalse(result['staged'])
        self.assertFalse(result['source_hashes_verified'])

    def test_stage_independent_copy_plays_and_preserves_live_inputs(self):
        source_files = [self.database,self.workspace/'state.sqlite',self.source,self.workspace/'job.json']
        before = {p:sha(p.read_bytes()) for p in source_files}
        result = self.run_stage(write=True)
        self.assertTrue(result['source_hashes_verified'])
        self.assertFalse(result['activated'])
        self.assertFalse((self.destination/'INCOMPLETE').exists())
        self.assertFalse(self.output.with_name(self.output.name+'.pending').exists())
        # A changed preparation file must not change the independent snapshot.
        (self.workspace/'asset-101-abcdefgh/video.mp4').write_bytes(b'changed')
        provider = PreparedVideos(self.output,result['index_sha256'],self.destination)
        reader = provider.open(101,identity(self.source))
        try:
            self.assertEqual(reader.chunk(0),self.raw)
        finally:
            reader.close()
        self.assertEqual(before,{p:sha(p.read_bytes()) for p in before})
        self.assertFalse(any(p.suffix == '.mov' for p in self.destination.rglob('*')))

    def test_missing_duplicate_and_empty_selection_refused_before_write(self):
        for ids in ([],[101,101],[999],[True],list(range(1,102))):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.run_stage(asset_ids=ids,write=True)
            self.assertFalse(self.destination.exists())

    def test_unready_row_refused(self):
        with closing(sqlite3.connect(self.workspace/'state.sqlite')) as db:
            db.execute("UPDATE items SET status='working'"); db.commit()
        with self.assertRaisesRegex(ValueError,'not ready'):
            self.run_stage(write=True)
        self.assertFalse(self.destination.exists())

    def test_byte_budget_and_disk_reserve_refuse_before_write(self):
        with self.assertRaisesRegex(ValueError,'budget'):
            self.run_stage(write=True,max_bytes=1)
        with patch.object(staging.shutil,'disk_usage',return_value=type('Space',(),{'free':0})()):
            with self.assertRaisesRegex(ValueError,'disk reserve'):
                staging.stage(self.config,self.workspace,self.destination,self.output,[101],write=True)
        self.assertFalse(self.destination.exists())

    def test_existing_outputs_never_overwritten(self):
        self.output.write_bytes(b'keep')
        with self.assertRaises(ValueError):self.run_stage(write=True)
        self.assertEqual(self.output.read_bytes(),b'keep')
        self.assertFalse(self.destination.exists())
        self.output.unlink(); self.destination.mkdir()
        marker=self.destination/'user.txt';marker.write_bytes(b'keep')
        with self.assertRaises(ValueError):self.run_stage(write=True)
        self.assertEqual(marker.read_bytes(),b'keep')

    def test_overlap_and_symlink_paths_refused(self):
        for parent in (self.workspace,self.sources,self.derived):
            with self.subTest(parent=parent),self.assertRaises(ValueError):
                self.run_stage(destination=parent/'staged',write=True)
            self.assertFalse((parent/'staged').exists())
        alias=self.root/'alias';alias.symlink_to(self.workspace,target_is_directory=True)
        with self.assertRaises(ValueError):self.run_stage(workspace=alias,write=True)
        alias.unlink();alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):self.run_stage(destination=alias/'staged',write=True)
        alias.unlink()
        video=self.workspace/'asset-101-abcdefgh/video.mp4'
        video.unlink();video.symlink_to(self.source)
        with self.assertRaises(Exception):self.run_stage(write=True)
        self.assertFalse(self.destination.exists())

    def test_changed_original_never_produces_final_index(self):
        self.source.write_bytes(b'changed-original')
        with self.assertRaisesRegex(ValueError,'Source changed'):
            self.run_stage(write=True)
        self.assertFalse(self.output.exists())
        self.assertTrue((self.destination/'INCOMPLETE').exists())

    def test_corrupt_prepared_copy_never_produces_final_index(self):
        video=self.workspace/'asset-101-abcdefgh/video.mp4'
        video.write_bytes(b'X'+self.raw[1:])
        with self.assertRaisesRegex(ValueError,'hash changed'):
            self.run_stage(write=True)
        self.assertFalse(self.output.exists())
        self.assertTrue((self.destination/'INCOMPLETE').exists())

    def test_preparation_changes_during_copy_are_refused(self):
        original=staging.copy_video
        def changed(*args):
            original(*args)
            with closing(sqlite3.connect(self.workspace/'state.sqlite')) as db:
                db.execute("UPDATE items SET status='pending'");db.commit()
        with patch.object(staging,'copy_video',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'Preparation changed'):
                self.run_stage(write=True)
        self.assertFalse(self.output.exists())

    def test_copy_error_leaves_explicit_incomplete_folder(self):
        with patch.object(staging,'copy_video',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):self.run_stage(write=True)
        self.assertFalse(self.output.exists())
        self.assertTrue((self.destination/'INCOMPLETE').exists())
        with self.assertRaises(ValueError):self.run_stage(write=True)

    def test_original_identity_is_not_rebased_to_copy(self):
        result=self.run_stage(write=True)
        index=json.loads(self.output.read_bytes())
        self.assertEqual(index['assets'][0]['source_identity'],list(identity(self.source)))
        provider=PreparedVideos(self.output,result['index_sha256'],self.destination)
        self.source.write_bytes(b'changed')
        with self.assertRaises(Exception):provider.open(101,identity(self.source))

    def test_existing_pending_index_refuses_before_copy(self):
        pending=self.output.with_name(self.output.name+'.pending');pending.write_bytes(b'keep')
        with self.assertRaises(ValueError):self.run_stage(write=True)
        self.assertFalse(self.destination.exists())
        self.assertEqual(pending.read_bytes(),b'keep')

    def test_copy_has_no_live_database_read_lock(self):
        original=staging.copy_video
        def inspect(*args):
            for path,sql in ((self.database,'UPDATE assets SET width=width'),
                             (self.workspace/'state.sqlite','UPDATE items SET id=id')):
                with closing(sqlite3.connect(path,timeout=0.05)) as db:
                    db.execute(sql);db.commit()
            return original(*args)
        with patch.object(staging,'copy_video',side_effect=inspect):
            self.assertTrue(self.run_stage(write=True)['staged'])

    def test_marker_cleanup_failure_prevents_final_publication(self):
        original=Path.unlink
        def fail_marker(path,*args,**kwargs):
            if path.name=='INCOMPLETE':raise OSError('denied')
            return original(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail_marker),self.assertRaises(OSError):
            self.run_stage(write=True)
        self.assertFalse(self.output.exists())
        self.assertTrue((self.destination/'INCOMPLETE').exists())

    def test_link_failure_preserves_incomplete_state_and_existing_output(self):
        def race(*args):
            self.output.write_bytes(b'other-owner')
            raise FileExistsError()
        with patch.object(staging.os,'link',side_effect=race),self.assertRaises(FileExistsError):
            self.run_stage(write=True)
        self.assertEqual(self.output.read_bytes(),b'other-owner')
        self.assertTrue((self.destination/'INCOMPLETE').exists())

    def test_pending_cleanup_failure_reports_completed_publication(self):
        original=Path.unlink
        def fail_pending(path,*args,**kwargs):
            if path.name.endswith('.pending'):raise OSError('denied')
            return original(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail_pending):result=self.run_stage(write=True)
        self.assertTrue(result['staged'])
        self.assertTrue(result['pending_index_retained'])
        self.assertTrue(self.output.exists())
        self.assertFalse((self.destination/'INCOMPLETE').exists())


if __name__=='__main__':unittest.main()
