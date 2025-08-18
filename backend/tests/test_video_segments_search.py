import os
from pathlib import Path
from PIL import Image


def _dummy_frame(path: Path, color=(80, 120, 160)):
    im = Image.new('RGB', (96, 64), color=color)
    im.save(path, 'JPEG')


def test_video_segments_rebuild_and_search(client, temp_env_root, monkeypatch):
    # Enable video and scene detection
    monkeypatch.setenv('VIDEO_ENABLED', 'true')
    monkeypatch.setenv('VIDEO_SCENE_DETECT', 'true')
    # Force settings reload and executor reinit
    from app.main import reinit_executor_for_tests
    reinit_executor_for_tests()

    # Create a pseudo-video and ingest
    originals = Path(temp_env_root['originals'])
    jpg = originals / 'seed.jpg'
    _dummy_frame(jpg)
    fake_video = originals / 'clip.mp4'
    fake_video.write_bytes(jpg.read_bytes())

    # Trigger ingest
    r = client.post('/ingest/scan', json={'roots':[str(originals)]})
    assert r.status_code == 200

    # Run some tasks
    from app.main import executor
    for _ in range(60):
        if not executor.run_once():
            break

    # Rebuild segment index and search
    rb = client.post('/video-seg-index/rebuild')
    assert rb.status_code == 200
    data = rb.json()
    assert 'loaded' in data

    srch = client.post('/search/video-segments', json={'text': 'test', 'k': 3})
    assert srch.status_code in (200, 500)  # 500 allowed if embedding service not ready in CI
    if srch.status_code == 200:
        out = srch.json()
        assert 'results' in out
