import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'backend')]
from build_home_discovery_export_fixture import create
import export_home_search_metadata as export

class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=create(Path(self.tmp.name).resolve()/'fixture')
        self.db=self.root/'snapshot.sqlite';self.catalog=self.root/'candidate/catalog.json'
    def build(self):return export.build(self.db,self.catalog,9)
    def test_exact_catalog_binding_readonly_no_media_or_people_inference(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        raw,receipt=self.build();v=json.loads(raw)
        self.assertEqual(v['catalog_sha256'],hashlib.sha256(self.catalog.read_bytes()).hexdigest())
        self.assertEqual(v['people'],[]);self.assertEqual(v['locations'],[])
        rows={r['id']:r for r in v['assets']};self.assertEqual(set(rows),{101,102,103,104})
        self.assertEqual(rows[103]['caption_text'],'Ｆａｍｉｌｙ at park.')
        self.assertEqual(rows[103]['taken_day'],'2025-12-01')
        self.assertEqual([t['id'] for t in rows[101]['tags']],[302])
        self.assertFalse(receipt['media_copied']);self.assertFalse(receipt['activated'])
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
    def test_conflicts_are_excluded_and_unreviewed_people_remain_absent(self):
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO captions VALUES(5,101,'Other active caption',0,0)")
            c.execute("INSERT INTO asset_tags VALUES(6,101,302,'img')")
        raw,r=self.build();a=json.loads(raw)['assets'][0]
        self.assertIsNone(a['caption_text']);self.assertEqual(a['tags'],[])
        self.assertEqual(r['coverage']['caption_states']['ambiguous'],1)
    def test_hidden_scope_and_resource_budget_refuse(self):
        with patch.object(export,'MAX_ROWS',2):
            with self.assertRaisesRegex(ValueError,'row_budget'): self.build()
        with sqlite3.connect(self.db) as c:c.execute("UPDATE assets SET status='hidden' WHERE id=101")
        with self.assertRaisesRegex(ValueError,'hidden_selected'): self.build()
    def test_roster_overflow_disables_whole_tag_capability_without_truncation(self):
        with sqlite3.connect(self.db) as c:
            c.executemany('INSERT INTO tags VALUES(?,?,?)',[(i,'Synthetic '+str(i),'scene') for i in range(1000,6001)])
            c.executemany('INSERT INTO asset_tags VALUES(?,?,?,?)',[(i,101,i,'manual') for i in range(1000,6001)])
        raw,r=self.build();v=json.loads(raw)
        self.assertNotIn('tags',v['enabled_filters']);self.assertEqual(v['tags'],[])
        self.assertTrue(r['coverage']['tag_roster_overflow']);self.assertEqual(r['coverage']['unpublished_tag_count'],5003)
        self.assertTrue(all(not a['tags'] for a in v['assets']))
    def test_tag_lookup_exports_full_roster_above_legacy_limit(self):
        catalog=json.loads(self.catalog.read_text())
        template=catalog['assets'][0]
        with sqlite3.connect(self.db) as c:
            for aid in range(1000,1060):
                catalog['assets'].append(dict(template,id=aid))
                c.execute("INSERT INTO assets(id,status,taken_at) VALUES(?,?,?)",(aid,'active',None))
            c.executemany('INSERT INTO tags VALUES(?,?,?)',[(i,'Synthetic '+str(i),'scene') for i in range(1000,7000)])
            c.executemany('INSERT INTO asset_tags VALUES(?,?,?,?)',[(i,1000+(i-1000)//100,i,'manual') for i in range(1000,7000)])
        catalog['assets'].sort(key=lambda a:a['id'],reverse=True)
        self.catalog.write_text(json.dumps(catalog))
        raw,receipt=export.build(self.db,self.catalog,9,tag_lookup=True);value=json.loads(raw)
        self.assertEqual(value['version'],2);self.assertEqual(len(value['tags']),6002)
        self.assertEqual(value['tags'][-1]['id'],6999)
        self.assertEqual(receipt['policy'],'home-search-tags-2')
        self.assertTrue(receipt['coverage']['tags_enabled'])
        old,_=self.build();self.assertNotIn('tags',json.loads(old)['enabled_filters'])

    def test_view_refused(self):
        with sqlite3.connect(self.db) as c:
            c.execute('ALTER TABLE captions RENAME TO originals');c.execute('CREATE VIEW captions AS SELECT * FROM originals')
        with self.assertRaisesRegex(ValueError,'schema_not_table'):self.build()
if __name__=='__main__':unittest.main()
