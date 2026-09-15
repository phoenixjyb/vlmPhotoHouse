"""Owner people management against migrated synthetic SQLite and real ASGI routes."""
import unittest
import test_library_reads as fixture
from app.access.transport import COOKIE, csrf_token
from test_access_foundation import NOW


class PeopleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls): fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.f=fixture.LibraryReadTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.client=self.f.client;self.owner=self.f.owner_token
        with self.f.connection() as db:
            for person,name in [(1,'Alice'),(2,'Foreign'),(3,'Unmapped'),(4,'Shared'),(5,'Orphan'),(6,'Deleted')]:
                db.execute('INSERT INTO persons(id,display_name,face_count,embedding_path) VALUES(?,?,999,?)',
                           (person,name,'private-embedding-path'))
            for face,asset,person in [(11,101,1),(21,201,2),(31,999,3),(41,102,4),(42,201,4),(61,103,6)]:
                db.execute('''INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h,embedding_path)
                    VALUES(?,?,?,0,0,1,1,'private-vector')''',(face,asset,person))
            db.commit()

    def get(self,path='/admin/people?library=family-a',token=None):
        return self.client.get(path,headers={'Authorization':'Bearer '+(token or self.owner)})

    def person(self,person=1):
        return next(p for p in self.get().json()['items'] if p['id']==str(person))

    def rename(self,name='Alicia',revision=None,person=1,token=None,library='family-a',**extra):
        return self.client.put(f'/admin/people/{person}?library={library}',
            headers={'Authorization':'Bearer '+(token or self.owner)},
            json={'display_name':name,'revision':revision or self.person()['revision'],**extra})

    def test_owner_directory_scopes_names_counts_and_hides_biometrics(self):
        response=self.get();self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['total'],2)
        self.assertEqual([(p['id'],p['face_count']) for p in response.json()['items']],[('1',1),('4',1)])
        self.assertTrue(self.person()['can_rename']);self.assertFalse(self.person(4)['can_rename'])
        for word in ('Foreign','Unmapped','Orphan','Deleted','embedding','private-','bbox'):
            self.assertNotIn(word,response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')

    def test_search_is_literal_and_supports_chinese(self):
        self.rename('家人 Alice')
        self.assertEqual(self.get('/admin/people?library=family-a&q=家人').json()['total'],1)
        for value in ('%','_','does-not-exist'):
            self.assertEqual(self.get('/admin/people?library=family-a&q='+value).json()['total'],0)

    def test_pagination_has_stable_complete_results(self):
        with self.f.connection() as db:
            for i in range(100,130):
                db.execute('INSERT INTO persons(id,display_name,face_count) VALUES(?,?,1)',(i,'Person '+str(i)))
                db.execute('INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h) VALUES(?,101,?,0,0,1,1)',(i,i))
            db.commit()
        first=self.get().json();second=self.get('/admin/people?library=family-a&page=2').json()
        self.assertEqual((first['total'],len(first['items']),len(second['items'])),(32,25,7))
        self.assertEqual(len({p['id'] for p in first['items']+second['items']}),32)

    def test_viewers_contributors_foreign_and_anonymous_denied_before_people_queries(self):
        for token in (self.f.member_token,self.f.other_token,'a'*43):
            self.f.trace.clear()
            self.assertEqual(self.get(token=token).status_code,401)
            self.assertFalse(any('FROM persons p' in sql for sql in self.f.trace))
            self.assertEqual(self.rename(token=token,revision='a'*64).status_code,401)
        self.f.mutate("UPDATE access_memberships SET role='contributor' WHERE account_id=?",(self.f.member_id,))
        self.assertEqual(self.get(token=self.f.member_token).status_code,401)
        self.assertEqual(self.client.get('/admin/people?library=family-a').status_code,401)
        self.assertEqual(self.get('/admin/people?library=family-b').status_code,401)

    def test_faces_are_scoped_bounded_and_return_only_protected_urls(self):
        r=self.get('/admin/people/4/faces?library=family-a');self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['total'],1)
        self.assertEqual(r.json()['items'],[{'id':'41','asset_id':'102','crop_url':'/faces/41/crop?library=family-a'}])
        for person in (2,3,5,6,999):
            self.assertEqual(self.get(f'/admin/people/{person}/faces?library=family-a').status_code,401)

    def test_rename_is_audited_and_does_not_change_faces_or_queue(self):
        old=self.person();r=self.rename();self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['display_name'],'Alicia');self.assertNotEqual(r.json()['revision'],old['revision'])
        with self.f.connection() as db:
            self.assertEqual(db.execute('select face_count,embedding_path from persons where id=1').fetchone(),(999,'private-embedding-path'))
            self.assertEqual(db.execute('select person_id from face_detections where id=11').fetchone(),(1,))
            self.assertEqual(db.execute("select count(*) from access_audit where action='person.rename.1'").fetchone()[0],1)
            self.assertEqual(db.execute('select count(*) from tasks').fetchone()[0],0)
            self.assertEqual(db.execute('pragma foreign_key_check').fetchall(),[])

    def test_stale_revision_aba_and_duplicate_save_refused(self):
        first=self.person()['revision']
        self.assertEqual(self.rename(revision=first).status_code,200)
        self.assertEqual(self.rename('Alice').status_code,200)
        self.assertEqual(self.rename('Overwrite',revision=first).status_code,409)
        self.assertEqual(self.person()['display_name'],'Alice')

    def test_shared_or_newly_out_of_scope_person_cannot_be_renamed(self):
        shared=self.person(4)
        self.assertEqual(self.rename(person=4,revision=shared['revision']).status_code,401)
        revision=self.person()['revision']
        self.f.mutate('UPDATE face_detections SET person_id=1 WHERE id=31')
        self.assertEqual(self.rename(revision=revision).status_code,401)

    def test_unmapped_foreign_deleted_missing_ids_cannot_be_renamed(self):
        for person in (2,3,5,6,999):
            self.assertEqual(self.rename(person=person,revision='a'*64).status_code,401)

    def test_authorization_rechecked_after_directory_read(self):
        revision=self.person()['revision']
        self.f.mutate("UPDATE access_libraries SET state='closed' WHERE id='family-a'")
        self.assertEqual(self.rename(revision=revision).status_code,401)

    def test_audit_failure_rolls_back_name(self):
        revision=self.person()['revision']
        self.f.mutate("CREATE TRIGGER synthetic_audit_failure BEFORE INSERT ON access_audit BEGIN SELECT RAISE(ABORT,'test'); END")
        response=self.rename(revision=revision)
        self.assertEqual(response.status_code,503)
        self.assertEqual(self.person()['display_name'],'Alice')

    def test_cookie_write_needs_origin_and_csrf(self):
        revision=self.person()['revision']
        self.client.cookies.set(COOKIE,self.owner)
        path='/admin/people/1?library=family-a';body={'display_name':'New name','revision':revision}
        self.assertEqual(self.client.put(path,json=body).status_code,403)
        headers={'Origin':'https://photohouse.test','X-CSRF-Token':csrf_token(self.owner)}
        self.assertEqual(self.client.put(path,json=body,headers=headers).status_code,200)

    def test_strict_inputs_and_unreviewed_mutations_remain_closed(self):
        for q in ('page=0','page=1&page=2','token=secret','q='+'x'*129):
            self.assertEqual(self.get('/admin/people?library=family-a&'+q).status_code,400)
        for name in ('',' ',' padded','x'*129,'bad\nname'):
            self.assertEqual(self.rename(name).status_code,400)
        self.assertEqual(self.rename(person_id='2').status_code,400)
        for method,path in [('POST','/admin/people'),('DELETE','/admin/people/1'),('PUT','/admin/faces/11')]:
            self.assertEqual(self.client.request(method,path,json={}).status_code,403)


if __name__=='__main__': unittest.main()
