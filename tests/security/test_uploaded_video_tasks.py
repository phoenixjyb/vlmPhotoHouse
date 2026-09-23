import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import tempfile

os.environ.setdefault('DERIVED_PATH', tempfile.mkdtemp(prefix='photohouse-video-task-'))

from app import tasks
from app.gps_utils import VideoProbeError, _validate_video_probe


class _Query:
    def filter_by(self, **kwargs):
        return self

    def filter(self, *args):
        return self

    def first(self):
        return None


class _Session:
    def __init__(self, asset):
        self.asset = asset
        self.added = []
        self.commits = 0

    def get(self, model, asset_id):
        return self.asset if asset_id == self.asset.id else None

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def query(self, model):
        return _Query()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class UploadedVideoTaskTests(TestCase):
    def test_strict_probe_rejects_extra_stream_and_unbounded_layout(self):
        info = {
            'streams': [
                {'codec_type': 'video', 'width': 1920, 'height': 1080,
                 'disposition': {}, 'duration': '2', 'r_frame_rate': '30/1'},
                {'codec_type': 'video', 'width': 1920, 'height': 1080,
                 'disposition': {}, 'duration': '2', 'r_frame_rate': '30/1'},
            ],
            'format': {'format_name': 'mov,mp4,m4a,3gp,3g2,mj2'},
        }
        meta = {'duration_sec': 2.0, 'width': 1920, 'height': 1080, 'fps': 30.0,
                'format_name': info['format']['format_name']}
        with self.assertRaises(VideoProbeError):
            _validate_video_probe(Path('video.mp4'), meta, info)

    def test_strict_probe_allows_nonexecuted_metadata_stream(self):
        info = {
            'streams': [
                {'codec_type': 'video', 'width': 1920, 'height': 1080,
                 'disposition': {}, 'duration': '2', 'r_frame_rate': '30/1'},
                {'codec_type': 'audio'}, {'codec_type': 'data'},
            ],
            'format': {'format_name': 'mov,mp4,m4a,3gp,3g2,mj2'},
        }
        meta = {'duration_sec': 2.0, 'width': 1920, 'height': 1080, 'fps': 30.0,
                'format_name': info['format']['format_name']}
        _validate_video_probe(Path('video.mp4'), meta, info)

    def test_successful_probe_only_enqueues_keyframes(self):
        asset = SimpleNamespace(id=7, path='video.mp4', mime='video/mp4',
                                duration_sec=None, fps=None, width=None, height=None,
                                gps_lat=None, gps_lon=None)
        session = _Session(asset)
        executor = object.__new__(tasks.TaskExecutor)
        executor.session_factory = lambda: session
        executor.settings = SimpleNamespace()
        task = SimpleNamespace(payload_json={'asset_id': 7})
        metadata = {'duration_sec': 2.0, 'fps': 30.0, 'width': 1920,
                    'height': 1080, 'gps_lat': None, 'gps_lon': None}
        with patch.object(tasks, 'probe_video_metadata', return_value=metadata) as probe:
            executor._handle_video_probe(session, task)
        probe.assert_called_once_with('video.mp4', timeout_sec=10, strict=True)
        self.assertEqual([(item.type, item.payload_json) for item in session.added],
                         [('video_keyframes', {'asset_id': 7})])
        self.assertEqual((asset.duration_sec, asset.fps, asset.width, asset.height),
                         (2.0, 30.0, 1920, 1080))

    def test_keyframes_enqueue_embed_and_caption_but_never_face(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'source.mp4'
            source.write_bytes(b'fixture')
            asset = SimpleNamespace(id=8, path=str(source), mime='video/mp4')
            session = _Session(asset)
            executor = object.__new__(tasks.TaskExecutor)
            executor.session_factory = lambda: _Session(asset)
            executor.settings = SimpleNamespace(video_keyframe_interval_sec=2.0)
            task = SimpleNamespace(payload_json={'asset_id': 8})

            def fake_ffmpeg(args, *, timeout, output_dir):
                (Path(output_dir) / 'frame_00001.jpg').write_bytes(b'jpeg-fixture')

            with patch.object(tasks, 'probe_video_metadata', return_value={
                    'duration_sec': 2.0, 'fps': 30.0, 'width': 1920, 'height': 1080}), \
                    patch.object(tasks, '_run_bounded_media_process', side_effect=fake_ffmpeg):
                executor._handle_video_keyframes(session, task)
            self.assertEqual([item.type for item in session.added], ['video_embed', 'caption'])
            self.assertNotIn('face', [item.type for item in session.added])

    def test_embedding_without_usable_keyframe_fails_visibly(self):
        with tempfile.TemporaryDirectory() as root, patch.object(tasks, 'DERIVED_DIR', Path(root)):
            session = _Session(SimpleNamespace(id=9, path='video.mp4', mime='video/mp4'))
            executor = object.__new__(tasks.TaskExecutor)
            with self.assertRaisesRegex(ValueError, 'no usable keyframe'):
                executor._handle_video_embed(session, SimpleNamespace(payload_json={'asset_id': 9}))


if __name__ == '__main__':
    import unittest
    unittest.main()
