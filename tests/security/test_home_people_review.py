import hashlib,json,sqlite3,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts'),str(ROOT/'tests/security')]
import test_home_search_metadata as base
from prepare_home_people_review import build as propose
from export_home_search_metadata import build

class PeopleReviewTests(unittest.TestCase):
    def setUp(self):
        self.f=base.MetadataTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        with sqlite3.connect(self.f.db) as c:
            c.execute('ALTER TABLE persons ADD COLUMN display_name TEXT');c.execute("UPDATE persons SET display_name='sample-'||id")
        self.roster=self.f.root/'roster.json';self.review=self.f.root/'review-people.json';self.approval=self.f.root/'approval-people.json'
        self.roster.write_text(json.dumps(dict(people=[dict(id=201,stored_name='sample-201',label='Sample Adult / 示例成人',aliases=['Example']),dict(id=202,stored_name='sample-202',label='Sample Child / 示例儿童',aliases=[])],pinned_person_ids=[202,201])))
        self.review.write_bytes(propose(self.f.db,self.f.catalog,self.roster))
        self.approval.write_text(json.dumps(dict(version=1,review_sha256=hashlib.sha256(self.review.read_bytes()).hexdigest(),approve_roster=True,approve_assignments=True)))
    def export(self):return build(self.f.db,self.f.catalog,10,tag_lookup=True,people_review=self.review,people_approval=self.approval)
    def test_explicit_review_exports_only_matching_manual_faces_and_ordered_shortcuts(self):
        raw,r=self.export();v=json.loads(raw)
        self.assertEqual(v['pinned_person_ids'],[202,201]);self.assertTrue(r['coverage']['people_enabled'])
        rows={a['id']:a for a in v['assets']};self.assertEqual(rows[103]['person_ids'],[201,202]);self.assertEqual(rows[104]['person_ids'],[])
        self.assertEqual(rows[103]['people_provenance'],'reviewed_assignments')
    def test_proposal_alone_or_changed_approval_is_not_authority(self):
        with self.assertRaises(ValueError):build(self.f.db,self.f.catalog,10,people_review=self.review)
        a=json.loads(self.approval.read_text());a['approve_assignments']=False;self.approval.write_text(json.dumps(a))
        with self.assertRaisesRegex(ValueError,'approval'):self.export()
    def test_changed_manual_assignment_or_name_is_refused(self):
        with sqlite3.connect(self.f.db) as c:c.execute("UPDATE face_detections SET label_source='dnn' WHERE id=1")
        with self.assertRaisesRegex(ValueError,'assignment_changed'):self.export()
        with sqlite3.connect(self.f.db) as c:c.execute("UPDATE persons SET display_name='renamed' WHERE id=201")
        with self.assertRaisesRegex(ValueError,'person_name_changed'):self.export()
    def test_catalog_drift_does_not_reuse_old_review(self):
        cat=json.loads(self.f.catalog.read_text());cat['revision']+=1;self.f.catalog.write_text(json.dumps(cat))
        with self.assertRaisesRegex(ValueError,'catalog_changed'):self.export()
