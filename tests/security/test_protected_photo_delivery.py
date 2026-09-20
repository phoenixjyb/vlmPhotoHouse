"""Protected on-demand reads retain membership checks without granting originals."""
from pathlib import Path
import sqlite3
import subprocess
import io
REAL_POPEN = subprocess.Popen
import unittest
from unittest.mock import patch
import test_closed_application as closed
ROOT=closed.ROOT
from app.access.media import MediaRuntime
from app.photo_delivery import PhotoCache


class ProtectedPhotoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): closed.ClosedApplicationTests.setUpClass()
    @classmethod
    def tearDownClass(cls): closed.ClosedApplicationTests.tearDownClass()
    def setUp(self):
        self.e=closed.ClosedApplicationTests();self.e.setUp();self.addCleanup(self.e.doCleanups)
        self.jpeg=(ROOT/'tests/security/fixtures/home-8x8.jpg').read_bytes()
        self.photo=self.e.originals/'101.jpg';self.photo.write_bytes(self.jpeg)
        with self.e.connection() as c:
            c.execute('UPDATE assets SET path=? WHERE id=101',(str(self.photo),))
            c.execute('UPDATE access_memberships SET originals=0 WHERE account_id=?',(self.e.member_id,));c.commit()
        self.cache=PhotoCache(self.e.root/'lazy-cache')
        self.e.app.state.media_runtime=MediaRuntime((self.e.originals,),self.e.derived,self.cache)
    def test_display_works_for_viewer_without_original_grant(self):
        with patch.object(PhotoCache,'render_opened',return_value=self.jpeg) as render:
            response=self.e.client.get('/assets/101/display?library=family-a',headers=self.e.headers())
            self.assertEqual(response.status_code,200,response.text[:100]);self.assertEqual(response.content,self.jpeg)
            self.assertEqual(render.call_count,1)
        self.assertEqual(self.e.client.get('/assets/101/media?library=family-a',headers=self.e.headers()).status_code,401)
        self.assertEqual(response.headers['cache-control'],'no-store')
    def test_anonymous_foreign_and_revoked_cannot_trigger_decoder(self):
        with patch.object(PhotoCache,'render_opened',side_effect=AssertionError('Unauthorized decode')):
            self.assertEqual(self.e.client.get('/assets/101/display?library=family-a').status_code,401)
            self.assertEqual(self.e.client.get('/assets/201/display?library=family-a',headers=self.e.headers()).status_code,401)
            with self.e.connection() as c:
                c.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(self.e.member_id,));c.commit()
            self.assertEqual(self.e.client.get('/assets/101/display?library=family-a',headers=self.e.headers()).status_code,401)
    def test_revocation_while_rendering_discards_generated_bytes(self):
        def render(*args,**kwargs):
            with self.e.connection() as c:
                c.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(self.e.member_id,));c.commit()
            return self.jpeg
        with patch.object(PhotoCache,'render_opened',side_effect=render):
            response=self.e.client.get('/assets/101/display?library=family-a',headers=self.e.headers())
        self.assertEqual(response.status_code,401);self.assertNotIn(self.jpeg,response.content)
    def test_thumbnail_missing_generates_grid_without_original_fallback(self):
        (self.e.derived/'thumbnails/256/101.jpg').unlink()
        with patch.object(PhotoCache,'render_opened',return_value=self.jpeg) as render:
            response=self.e.client.get('/assets/101/thumbnail?library=family-a',headers=self.e.headers())
        self.assertEqual(response.status_code,200);self.assertEqual(render.call_args.args[-1],'grid')
    def test_real_worker_normalizes_oriented_photo_and_reuses_display_cache(self):
        from PIL import Image
        image = Image.new('RGB',(1600,900),(90,120,70))
        exif = Image.Exif(); exif[274] = 6; exif[270] = 'Synthetic private description'
        image.save(self.photo,'JPEG',exif=exif)
        # This Mac may be below the production 4 GiB available-RAM floor. Keep
        # real worker/disk/deadline/RSS checks, but control available RAM for this
        # synthetic codec test; it is not Windows resource qualification.
        import sys
        sys.path.insert(0,str(ROOT/'scripts'))
        from home_preparation_resources import Guard, memory
        self.cache.guard_factory = lambda root: Guard(root,2*1024**3,
            observe=lambda process: (8*1024**3,memory(process)[1]))
        # Only restore this owned subprocess path. Network guards stay installed.
        with patch('subprocess.Popen',REAL_POPEN):
            response = self.e.client.get('/assets/101/display?library=family-a',headers=self.e.headers())
        self.assertEqual(response.status_code,200,response.text[:100] if response.status_code!=200 else '')
        with Image.open(io.BytesIO(response.content)) as decoded:
            self.assertEqual(decoded.size,(900,1600))
            self.assertEqual(dict(decoded.getexif()),{})
        self.assertNotIn(b'Synthetic private description',response.content)
        # The fixture's Popen guard forbids any worker on the cache hit.
        repeated = self.e.client.get('/assets/101/display?library=family-a',headers=self.e.headers())
        self.assertEqual(repeated.content,response.content)
        self.assertEqual(repeated.status_code,200)
        self.assertEqual(self.e.client.get('/assets/101/media?library=family-a',headers=self.e.headers()).status_code,401)

    def test_default_runtime_does_not_start_decoder(self):
        self.e.app.state.media_runtime=self.e.media
        with patch.object(PhotoCache,'render_opened',side_effect=AssertionError('Default must stay closed')):
            self.assertEqual(self.e.client.get('/assets/101/display?library=family-a',headers=self.e.headers()).status_code,503)

if __name__=='__main__':unittest.main()
