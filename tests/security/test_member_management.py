"""Actual ASGI owner readback/revocation; fully migrated synthetic storage."""
import unittest

import test_library_reads as library_fixture
from app.access.transport import COOKIE, csrf_token
from test_access_foundation import MEMBER, NOW


class MemberManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library_fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        library_fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.fixture=library_fixture.LibraryReadTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.client=self.fixture.client
        self.owner=library_fixture.LibraryReadTests.owner_token
        self.member=library_fixture.LibraryReadTests.member_token
        self.member_id=library_fixture.LibraryReadTests.member_id
        self.other=library_fixture.LibraryReadTests.other_token

    def request(self,method,path,token=None,**kwargs):
        return self.client.request(method,path,headers={'Authorization':'Bearer '+(token or self.owner)},**kwargs)

    def rows(self):
        response=self.request('GET','/libraries/family-a/members')
        self.assertEqual(response.status_code,200)
        return response.json()['items']

    def member_row(self):
        return next(row for row in self.rows() if row['account_id']==self.member_id)

    def revoke(self,revision='1',token=None,library='family-a',target=None,**kwargs):
        return self.request('POST',f'/libraries/{library}/members/{target or self.member_id}/revoke',token,
                            json={'revision':revision},**kwargs)

    def test_owner_list_is_scoped_bounded_and_has_no_credentials(self):
        response=self.request('GET','/libraries/family-a/members?page_size=1')
        self.assertEqual(response.status_code,200)
        result=response.json()
        self.assertEqual(result['total'],2)
        self.assertEqual(len(result['items']),1)
        self.assertEqual(result['items'][0]['role'],'owner')
        self.assertEqual(self.member_row()['phone_login'],MEMBER)
        self.assertEqual(self.member_row()['revision'],'1')
        self.assertTrue(self.member_row()['available'])
        for forbidden in ('password','hash','digest','session','family-b','+12025550101'):
            self.assertNotIn(forbidden,response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')

    def test_viewer_other_library_and_anonymous_never_query_member_directory(self):
        for token in (self.member,self.other,'a'*43):
            self.fixture.trace.clear()
            self.assertEqual(self.request('GET','/libraries/family-a/members',token).status_code,401)
            self.assertFalse(any('a.phone_login,m.status' in sql for sql in self.fixture.trace))
        self.assertEqual(self.client.get('/libraries/family-a/members').status_code,401)
        self.assertEqual(self.request('GET','/libraries/family-b/members').status_code,401)

    def test_revoke_is_atomic_audited_and_denies_next_library_request(self):
        self.assertEqual(self.revoke().status_code,200)
        row=self.member_row()
        self.assertEqual((row['status'],row['revision'],row['available']),('revoked','2',False))
        self.assertEqual(self.request('GET','/assets?library=family-a',self.member).status_code,401)
        self.assertEqual(self.request('GET','/auth/session',self.member).status_code,200)
        with self.fixture.connection() as db:
            self.assertEqual(db.execute('SELECT originals FROM access_memberships WHERE account_id=?',(self.member_id,)).fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM access_audit WHERE action='membership.revoked' AND target_account=?",(self.member_id,)).fetchone()[0],1)

    def test_stale_confirmation_does_not_overwrite_newer_membership_or_audit(self):
        self.fixture.mutate('UPDATE access_memberships SET revision=2,originals=1 WHERE account_id=?',(self.member_id,))
        self.assertEqual(self.revoke('1').status_code,409)
        self.assertEqual(self.member_row()['status'],'approved')
        self.assertEqual(self.revoke('2').status_code,200)
        self.assertEqual(self.revoke('2').status_code,409)
        with self.fixture.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM access_audit WHERE action='membership.revoked'").fetchone()[0],1)

    def test_owner_self_and_foreign_account_targets_cannot_be_revoked(self):
        owner_id=next(row['account_id'] for row in self.rows() if row['role']=='owner')
        for token,library,target in [(self.owner,'family-a',owner_id),(self.owner,'family-b',self.member_id),
                                      (self.member,'family-a',self.member_id),(self.other,'family-a',self.member_id),
                                      (self.owner,'family-a','missing')]:
            self.assertEqual(self.revoke(token=token,library=library,target=target).status_code,401)
        self.assertEqual(self.member_row()['status'],'approved')

    def test_web_revoke_requires_origin_csrf_and_ignores_no_grant_fields(self):
        self.client.cookies.set(COOKIE,self.owner)
        path=f'/libraries/family-a/members/{self.member_id}/revoke'
        self.assertEqual(self.client.post(path,json={'revision':'1'}).status_code,403)
        headers={'Origin':'https://photohouse.test','X-CSRF-Token':csrf_token(self.owner)}
        self.assertEqual(self.client.post(path,headers=headers,json={'revision':'1','status':'approved'}).status_code,400)
        self.assertEqual(self.client.post(path,headers=headers,json={'revision':'1','originals':'true'}).status_code,400)
        self.assertEqual(self.client.post(path,headers=headers,json={'revision':'1'}).status_code,200)

    def test_disabled_owner_closed_library_and_expired_owner_membership_deny(self):
        owner_id=next(row['account_id'] for row in self.rows() if row['role']=='owner')
        cases=[("UPDATE access_accounts SET state='disabled' WHERE id=?",(owner_id,)),
               ("UPDATE access_libraries SET state='closed' WHERE id='family-a'",()),
               ('UPDATE access_memberships SET expires_at=? WHERE account_id=?',(NOW,owner_id))]
        for sql,args in cases:
            self.fixture.mutate(sql,args)
            self.assertEqual(self.request('GET','/libraries/family-a/members').status_code,401)
            self.assertEqual(self.revoke().status_code,401)
            self.fixture.mutate("UPDATE access_accounts SET state='active'")
            self.fixture.mutate("UPDATE access_libraries SET state='active'")
            self.fixture.mutate('UPDATE access_memberships SET expires_at=NULL')
        self.assertEqual(self.member_row()['status'],'approved')

    def test_strict_read_query_and_revision_contract(self):
        for query in ('page=0','page_size=101','page=1&page=2','token=private','page='+'9'*1100):
            self.assertEqual(self.request('GET','/libraries/family-a/members?'+query).status_code,400)
        for value in ('0','-1','1.0','99999999999999999999999999','true'):
            self.assertEqual(self.revoke(value).status_code,400)
        path=f'/libraries/family-a/members/{self.member_id}/revoke'
        self.assertEqual(self.request('POST',path,json={'revision':1}).status_code,400)
        self.assertEqual(self.request('POST',path+'?token=private',json={'revision':'1'}).status_code,400)
        for path in (f'/libraries/family-a/members/{self.member_id}/approve',f'/libraries/family-a/members/{self.member_id}/originals'):
            self.assertEqual(self.request('POST',path,json={}).status_code,403)


if __name__=='__main__':
    unittest.main()
