"""Real offline export over tiny synthetic ready receipts; no encoder or listener."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import export_protected_videos as exporter
from app.access.prepared_video import PreparedVideos
from app.home_catalog import identity


def sha(raw): return hashlib.sha256(raw).hexdigest()


class ExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.sources = self.root/'originals'; self.sources.mkdir()
        self.workspace = self.root/'workspace'; self.workspace.mkdir()
        self.output = self.root/'private-index.json'
        self.database = self.root/'assets.sqlite'
        self.source = self.sources/'101.mov'; self.source.write_bytes(b'original-synthetic-source')
        source_row = (str(self.source), 'video/quicktime', 320, 180, 'active')
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('CREATE TABLE assets(id INTEGER PRIMARY KEY,path,mime,width,height,status)')
            db.execute('INSERT INTO assets VALUES (101,?,?,?,?,?)',source_row); db.commit()
        directory = self.workspace/'asset-101-abcdefgh'; directory.mkdir()
        raw = (ROOT/'tests/security/fixtures/home-video.mp4').read_bytes()
        (directory/'video.mp4').write_bytes(raw)
        chunks = json.dumps([sha(raw)]).encode(); (directory/'video.chunks.json').write_bytes(chunks)
        video = dict(state='ready',mime='video/mp4',video_codec='h264',audio_codec=None,width=320,height=180,duration_ms=500,bytes=len(raw),sha256=sha(raw),chunks_sha256=sha(chunks))
        result = dict(video=video,previews={},source_sha256=sha(self.source.read_bytes()),seconds=1)
        job = json.dumps(dict(version=1,database=str(self.database),source_root=str(self.sources))).encode()
        (self.workspace/'job.json').write_bytes(job)
        metadata_hash = sha(json.dumps(source_row).encode())
        (directory/'receipt.json').write_text(json.dumps(dict(job_sha256=sha(job),metadata_hash=metadata_hash,result=result)))
        with closing(sqlite3.connect(self.workspace/'state.sqlite')) as db:
            db.execute('CREATE TABLE meta(key,value)'); db.execute('INSERT INTO meta VALUES (?,?)',('job_sha256',json.dumps(sha(job))))
            db.execute('CREATE TABLE items(id,kind,status,directory,result,metadata_hash,source_hash)')
            db.execute('INSERT INTO items VALUES (?,?,?,?,?,?,?)',(101,'video','ready',directory.name,json.dumps(result),metadata_hash,result['source_sha256'])); db.commit()
        self.raw = raw

    def test_export_roundtrip_preserves_sources_and_refuses_overwrite(self):
        before = {p:sha(p.read_bytes()) for p in (self.database,self.workspace/'state.sqlite',self.source)}
        report = exporter.export(self.database,self.workspace,self.output)
        self.assertEqual(report['ready_videos'],1); self.assertFalse(report['activated'])
        provider = PreparedVideos(self.output,report['index_sha256'],self.workspace)
        reader = provider.open(101,identity(self.source))
        try: self.assertEqual(reader.chunk(0),self.raw)
        finally: reader.close()
        self.assertEqual(before,{p:sha(p.read_bytes()) for p in before})
        with self.assertRaises(ValueError): exporter.export(self.database,self.workspace,self.output)

    def test_changed_original_not_exported(self):
        self.source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Source changed'): exporter.export(self.database,self.workspace,self.output)
        self.assertFalse(self.output.exists())

    def test_changed_prepared_bytes_not_exported(self):
        (self.workspace/'asset-101-abcdefgh/video.mp4').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Prepared bytes changed'): exporter.export(self.database,self.workspace,self.output)
        self.assertFalse(self.output.exists())

    def test_wrong_job_receipt_or_source_metadata_refused(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("UPDATE assets SET mime='video/mp4'"); db.commit()
        with self.assertRaisesRegex(ValueError,'Source metadata changed'): exporter.export(self.database,self.workspace,self.output)
        self.assertFalse(self.output.exists())

    def test_index_cannot_be_written_into_media_or_workspace(self):
        for parent in (self.sources,self.workspace):
            with self.assertRaises(ValueError): exporter.export(self.database,self.workspace,parent/'index.json')
            self.assertFalse((parent/'index.json').exists())

    def test_hashing_holds_no_asset_or_preparation_database_read_lock(self):
        original = exporter.hash_file
        def inspect(*args,**kwargs):
            for database, sql in ((self.database,'UPDATE assets SET width=width'),
                                  (self.workspace/'state.sqlite','UPDATE items SET id=id')):
                with closing(sqlite3.connect(database,timeout=0.05)) as db:
                    db.execute(sql); db.commit()
            return original(*args,**kwargs)
        with patch.object(exporter,'hash_file',side_effect=inspect):
            self.assertEqual(exporter.export(self.database,self.workspace,self.output)['ready_videos'],1)

    def test_source_row_changed_during_hash_is_rejected(self):
        original = exporter.hash_file
        def inspect(*args,**kwargs):
            result = original(*args,**kwargs)
            with closing(sqlite3.connect(self.database,timeout=0.05)) as db:
                db.execute('UPDATE assets SET width=321'); db.commit()
            return result
        with patch.object(exporter,'hash_file',side_effect=inspect), self.assertRaisesRegex(ValueError,'Source changed'):
            exporter.export(self.database,self.workspace,self.output)
        self.assertFalse(self.output.exists())

    def test_no_ready_videos_is_explicit_empty_index(self):
        with closing(sqlite3.connect(self.workspace/'state.sqlite')) as db:
            db.execute("UPDATE items SET status='working'"); db.commit()
        result = exporter.export(self.database,self.workspace,self.output)
        self.assertEqual(result['ready_videos'],0)
