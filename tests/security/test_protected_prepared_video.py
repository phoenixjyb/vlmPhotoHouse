"""Protected prepared-video playback: library access without original grants."""
import hashlib
import json
import asyncio
import threading
import unittest
from unittest.mock import patch

import test_closed_application as closed
from starlette.requests import Request
from app.access.media import AuthorizedMediaResponse, MediaRuntime
from app.access.prepared_video import PreparedVideos
from app.home_catalog import CHUNK_BYTES


class ProtectedPreparedVideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        closed.ClosedApplicationTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        closed.ClosedApplicationTests.tearDownClass()

    def setUp(self):
        self.e = closed.ClosedApplicationTests()
        self.e.setUp()
        self.addCleanup(self.e.doCleanups)
        self.e.mutate('UPDATE access_memberships SET originals=0 WHERE account_id=?',
                      (self.e.member_id,))

        self.prepared_root = self.e.root / 'prepared-videos'
        self.prepared_root.mkdir()
        self.index = self.e.root / 'prepared-index.json'
        folder = self.prepared_root / 'asset-101'
        folder.mkdir()
        # Two chunks exercise cross-boundary Range and per-chunk integrity checks.
        self.video = (b'A' * CHUNK_BYTES) + (b'B' * 257)
        (folder / 'video.mp4').write_bytes(self.video)
        hashes = [hashlib.sha256(self.video[:CHUNK_BYTES]).hexdigest(),
                  hashlib.sha256(self.video[CHUNK_BYTES:]).hexdigest()]
        chunks = json.dumps(hashes, separators=(',', ':')).encode()
        (folder / 'video.chunks.json').write_bytes(chunks)
        source = self.e.originals / '101.mp4'
        info = source.stat()
        metadata = {
            'state': 'ready', 'mime': 'video/mp4', 'video_codec': 'h264',
            'audio_codec': None, 'width': 320, 'height': 180,
            'duration_ms': 1000, 'bytes': len(self.video),
            'sha256': hashlib.sha256(self.video).hexdigest(),
            'chunks_sha256': hashlib.sha256(chunks).hexdigest(),
        }
        value = {'version': 1, 'assets': [{
            'id': 101,
            'source_identity': [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns],
            'directory': 'asset-101', 'video': metadata,
        }]}
        raw = json.dumps(value, separators=(',', ':')).encode()
        self.index.write_bytes(raw)
        provider = PreparedVideos(self.index, hashlib.sha256(raw).hexdigest(), self.prepared_root)
        self.e.app.state.media_runtime = MediaRuntime(
            (self.e.originals,), self.e.derived, prepared_videos=provider)
        self.provider = provider

    def test_viewer_can_play_prepared_video_without_original_grant(self):
        url = '/assets/101/playback?library=family-a'
        response = self.e.client.get(url, headers=self.e.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.video)
        self.assertEqual(response.headers['etag'], '"' + hashlib.sha256(self.video).hexdigest() + '"')
        self.e.assert_private(response)
        self.assertEqual(self.e.client.get('/assets/101/media?library=family-a',
                                            headers=self.e.headers()).status_code, 401)

    def test_head_ranges_and_if_range_are_strongly_validated(self):
        url = '/assets/101/playback?library=family-a'
        full = self.e.client.get(url, headers=self.e.headers())
        etag = full.headers['etag']
        head = self.e.client.head(url, headers=self.e.headers())
        self.assertEqual((head.status_code, head.content), (200, b''))
        self.assertEqual(head.headers['content-length'], str(len(self.video)))
        requested = f'bytes={CHUNK_BYTES - 4}-{CHUNK_BYTES + 3}'
        ranged = self.e.client.get(url, headers=self.e.headers(Range=requested))
        self.assertEqual(ranged.status_code, 206)
        self.assertEqual(ranged.content, self.video[CHUNK_BYTES - 4:CHUNK_BYTES + 4])
        self.assertEqual(ranged.headers['content-range'],
                         f'bytes {CHUNK_BYTES - 4}-{CHUNK_BYTES + 3}/{len(self.video)}')
        exact = self.e.client.get(url, headers=self.e.headers(Range='bytes=0-3', **{'If-Range': etag}))
        self.assertEqual((exact.status_code, exact.content), (206, self.video[:4]))
        stale = self.e.client.get(url, headers=self.e.headers(Range='bytes=0-3', **{'If-Range': '"stale"'}))
        self.assertEqual((stale.status_code, stale.content), (200, self.video))
        self.assertEqual(self.e.client.get(url, headers=self.e.headers(Range='bytes=0-1,3-4')).status_code, 400)
        self.assertEqual(self.e.client.get(url, headers=self.e.headers(Range='bytes=99999999-')).status_code, 416)

    def test_unauthorized_lookup_does_not_open_provider(self):
        with patch.object(self.provider, 'open', side_effect=AssertionError('provider lookup before auth')):
            self.assertEqual(self.e.client.get('/assets/101/playback?library=family-a').status_code, 401)
            self.assertEqual(self.e.client.get('/assets/201/playback?library=family-a',headers=self.e.headers()).status_code,401)
            self.assertEqual(self.e.client.get('/assets/999/playback?library=family-a',headers=self.e.headers()).status_code,401)
            self.e.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                          (self.e.member_id,))
            self.assertEqual(self.e.client.get('/assets/101/playback?library=family-a',
                                               headers=self.e.headers()).status_code, 401)

    def test_provider_unavailable_unprepared_and_source_changed_fail_closed(self):
        url = '/assets/101/playback?library=family-a'
        self.e.app.state.media_runtime = MediaRuntime((self.e.originals,), self.e.derived)
        self.assertEqual(self.e.client.get(url, headers=self.e.headers()).status_code, 503)
        self.e.app.state.media_runtime = MediaRuntime(
            (self.e.originals,), self.e.derived, prepared_videos=self.provider)
        saved = self.provider.entries
        self.provider.entries = {}
        try:
            self.assertEqual(self.e.client.get(url, headers=self.e.headers()).status_code, 404)
        finally:
            self.provider.entries = saved
        source = self.e.originals / '101.mp4'
        source.write_bytes(source.read_bytes() + b'changed')
        self.assertEqual(self.e.client.get(url, headers=self.e.headers()).status_code, 409)

    def test_prepared_corruption_and_symlink_are_rejected(self):
        folder = self.prepared_root / 'asset-101'
        output = folder / 'video.mp4'
        output.write_bytes(b'corrupt')
        self.assertEqual(self.e.client.get('/assets/101/playback?library=family-a',
                                            headers=self.e.headers()).status_code, 409)
        output.unlink()
        outside = self.e.root / 'outside.mp4'
        outside.write_bytes(self.video)
        try:
            output.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest('symlinks unavailable')
        response = self.e.client.get('/assets/101/playback?library=family-a',
                                     headers=self.e.headers())
        self.assertIn(response.status_code, (404, 503))

    def test_same_size_corrupt_chunk_and_replaced_index_fail_closed(self):
        output = self.prepared_root/'asset-101/video.mp4'
        raw = bytearray(self.video); raw[0] ^= 1; output.write_bytes(raw)
        response = self.e.client.get('/assets/101/playback?library=family-a',headers=self.e.headers())
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.provider.slots._value,4)
        output.write_bytes(self.video)
        self.index.write_bytes(self.index.read_bytes()+b' ')
        self.assertEqual(self.e.client.get('/assets/101/playback?library=family-a',headers=self.e.headers()).status_code,409)
        self.assertEqual(self.provider.slots._value,4)

    def test_four_reader_limit_reports_retry_and_recovers(self):
        from app.home_catalog import identity
        readers = [self.provider.open(101,identity(self.e.originals/'101.mp4')) for _ in range(4)]
        try:
            response = self.e.client.get('/assets/101/playback?library=family-a',headers=self.e.headers())
            self.assertEqual(response.status_code,429)
            self.assertEqual(response.headers['retry-after'],'2')
        finally:
            for reader in readers: reader.close()
        self.assertEqual(self.e.client.head('/assets/101/playback?library=family-a',headers=self.e.headers()).status_code,200)
        self.assertEqual(self.provider.slots._value,4)

    def test_revocation_between_range_requests_denies_retry(self):
        url = '/assets/101/playback?library=family-a'
        first = self.e.client.get(url, headers=self.e.headers(Range='bytes=0-7'))
        self.assertEqual(first.status_code, 206)
        self.e.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                      (self.e.member_id,))
        with patch.object(self.provider, 'open', side_effect=AssertionError('revoked provider lookup')):
            response = self.e.client.get(url, headers=self.e.headers(Range='bytes=8-15'))
        self.assertEqual(response.status_code, 401)

    def test_revocation_during_multichunk_stream_stops_after_first_chunk(self):
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
                 'http_version': '1.1', 'method': 'GET', 'scheme': 'https',
                 'path': '/assets/101/playback', 'raw_path': b'/assets/101/playback',
                 'query_string': b'library=family-a', 'headers': [
                     (b'host', b'photohouse.test'),
                     (b'authorization', ('Bearer ' + self.e.member_token).encode()),
                 ], 'client': ('192.0.2.10', 23456), 'server': ('photohouse.test', 443),
                 'root_path': '', 'app': self.e.app}
        messages = []
        revoked = False

        async def send(message):
            nonlocal revoked
            messages.append(message)
            if message['type'] == 'http.response.body' and message.get('body') and not revoked:
                revoked = True
                self.e.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                              (self.e.member_id,))

        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        with self.assertRaises(Exception):
            asyncio.run(self.e.app(scope, receive, send))
        bodies = [m.get('body', b'') for m in messages if m['type'] == 'http.response.body' and m.get('body')]
        self.assertEqual(sum(m['type'] == 'http.response.start' for m in messages),1)
        self.assertEqual(len(bodies), 1)
        self.assertEqual(bodies[0], self.video[:CHUNK_BYTES])
        self.assertEqual(self.provider.slots._value, 4)

    def test_cancellation_during_provider_open_closes_late_reader(self):
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
                 'http_version': '1.1', 'method': 'GET', 'scheme': 'https',
                 'path': '/assets/101/playback', 'raw_path': b'/assets/101/playback',
                 'query_string': b'library=family-a', 'headers': [
                     (b'host', b'photohouse.test'),
                     (b'authorization', ('Bearer ' + self.e.member_token).encode()),
                 ], 'client': ('192.0.2.10', 23456), 'server': ('photohouse.test', 443),
                 'root_path': '', 'app': self.e.app}
        request = Request(scope)
        started, release, returned = threading.Event(), threading.Event(), threading.Event()
        actual = self.provider.open
        readers = []

        def paused(aid, source_pin):
            reader = actual(aid, source_pin)
            readers.append(reader)
            started.set()
            release.wait(3)
            returned.set()
            return reader

        async def send(message):
            raise AssertionError('Cancelled request must not send data')

        async def receive():
            return {'type': 'http.disconnect'}

        response = AuthorizedMediaResponse(request, self.e.member_token, 'family-a',
                                           101, 'playback', 256, False)

        async def run():
            task = asyncio.create_task(response(scope, receive, send))
            try:
                for _ in range(200):
                    if started.is_set():
                        break
                    await asyncio.sleep(.005)
                self.assertTrue(started.is_set())
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
            for _ in range(200):
                if returned.is_set():
                    break
                await asyncio.sleep(.005)
            self.assertTrue(returned.is_set())
            await asyncio.sleep(.05)
            self.assertTrue(readers and readers[0].closed)
            self.assertEqual(self.provider.slots._value, 4)

        try:
            with patch.object(self.provider, 'open', side_effect=paused):
                asyncio.run(run())
        finally:
            release.set()
            for reader in readers:
                reader.close()
        self.assertEqual(self.provider.slots._value, 4)

    def test_later_chunk_corruption_aborts_without_second_body(self):
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
                 'http_version': '1.1', 'method': 'GET', 'scheme': 'https',
                 'path': '/assets/101/playback', 'raw_path': b'/assets/101/playback',
                 'query_string': b'library=family-a', 'headers': [
                     (b'host', b'photohouse.test'),
                     (b'authorization', ('Bearer ' + self.e.member_token).encode()),
                 ], 'client': ('192.0.2.10', 23456), 'server': ('photohouse.test', 443),
                 'root_path': '', 'app': self.e.app}
        messages = []
        corrupted = False
        second = self.prepared_root / 'asset-101' / 'video.mp4'

        async def send(message):
            nonlocal corrupted
            messages.append(message)
            if message['type'] == 'http.response.body' and message.get('body') and not corrupted:
                corrupted = True
                with second.open('r+b') as stream:
                    stream.seek(CHUNK_BYTES)
                    stream.write(b'C' * 257)

        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        with self.assertRaises(Exception):
            asyncio.run(self.e.app(scope, receive, send))
        bodies = [m.get('body', b'') for m in messages if m['type'] == 'http.response.body' and m.get('body')]
        self.assertEqual(len(bodies), 1)
        self.assertEqual(bodies[0], self.video[:CHUNK_BYTES])
        self.assertEqual(self.provider.slots._value, 4)


if __name__ == '__main__':
    unittest.main()
