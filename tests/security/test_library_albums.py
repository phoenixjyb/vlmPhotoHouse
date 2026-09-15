"""Synthetic migrated SQLite and actual protected HTTP album contracts."""
import unittest
import uuid
import test_library_reads as fixture
from app.access.transport import COOKIE, csrf_token


class AlbumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.LibraryReadTests.setUpClass()
    @classmethod
    def tearDownClass(cls): fixture.LibraryReadTests.tearDownClass()
    def setUp(self):
        self.f=fixture.LibraryReadTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.client=self.f.client;self.token=self.f.owner_token
    def headers(self,token=None): return {'Authorization':'Bearer '+(token or self.token)}
    def body(self,**changes):
        return {'title':'Our family','title_zh':'家人的时光','description':'A story','theme':'trip',
                'asset_ids':'101,102','cover_asset_id':'102','mutation_id':str(uuid.uuid4()),**changes}
    def create(self,body=None,token=None,library='family-a'):
        return self.client.post('/admin/albums?library='+library,headers=self.headers(token),json=body or self.body())
    def listing(self,token=None,library='family-a',page=1):
        return self.client.get(f'/library-albums?library={library}&page={page}',headers=self.headers(token))
    def update(self,album,**changes):
        body={key:album[key] for key in ('title','title_zh','description','theme','cover_asset_id','revision')}
        body['asset_ids']=','.join(album['asset_ids']);body.update(changes)
        return self.client.put('/admin/albums/'+album['id']+'?library=family-a',headers=self.headers(),json=body)

    def test_create_scoped_member_reads_and_no_legacy_album_import(self):
        self.f.mutate("INSERT INTO albums(title,theme,status) VALUES('Hidden old album','custom','draft')")
        response=self.create();self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['asset_ids'],['101','102'])
        data=self.listing(self.f.member_token).json();self.assertEqual(data['total'],1);self.assertFalse(data['can_manage'])
        self.assertNotIn('Hidden old album',str(data));self.assertNotIn('path',str(data))
        self.assertEqual(self.listing(self.f.other_token).status_code,401)
        self.assertEqual(self.listing(self.f.other_token,'family-b').json()['total'],0)
        self.assertEqual(self.create(token=self.f.member_token).status_code,401)
        self.assertEqual(self.create(library='family-b').status_code,401)
        self.assertEqual(self.client.get('/library-albums?library=family-a').status_code,401)

    def test_repeat_creation_is_not_duplicate_and_changed_mutation_rejected(self):
        body=self.body();first=self.create(body).json();second=self.create(body).json()
        self.assertEqual(first['id'],second['id']);self.assertEqual(self.listing().json()['total'],1)
        self.assertEqual(self.create({**body,'title':'Changed'}).status_code,409)

    def test_order_cover_title_and_empty_album_edit_preserve_media(self):
        first=self.create().json();response=self.update(first,asset_ids='102,101',cover_asset_id='101',title='Updated')
        self.assertEqual(response.status_code,200);updated=response.json()
        self.assertEqual(updated['asset_ids'],['102','101']);self.assertEqual(updated['cover_asset_id'],'101')
        self.assertEqual(self.update(first,title='Stale overwrite').status_code,409)
        empty=self.update(updated,asset_ids='',cover_asset_id='');self.assertEqual(empty.status_code,200)
        self.assertEqual(empty.json()['asset_ids'],[]);self.assertEqual(self.listing().json()['total'],1)
        with self.f.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM assets').fetchone()[0],5)
            self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0],0)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_foreign_deleted_unmapped_or_duplicate_assets_and_invalid_cover_refused(self):
        for ids in ('201','103','999','101,101','0','1.2',','.join(str(i) for i in range(1,62))):
            self.assertIn(self.create(self.body(asset_ids=ids,cover_asset_id='')).status_code,(400,401))
        self.assertEqual(self.create(self.body(cover_asset_id='201')).status_code,400)
        self.assertEqual(self.create(self.body(title='')).status_code,400)
        self.assertEqual(self.create(self.body(asset_ids=[101])).status_code,400)
        self.assertEqual(self.create(self.body(mutation_id='not-a-uuid')).status_code,400)
        self.assertEqual(self.listing().json()['total'],0)

    def test_moved_assets_not_disclosed_and_require_explicit_edit_review(self):
        album=self.create().json();self.f.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=102")
        current=self.listing().json()['items'][0]
        self.assertEqual(current['asset_ids'],['101']);self.assertEqual(current['cover_asset_id'],'101');self.assertTrue(current['needs_review'])
        self.assertEqual(self.update(album,title='Old selections').status_code,401)
        self.assertEqual(self.update(current,title='Reviewed').status_code,200)

    def test_audit_failure_rolls_back_update_and_creation(self):
        album=self.create().json();self.f.mutate("CREATE TRIGGER refuse_album BEFORE INSERT ON access_audit BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        self.assertEqual(self.update(album,title='Rollback').status_code,503)
        self.assertEqual(self.create().status_code,503)
        data=self.listing().json();self.assertEqual(data['total'],1);self.assertEqual(data['items'][0]['title'],album['title'])

    def test_oversized_unmanaged_album_metadata_fails_closed(self):
        album=self.create().json()
        self.f.mutate('UPDATE albums SET description=? WHERE id=?',('private-long-data'*10000,int(album['id'])))
        response=self.listing();self.assertEqual(response.status_code,503)
        self.assertNotIn('private-long-data',response.text)

    def test_paging_and_cookie_csrf(self):
        for i in range(12): self.assertEqual(self.create(self.body(title=str(i))).status_code,200)
        first=self.listing().json();second=self.listing(page=2).json()
        self.assertEqual((first['total'],len(first['items']),len(second['items'])),(12,10,2))
        self.assertEqual(len({a['id'] for a in first['items']+second['items']}),12)
        self.client.cookies.set(COOKIE,self.token);body=self.body()
        self.assertEqual(self.client.post('/admin/albums?library=family-a',json=body).status_code,403)
        self.assertEqual(self.client.post('/admin/albums?library=family-a',json=body,headers={'Origin':'https://photohouse.test','X-CSRF-Token':csrf_token(self.token)}).status_code,200)
