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

    def assignment_fixture(self):
        with self.f.connection() as db:
            db.execute("INSERT INTO persons(id,display_name,face_count,embedding_path) VALUES(7,'家人 Seven',1,'private-person-vector')")
            db.execute('''INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h)
                VALUES(71,102,7,0,0,1,1),(12,101,NULL,0,0,1,1)''')
            db.execute("UPDATE face_detections SET label_source='dnn',label_score=0.8 WHERE id=11")
            db.execute('''INSERT INTO person_embedding_artifacts(person_id,model,model_version,dim,storage_path,status)
                VALUES(1,'synthetic','test',2,'private-centroid','active'),(7,'synthetic','test',2,'private-target','shadow')''')
            db.commit()

    def test_new_person_unassign_and_orphan_selection_keep_owned_name(self):
        self.assignment_fixture();revision=self.assignment_body(face=12)['revision']
        path='/admin/faces/12/new-person?library=family-a';body={'display_name':'小朋友','revision':revision}
        created=self.client.post(path,headers={'Authorization':'Bearer '+self.owner},json=body)
        self.assertEqual(created.status_code,200);person=created.json()['person_id']
        self.assertEqual(self.client.post(path,headers={'Authorization':'Bearer '+self.owner},json=body).status_code,409)
        response=self.client.post('/admin/faces/12/unassign?library=family-a',headers={'Authorization':'Bearer '+self.owner},json={'revision':created.json()['revision']})
        self.assertEqual(response.status_code,200);self.assertIsNone(response.json()['person_id'])
        retained=self.person(int(person));self.assertEqual(retained['display_name'],'小朋友');self.assertEqual(retained['face_count'],0)
        self.assertEqual(self.assign(self.assignment_body(face=12,target=int(person)),face=12).status_code,200)
        self.assertEqual(self.get('/admin/people?library=family-b',self.f.other_token).json()['total'],2)

    def test_unassignment_retains_old_person_and_refuses_shared_and_stale(self):
        self.assignment_fixture();revision=self.assignment_body()['revision'];headers={'Authorization':'Bearer '+self.owner}
        path='/admin/faces/11/unassign?library=family-a'
        self.assertEqual(self.client.post(path,headers=headers,json={'revision':revision}).status_code,200)
        self.assertEqual(self.person()['face_count'],0)
        self.assertEqual(self.client.post(path,headers=headers,json={'revision':revision}).status_code,409)
        self.assertEqual(self.client.post('/admin/faces/41/unassign?library=family-a',headers=headers,json={'revision':revision}).status_code,401)

    def test_person_owned_elsewhere_is_not_disclosed_after_asset_moves(self):
        self.assignment_fixture()
        with self.f.connection() as db:
            owner=db.execute("SELECT bootstrap_operator FROM access_libraries WHERE id='family-b'").fetchone()[0]
            db.execute('INSERT INTO access_person_libraries VALUES(1,?,?,1)',('family-b',owner));db.commit()
        result=self.get('/admin/assets/101/faces?library=family-a').json()['items'][0]
        self.assertIsNone(result['person_id']);self.assertIsNone(result['display_name']);self.assertFalse(result['can_assign'])
        self.assertNotIn('Alice',self.get().text)

    def test_new_person_creation_rolls_back_when_face_jobs_active(self):
        self.assignment_fixture();revision=self.assignment_body(face=12)['revision']
        self.f.mutate("INSERT INTO tasks(type,state,priority,retry_count,payload_json) VALUES('face','running',1,0,'{}')")
        response=self.client.post('/admin/faces/12/new-person?library=family-a',headers={'Authorization':'Bearer '+self.owner},json={'revision':revision,'display_name':'Must not persist'})
        self.assertEqual(response.status_code,409)
        with self.f.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM persons WHERE display_name='Must not persist'").fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_person_libraries').fetchone()[0],0)

    def assignment_body(self, face=11, target=7):
        record=next(item for item in self.get('/admin/assets/101/faces?library=family-a').json()['items'] if item['id']==str(face))
        return {'person_id':str(target),'revision':record['revision'],'person_revision':self.person(target)['revision']}

    def assign(self, body, face=11, token=None, library='family-a'):
        return self.client.post(f'/admin/faces/{face}/assignment?library={library}',
            headers={'Authorization':'Bearer '+(token or self.owner)},json=body)

    def test_asset_face_review_scoped_and_paginated(self):
        self.assignment_fixture()
        result=self.get('/admin/assets/101/faces?library=family-a');self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['total'],2)
        self.assertIsNone(result.json()['items'][1]['person_id'])
        for forbidden in ('embedding','bbox','private-vector','label_score'):
            self.assertNotIn(forbidden,result.text)
        for asset in (103,201,999,777):
            self.assertEqual(self.get(f'/admin/assets/{asset}/faces?library=family-a').status_code,401)
        self.assertEqual(self.get('/admin/assets/101/faces?library=family-a',self.f.member_token).status_code,401)
        with self.f.connection() as db:
            for face in range(100,130):
                db.execute('INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h) VALUES(?,101,0,0,1,1)',(face,))
            db.commit()
        first=self.get('/admin/assets/101/faces?library=family-a').json()
        second=self.get('/admin/assets/101/faces?library=family-a&page=2').json()
        self.assertEqual((first['total'],len(first['items']),len(second['items'])),(32,25,7))
        self.assertEqual(len({item['id'] for item in first['items']+second['items']}),32)

    def test_assignment_atomic_history_counts_aggregate_invalidation_no_gpu_jobs(self):
        self.assignment_fixture();body=self.assignment_body()
        response=self.assign(body);self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['person_id'],'7')
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT person_id,label_source,label_score,embedding_path FROM face_detections WHERE id=11').fetchone(),(7,'manual',None,'private-vector'))
            self.assertEqual(db.execute('SELECT id,face_count,embedding_path FROM persons WHERE id IN (1,7) ORDER BY id').fetchall(),[(1,0,None),(7,2,None)])
            self.assertEqual(db.execute('SELECT status,storage_path FROM person_embedding_artifacts ORDER BY person_id').fetchall(),[('stale','private-centroid'),('stale','private-target')])
            event=db.execute('SELECT old_person_id,new_person_id,old_label_source,new_label_source,old_label_score,actor FROM face_assignment_events WHERE face_id=11').fetchone()
            self.assertEqual(event[:5],(1,7,'dnn','manual',0.8));self.assertTrue(event[5])
            self.assertEqual(db.execute("SELECT count(*) FROM access_audit WHERE action='face.assign.11'").fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0],0)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(self.assign(body).status_code,409)

    def test_unassigned_face_can_join_existing_scoped_person(self):
        self.assignment_fixture()
        self.assertEqual(self.assign(self.assignment_body(face=12),face=12).status_code,200)

    def test_assignment_requires_fresh_face_and_target_name(self):
        self.assignment_fixture();body=self.assignment_body()
        self.f.mutate("UPDATE persons SET display_name='changed',updated_at='later' WHERE id=7")
        self.assertEqual(self.assign(body).status_code,409)
        body=self.assignment_body();self.f.mutate("UPDATE face_detections SET bbox_x=0.3 WHERE id=11")
        self.assertEqual(self.assign(body).status_code,409)
        body=self.assignment_body();self.f.mutate("INSERT INTO face_assignment_events(face_id,source) VALUES(11,'manual')")
        self.assertEqual(self.assign(body).status_code,409)

    def test_assignment_source_target_scope_and_authorization_rechecked(self):
        self.assignment_fixture();body=self.assignment_body()
        for token in (self.f.member_token,self.f.other_token,'a'*43):
            self.assertEqual(self.assign(body,token=token).status_code,401)
        for target in (2,3,4,5,6,999):
            self.assertEqual(self.assign({**body,'person_id':str(target)}).status_code,401)
        for face in (21,31,41,61,999):
            self.assertEqual(self.assign(body,face=face).status_code,401)
        self.f.mutate('UPDATE face_detections SET person_id=7 WHERE id=31')
        self.assertEqual(self.assign(body).status_code,401)
        self.f.mutate('UPDATE face_detections SET person_id=3 WHERE id=31')
        self.f.mutate("UPDATE access_memberships SET role='viewer' WHERE library_id='family-a'")
        self.assertEqual(self.assign(body).status_code,401)

    def test_assignment_refuses_face_jobs_but_does_not_stop_caption_work(self):
        self.assignment_fixture();body=self.assignment_body()
        for kind in ('face','face_embed','person_cluster','person_recluster','person_label_propagate'):
            for state in ('pending','running'):
                self.f.mutate('INSERT INTO tasks(id,type,state,priority,retry_count,payload_json) VALUES(1,?,?,1,0,\'{}\')',(kind,state))
                self.assertEqual(self.assign(body).status_code,409)
                self.f.mutate('DELETE FROM tasks WHERE id=1')
        self.f.mutate("INSERT INTO tasks(id,type,state,priority,retry_count,payload_json) VALUES(1,'caption','running',1,0,'{}')")
        self.assertEqual(self.assign(body).status_code,200)
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT type,state FROM tasks').fetchall(),[('caption','running')])

    def test_assignment_audit_or_history_failure_rolls_back_every_change(self):
        self.assignment_fixture();body=self.assignment_body()
        for table in ('access_audit','face_assignment_events','person_embedding_artifacts'):
            operation='UPDATE' if table=='person_embedding_artifacts' else 'INSERT'
            self.f.mutate(f"CREATE TRIGGER refuse_assignment BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'synthetic'); END")
            self.assertEqual(self.assign(body).status_code,503)
            with self.f.connection() as db:
                self.assertEqual(db.execute('SELECT person_id FROM face_detections WHERE id=11').fetchone(),(1,))
                self.assertEqual(db.execute('SELECT count(*) FROM face_assignment_events').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT face_count,embedding_path FROM persons WHERE id=1').fetchone(),(999,'private-embedding-path'))
            self.f.mutate('DROP TRIGGER refuse_assignment')

    def test_assignment_cookie_csrf_and_strict_body(self):
        self.assignment_fixture();body=self.assignment_body()
        for change in ({'revision':'bad'},{'person_id':7},{'person_id':'0'},{'create_new':True},{'person_revision':None}):
            self.assertEqual(self.assign({**body,**change}).status_code,400)
        self.client.cookies.set(COOKIE,self.owner)
        path='/admin/faces/11/assignment?library=family-a'
        self.assertEqual(self.client.post(path,json=body).status_code,403)
        self.assertEqual(self.client.post(path,json=body,headers={'Origin':'https://photohouse.test','X-CSRF-Token':csrf_token(self.owner)}).status_code,200)


if __name__=='__main__': unittest.main()
