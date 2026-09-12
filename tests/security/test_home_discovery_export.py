"""Standalone synthetic snapshots only; no live SQLite or network."""
from contextlib import ExitStack
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'backend')]
import export_home_discovery as exp
from build_home_discovery_export_fixture import create
from app.home_discovery import Configuration, create_home_discovery
from fastapi.testclient import TestClient


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='discovery-export-test-');self.addCleanup(self.tmp.cleanup)
        self.root=create(Path(self.tmp.name).resolve()/'fixture')
        self.db=self.root/'snapshot.sqlite';self.candidate=self.root/'candidate';self.request=self.root/'request.json'
        for name in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system'):
            guard=patch(name,side_effect=AssertionError('External operation forbidden'));guard.start();self.addCleanup(guard.stop)

    def mutate(self, fn):
        value=json.loads(self.request.read_text());fn(value);self.request.write_bytes(exp.packed(value))

    def sql(self, text):
        with sqlite3.connect(self.db) as c:c.executescript(text)

    def build(self):return exp.build(self.db,self.candidate,self.request)

    def seal(self):
        receipt=exp.review(self.db,self.candidate,self.request,self.root/'review.json')
        approval={'version':1,'plan_sha256':receipt['plan_sha256'],**{k:True for k in ('approve_selection','approve_roster','approve_assignments','approve_regions','approve_metadata')}}
        (self.root/'synthetic-approval.json').write_bytes(exp.packed(approval))
        return receipt

    def publish(self):return exp.publish(self.db,self.candidate,self.request,self.root/'review.json',self.root/'synthetic-approval.json',self.root/'output')

    def test_review_and_output_deterministic_disabled_private_and_hash_bound(self):
        before={p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        one,files=self.build();two,_=self.build();self.assertEqual(one,two)
        self.seal();receipt=self.publish();self.assertFalse(receipt['enabled'])
        for name,raw in files.items():
            p=self.root/'output'/name;self.assertEqual(raw,p.read_bytes());self.assertEqual(exp.sha(raw),receipt['output_hashes'][name])
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
        for name,raw in before.items():self.assertEqual((self.root/name).read_bytes(),raw)
        self.assertNotIn(str(self.root),exp.packed(one).decode())
        self.assertEqual((self.root/'output').stat().st_mode & 0o777,0o700)

    def test_sql_readonly_in_memory_no_schema_or_sidecar_writes(self):
        before=self.db.read_bytes();connections=[];real=sqlite3.connect;trace=[]
        def connect(path,*args,**kwargs):
            self.assertEqual(path,':memory:');conn=real(path,*args,**kwargs);conn.set_trace_callback(trace.append);connections.append(conn);return conn
        with patch.object(exp.sqlite3,'connect',side_effect=connect):self.build()
        self.assertEqual(self.db.read_bytes(),before)
        self.assertFalse(any(Path(str(self.db)+suffix).exists() for suffix in ('-wal','-shm','-journal')))
        self.assertTrue(trace)
        # sqlite3.deserialize internally attaches its byte buffer to main; no disk DB is opened.
        self.assertEqual(trace[0],"ATTACH x AS 'main'")
        self.assertTrue(all(s.startswith(('PRAGMA query_only=ON','BEGIN','SELECT','ROLLBACK')) for s in trace[1:]),trace)

    def test_candidate_and_selection_are_exact_not_all_active_consent(self):
        for ids in ([101,102,103],[101,102,103,104,999],[101,101,103,104],[104,103,102,101]):
            original=self.request.read_bytes();self.mutate(lambda v:v.update(selected_asset_ids=ids))
            with self.assertRaises(Exception):self.build()
            self.request.write_bytes(original)
        self.mutate(lambda v:v.update(catalog_sha256='0'*64))
        with self.assertRaisesRegex(exp.ExportError,'catalog_hash_mismatch'):self.build()

    def test_hidden_deleted_and_missing_ids_fail_instead_of_silent_drop(self):
        for status in ('hidden','deleted'):
            self.sql("UPDATE assets SET status='"+status+"' WHERE id=101")
            with self.assertRaisesRegex(exp.ExportError,'hidden_missing'):self.build()
        self.sql('DELETE FROM assets WHERE id=101')
        with self.assertRaisesRegex(exp.ExportError,'hidden_missing'):self.build()

    def test_schema_missing_columns_views_and_write_trigger_not_used(self):
        self.sql("CREATE TABLE audit(id INTEGER); CREATE TRIGGER watch AFTER UPDATE ON assets BEGIN INSERT INTO audit VALUES(1); END;")
        self.build()
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM audit').fetchone()[0],0)
        self.sql('ALTER TABLE captions RENAME COLUMN text TO old_text')
        with self.assertRaises(sqlite3.DatabaseError):self.build()
        self.sql('DROP TABLE captions; CREATE VIEW captions AS SELECT 1 AS id;')
        with self.assertRaisesRegex(exp.ExportError,'schema_missing_or_view'):self.build()

    def test_wal_header_and_any_sidecar_refused(self):
        for suffix in ('-wal','-shm','-journal'):
            p=Path(str(self.db)+suffix);p.write_bytes(b'synthetic')
            with self.assertRaisesRegex(exp.ExportError,'snapshot_sidecar'):self.build()
            p.unlink()
        raw=bytearray(self.db.read_bytes());raw[18:20]=b'\x02\x02';self.db.write_bytes(raw)
        with self.assertRaisesRegex(exp.ExportError,'standalone_snapshot'):self.build()

    def test_caption_edited_priority_ambiguity_supersession_and_oversize(self):
        self.sql("INSERT INTO captions VALUES(5,103,'alternative unedited',0,0),(6,101,'ambiguous',0,0),(7,104,'edited wins',1,0)")
        p,_=self.build();rows={r['id']:r for r in p['plan']['index']['assets']}
        self.assertIsNone(rows[101]['caption_text']);self.assertEqual(rows[103]['caption_text'],'Ｆａｍｉｌｙ at park.')
        self.assertEqual(rows[104]['caption_text'],'edited wins')
        self.sql("INSERT INTO captions VALUES(8,104,'second edit',1,0)")
        p,_=self.build();self.assertEqual(p['plan']['coverage']['caption_states']['ambiguous'],2)
        self.sql('DELETE FROM captions WHERE id=8')
        with sqlite3.connect(self.db) as c:c.execute('UPDATE captions SET text=? WHERE id=7',('字'*1366,))
        p,_=self.build();self.assertEqual(p['plan']['coverage']['caption_states']['oversized'],1)
        self.assertEqual(p['plan']['coverage']['caption_exclusions']['superseded'],1)

    def test_tags_block_duplicate_missing_source_and_kind_preserved(self):
        self.sql("INSERT INTO asset_tags VALUES(6,102,301,'img'),(7,102,301,'manual'),(8,104,999,'cap'),(9,102,302,NULL); UPDATE tags SET type='person' WHERE id=302")
        p,_=self.build();coverage=p['plan']['coverage']
        self.assertEqual(coverage['tag_exclusions'],{'blocked':1,'duplicate_or_conflicting':2,'missing_tag':1})
        self.assertEqual(coverage['tag_sources']['unknown'],1)
        row=next(r for r in p['plan']['index']['assets'] if r['id']==102)
        self.assertEqual(row['person_ids'],[]);self.assertEqual(row['tags'],[{'id':302,'source':'unknown'}])
        self.assertEqual(next(t for t in p['plan']['index']['tags'] if t['id']==302)['kind'],'person')

    def test_seven_unresolved_shortcuts_and_roster_do_not_bless_assignments(self):
        self.mutate(lambda v:v.update(assignment_review=[]))
        p,_=self.build();self.assertTrue(all(not r['person_ids'] for r in p['plan']['index']['assets']))
        self.mutate(lambda v:v.update(roster_review={'people':[],'pinned_person_ids':[],'unresolved_shortcut_count':7}))
        p,_=self.build();self.assertEqual(p['plan']['coverage']['unresolved_shortcuts'],7)
        self.assertNotIn('people',p['plan']['index']['enabled_filters'])
        self.assertEqual(p['plan']['index']['people'],[])

    def test_manual_marker_alone_and_caption_name_never_approve_people(self):
        p,_=self.build();rows={r['id']:r for r in p['plan']['index']['assets']}
        self.assertEqual(rows[104]['person_ids'],[])
        self.assertIn('Sample Child',rows[104]['caption_text'])
        self.mutate(lambda v:v['assignment_review'].append({'face_id':4,'asset_id':104,'person_id':201,'label_source':'dnn'}))
        with self.assertRaisesRegex(exp.ExportError,'unreviewed_assignment'):self.build()

    def test_changed_or_foreign_face_and_unresolved_roster_fail(self):
        self.sql('UPDATE face_detections SET person_id=201 WHERE id=1')
        with self.assertRaisesRegex(exp.ExportError,'assignment_evidence_changed'):self.build()
        self.sql('UPDATE face_detections SET person_id=202 WHERE id=1')
        self.mutate(lambda v:v['roster_review']['people'][0].update(id=None))
        with self.assertRaisesRegex(exp.ExportError,'unresolved_or_duplicate_person'):self.build()

    def test_date_and_region_missing_invalid_and_no_ingest_fallback(self):
        self.sql("UPDATE assets SET taken_at='2026-02-30' WHERE id=101")
        self.mutate(lambda v:v.update(region_review={'locations':[],'assignments':[]}))
        p,_=self.build();self.assertEqual(p['plan']['coverage']['dates'],{'invalid':1,'missing':1,'valid':2})
        self.assertNotIn('locations',p['plan']['index']['enabled_filters'])
        self.assertTrue(all(r['location_ids']==[] for r in p['plan']['index']['assets']))

    def test_zero_partial_and_complete_metadata_coverage(self):
        for ids in ([],[102],[101,102,103,104]):
            self.mutate(lambda v:v.update(indexed_asset_ids=ids,assignment_review=[],region_review={'locations':[],'assignments':[]}))
            p,_=self.build();self.assertEqual(p['plan']['coverage']['indexed_assets'],len(ids))
            self.assertEqual(p['plan']['coverage']['index_complete'],len(ids)==4)
            self.assertEqual(p['plan']['coverage']['metadata_completeness'],'not_inferred')

    def test_media_copy_opt_in_and_variant_coverage(self):
        p,files=self.build();self.assertEqual(p['plan']['coverage']['media']['video'],{'not_prepared':1,'bytes_verified_ready':1})
        self.assertIn('prepared/video/102.mp4',files)
        self.mutate(lambda v:v.update(copy_prepared=False))
        p,files=self.build();self.assertFalse(any(n.startswith('prepared/') for n in files))
        self.assertEqual(p['plan']['coverage']['media']['display']['not_copied'],1)
        self.assertTrue(all(a['previews']['display']['state']=='unavailable' for a in p['plan']['catalog']['assets']))
        self.assertFalse(any(a['video'] and a['video']['state']=='ready' for a in p['plan']['catalog']['assets']))

    def test_prepared_photo_video_chunks_and_symlinks_rejected(self):
        for name in ('grid/101.jpg','video/102.mp4','video/102.chunks.json'):
            p=self.candidate/'prepared'/name;old=p.read_bytes();p.write_bytes(b'corrupt')
            with self.assertRaises(Exception):self.build()
            p.write_bytes(old)
        p=self.candidate/'prepared/grid/101.jpg';p.unlink();p.symlink_to(self.candidate/'prepared/display/101.jpg')
        with self.assertRaises(Exception):self.build()

    def test_approval_explicit_scope_digest_and_no_auto_approval(self):
        self.seal();p=self.root/'synthetic-approval.json';original=p.read_bytes()
        for key in ('approve_selection','approve_roster','approve_assignments','approve_regions','approve_metadata'):
            v=json.loads(original);v[key]=False;p.write_bytes(exp.packed(v))
            with self.assertRaisesRegex(exp.ExportError,'explicit_review_required'):self.publish()
            self.assertFalse((self.root/'output').exists())
        v=json.loads(original);v['plan_sha256']='0'*64;p.write_bytes(exp.packed(v))
        with self.assertRaisesRegex(exp.ExportError,'approval_mismatch'):self.publish()

    def test_input_mutation_invalidates_review_and_output_collision_preserves_work(self):
        self.seal();self.sql("UPDATE captions SET text='changed' WHERE id=1")
        with self.assertRaisesRegex(exp.ExportError,'review_inputs_changed'):self.publish()
        self.assertFalse((self.root/'output').exists())
        p=self.root/'output';p.mkdir();(p/'owned').write_text('preserve')
        with self.assertRaisesRegex(exp.ExportError,'output_collision'):self.publish()
        self.assertEqual((p/'owned').read_text(),'preserve')

    def test_review_tampering_and_request_mutation_rejected(self):
        self.seal();p=self.root/'review.json';v=json.loads(p.read_text());v['plan']['index']['revision']=100;p.write_bytes(exp.packed(v))
        with self.assertRaisesRegex(exp.ExportError,'review_digest_mismatch'):self.publish()
        p.unlink();(self.root/'synthetic-approval.json').unlink();self.seal()
        self.mutate(lambda v:v.update(discovery_revision=8))
        with self.assertRaisesRegex(exp.ExportError,'review_inputs_changed'):self.publish()

    def test_row_time_json_and_media_budgets(self):
        for name,value in [('MAX_ROWS',2),('MAX_TOTAL_ROWS',4),('MAX_JSON',128),('MAX_MEDIA_TOTAL',1),('MAX_MEDIA_FILE',1)]:
            with self.subTest(name=name),patch.object(exp,name,value):
                with self.assertRaises(Exception):self.build()
        with patch.object(exp,'check_time',side_effect=exp.ExportError('time_budget')):
            with self.assertRaisesRegex(exp.ExportError,'time_budget'):self.build()

    def test_review_cannot_write_inside_candidate_or_replace_existing_file(self):
        before={p.relative_to(self.candidate).as_posix():p.read_bytes() for p in self.candidate.rglob('*') if p.is_file()}
        for target in (self.candidate/'review.json',self.candidate/'prepared'/'review.json'):
            with self.assertRaisesRegex(exp.ExportError,'unsafe_output'):
                exp.review(self.db,self.candidate,self.request,target)
        self.assertEqual(before,{p.relative_to(self.candidate).as_posix():p.read_bytes() for p in self.candidate.rglob('*') if p.is_file()})
        with self.assertRaisesRegex(exp.ExportError,'output_collision'):
            exp.review(self.db,self.candidate,self.request,self.request)

    def test_prepared_or_roster_mutation_after_review_rejected(self):
        self.seal();p=self.candidate/'prepared/video/102.mp4';raw=p.read_bytes();p.write_bytes(raw[:-1]+b'X')
        with self.assertRaisesRegex(exp.ExportError,'prepared_hash_mismatch'):self.publish()
        p.write_bytes(raw)
        self.mutate(lambda v:v['roster_review']['people'][0].update(label='Changed synthetic label'))
        with self.assertRaisesRegex(exp.ExportError,'review_inputs_changed'):self.publish()
        self.assertFalse((self.root/'output').exists())

    def test_failure_during_write_leaves_only_new_disabled_attempt(self):
        self.seal();real=exp.new_file
        def fail(path,raw):
            if path.name=='catalog.json':raise OSError('synthetic disk failure')
            return real(path,raw)
        with patch.object(exp,'new_file',side_effect=fail):
            with self.assertRaises(OSError):self.publish()
        self.assertFalse(json.loads((self.root/'output/control.json').read_text())['enabled'])
        self.assertTrue((self.candidate/'catalog.json').exists())

    def test_disabled_then_synthetic_enabled_asgi_replay(self):
        self.seal();receipt=self.publish();root=self.root/'output'
        config=Configuration(root/'control.json',root/'prepared','https://home.photohouse.test:18444',('192.168.40.0/24',))
        app=create_home_discovery(config,root/'discovery.json',receipt['output_hashes']['discovery.json'])
        with TestClient(app,base_url=config.origin,client=('192.168.40.20',1)) as client:
            for route in ('/home/v2/catalog','/home/discovery/v1/facets'):
                self.assertEqual(client.get(route).status_code,403)
            control=json.loads((root/'control.json').read_text());control['enabled']=True;(root/'control.json').write_bytes(exp.packed(control))
            facets=client.get('/home/discovery/v1/facets').json();self.assertEqual(facets['pinned_person_ids'],[202,201])
            result=client.post('/home/discovery/v1/search',json={'revision':7,'page':1,'page_size':50,'filters':{'people':{'ids':[201,202],'match':'all'},'caption':'family'}})
            self.assertEqual(result.status_code,200);self.assertEqual([a['id'] for a in result.json()['items']],[103])
            self.assertEqual(client.get('/home/v2/assets/101/preview?variant=display&revision=1').status_code,200)
            r=client.get('/home/v2/assets/102/video?revision=1',headers={'Range':'bytes=0-7'})
            self.assertEqual(r.status_code,206);self.assertEqual(r.content,(ROOT/'tests/security/fixtures/home-video.mp4').read_bytes()[:8])
            self.assertEqual(client.get('/assets/101/original').status_code,403)
            control['enabled']=False;(root/'control.json').write_bytes(exp.packed(control));self.assertEqual(client.get('/home/discovery/v1/facets').status_code,403)


if __name__=='__main__':unittest.main()
