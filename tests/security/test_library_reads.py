"""Real closed application + fully migrated synthetic SQLite library reads."""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from sqlalchemy import create_engine
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.main import create_app
from app.access.library import LibraryReads
from app.access.service import AccessService
from app.access.transport import AccessRuntime, COOKIE
from app.access.bootstrap import bootstrap_owner
from test_orm_migrations import config
from test_access_foundation import OWNER, OTHER_OWNER, MEMBER, PASSWORD, NOW


class LibraryReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='photohouse-gallery-template-')
        path = Path(cls.directory.name) / 'synthetic.sqlite'
        engine = create_engine('sqlite:///' + str(path))
        with engine.begin() as connection:
            cfg = config(); cfg.attributes['connection'] = connection
            command.upgrade(cfg, 'head')
        engine.dispose()
        cls.template = sqlite3.connect(path)
        cls.template.execute('PRAGMA foreign_keys=ON')
        bootstrap_owner(cls.template, phone=OWNER, password=PASSWORD, library_id='family-a')
        bootstrap_owner(cls.template, phone=OTHER_OWNER, password=PASSWORD, library_id='family-b')
        service = AccessService(cls.template, clock=lambda: NOW)
        cls.owner_token = service.login(OWNER, PASSWORD)
        cls.other_token = service.login(OTHER_OWNER, PASSWORD)
        cls.member_token = service.register(MEMBER, PASSWORD, service.invite(cls.owner_token, 'family-a', MEMBER))
        cls.member_id = service.profile(cls.member_token)['account_id']
        for asset_id, library, status, date in [(101,'family-a','active','2026-01-01'),
                (102,'family-a',None,'2026-01-02'), (103,'family-a','deleted','2026-01-03'),
                (201,'family-b','active','2026-02-01'), (999,None,'active','2026-03-01')]:
            cls.template.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at,
                gps_lat,gps_lon,caption_error_last) VALUES (?,?,?,?,?,640,480,?,1,2,?)''',
                (asset_id, f'private-synthetic/{asset_id}.jpg', f'private-hash-{asset_id}',status,
                 'image/jpeg',date,'private-provider-error'))
            if library:
                cls.template.execute('INSERT INTO access_asset_libraries VALUES (?,?)', (asset_id,library))
            cls.template.execute('''INSERT INTO captions(id,asset_id,text,model,user_edited,superseded)
                VALUES (?,?,?,'private-model',0,0)''', (asset_id,asset_id,f'caption-{asset_id}'))
        cls.template.execute("INSERT INTO captions(id,asset_id,text,model,user_edited,superseded) VALUES (1001,101,'old-hidden','model',0,1)")
        cls.template.commit()

    @classmethod
    def tearDownClass(cls):
        cls.template.close(); cls.directory.cleanup()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='photohouse-gallery-')
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'synthetic.sqlite'
        with closing(sqlite3.connect(self.path)) as db:
            self.template.backup(db)
        self.now = NOW
        self.trace = []
        runtime = AccessRuntime(self.connection, 'https://photohouse.test', clock=lambda:self.now)
        self.client = TestClient(create_app(access_runtime=runtime), base_url='https://photohouse.test')
        self.addCleanup(self.client.close)
        for target in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system'):
            guard = patch(target,side_effect=AssertionError('External I/O forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path)
        db.execute('PRAGMA foreign_keys=ON')
        db.set_trace_callback(self.trace.append)
        try:
            yield db
        finally:
            db.close()

    def mutate(self, sql, args=()):
        with self.connection() as db:
            db.execute(sql,args); db.commit()

    def get(self, path, token=None):
        return self.client.get(path, headers={'Authorization':'Bearer ' + (token or self.member_token)})

    def test_gallery_scopes_count_before_pagination_and_returns_safe_contract(self):
        response = self.get('/assets?library=family-a&page_size=1')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['cache-control'],'no-store')
        result = response.json()
        self.assertEqual((result['total'],result['page'],result['page_size']),(2,1,1))
        self.assertFalse(result['originals_allowed'])
        self.assertEqual([r['id'] for r in result['items']],[102])
        self.assertEqual([r['id'] for r in self.get('/assets?library=family-a&page_size=1&page=2').json()['items']],[101])
        self.assertEqual(self.get('/assets?library=family-a&page=100').json()['items'],[])
        for forbidden in ('path','hash','gps','model','error','private-'):
            self.assertNotIn(forbidden,response.text)
        self.assertEqual(result['items'][0]['thumbnail_url'],'/assets/102/thumbnail?library=family-a')
        self.assertEqual(set(result['items'][0]),{'id','kind','width','height','duration_sec','taken_at','thumbnail_url'})

    def test_detail_and_current_captions_are_parent_scoped_and_redacted(self):
        detail = self.get('/assets/detail/101?library=family-a')
        self.assertEqual(detail.status_code,200)
        self.assertEqual(detail.json()['asset']['id'],101)
        captions = self.get('/assets/101/captions?library=family-a')
        self.assertEqual(captions.status_code,200)
        self.assertEqual([r['text'] for r in captions.json()['items']],['caption-101'])
        self.assertNotIn('model',captions.text)
        self.assertFalse(captions.json()['has_more'])

    def test_foreign_deleted_unmapped_missing_parent_denied_before_caption_query(self):
        for asset_id in (103,201,999,123456):
            for path in (f'/assets/detail/{asset_id}',f'/assets/{asset_id}/captions'):
                self.trace.clear()
                response = self.get(path+'?library=family-a')
                self.assertEqual(response.status_code,401)
                self.assertEqual(response.json(),{'detail':'Access denied'})
                self.assertFalse(any('FROM captions c' in sql for sql in self.trace))
        self.assertEqual(self.get('/assets/detail/101?library=family-b').status_code,401)
        self.assertEqual(self.get('/assets?library=family-b').status_code,401)
        self.assertEqual(self.get('/assets?library=family-b',self.other_token).json()['total'],1)

    def test_all_auth_failures_precede_asset_or_caption_queries(self):
        paths = ['/assets','/assets/detail/101','/assets/101/captions']
        mutations = [
            ("UPDATE access_memberships SET status='requested' WHERE account_id=?",(self.member_id,)),
            ("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(self.member_id,)),
            ('UPDATE access_memberships SET expires_at=? WHERE account_id=?',(NOW,self.member_id)),
            ("UPDATE access_accounts SET state='disabled' WHERE id=?",(self.member_id,)),
            ('UPDATE access_sessions SET revoked=1 WHERE account_id=?',(self.member_id,)),
            ('UPDATE access_sessions SET expires_at=? WHERE account_id=?',(NOW,self.member_id)),
            ("UPDATE access_libraries SET state='closed' WHERE id='family-a'",()),
        ]
        for sql,args in mutations:
            self.mutate(sql,args)
            for path in paths:
                self.trace.clear()
                self.assertEqual(self.get(path+'?library=family-a').status_code,401)
                self.assertFalse(any('FROM assets a' in s or 'FROM captions c' in s for s in self.trace))
            self.mutate("UPDATE access_memberships SET status='approved',expires_at=NULL WHERE account_id=?",(self.member_id,))
            self.mutate("UPDATE access_accounts SET state='active'")
            self.mutate('UPDATE access_sessions SET revoked=0,expires_at=?',(NOW+86400,))
            self.mutate("UPDATE access_libraries SET state='active'")
        for path in paths:
            self.trace.clear()
            self.assertEqual(self.client.get(path+'?library=family-a').status_code,401)
            self.assertEqual(self.get(path+'?library=family-a','a'*43).status_code,401)
            self.assertFalse(any('FROM assets a' in s for s in self.trace))

    def test_cookie_reads_and_next_request_revocation(self):
        self.client.cookies.set(COOKIE,self.member_token)
        self.assertEqual(self.client.get('/assets?library=family-a').status_code,200)
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(self.member_id,))
        self.assertEqual(self.client.get('/assets?library=family-a').status_code,401)

    def test_strict_query_validation_and_unreviewed_methods(self):
        for query in ('','library=family-a&token=secret','library=family-a&library=family-b',
                'library=family-a&page=0','library=family-a&page=-1','library=family-a&page_size=101',
                'library=family-a&page=100001','library=family-a&page=1.0','library=family-a&q=private',
                'library=family-a&size=256','library='+'a'*129,'library=family-a&page='+'9'*2000):
            self.assertEqual(self.get('/assets?'+query).status_code,400)
        for path in ('/assets/detail/0?library=family-a','/assets/9223372036854775808/captions?library=family-a'):
            self.assertEqual(self.get(path).status_code,400)
        for method in ('post','head','options'):
            self.assertEqual(getattr(self.client,method)('/assets?library=family-a').status_code,403)

    def test_caption_row_and_text_bounds_keep_html_as_plain_json(self):
        for i in range(30):
            self.mutate('INSERT INTO captions(asset_id,text,model,user_edited,superseded) VALUES (101,?,\'model\',1,0)',
                        ('<script>synthetic()</script>'+'x'*9000,))
        result = self.get('/assets/101/captions?library=family-a').json()
        self.assertTrue(result['has_more'])
        self.assertEqual(len(result['items']),20)
        self.assertTrue(all(len(r['text'])==8192 and r['truncated'] and r['user_edited'] for r in result['items']))

    def test_owner_role_does_not_imply_original_grant(self):
        self.assertFalse(self.get('/assets?library=family-a',self.owner_token).json()['originals_allowed'])
        self.mutate('UPDATE access_memberships SET originals=1 WHERE account_id=?',(self.member_id,))
        self.assertTrue(self.get('/assets/detail/101?library=family-a').json()['originals_allowed'])

    def test_policy_and_page_count_share_a_snapshot(self):
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            service = AccessService(db,clock=lambda:NOW)
            original = service._require
            def concurrent_revoke(*args,**kwargs):
                result = original(*args,**kwargs)
                self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(self.member_id,))
                return result
            with patch.object(service,'_require',side_effect=concurrent_revoke):
                self.assertEqual(LibraryReads(service).gallery(self.member_token,'family-a')['total'],2)
        self.assertEqual(self.get('/assets?library=family-a').status_code,401)


if __name__ == '__main__':
    unittest.main()
