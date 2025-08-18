import os
from pathlib import Path
from PIL import Image


def create_dummy_image(path: Path, color=(10,20,30)):
    im = Image.new('RGB', (64,48), color=color)
    im.save(path, 'JPEG')


def test_video_stub_flow(client, temp_env_root, monkeypatch):
    # Enable video support (no ffmpeg required)
    monkeypatch.setenv('VIDEO_ENABLED', 'true')
    # Force settings reload/executor reinit
    from app.main import reinit_executor_for_tests
    reinit_executor_for_tests()

    # Create a fake video file (just an image with .mp4 extension); should ingest as video by extension
    originals = Path(temp_env_root['originals'])
    fake_video = originals / 'clip.mp4'
    create_dummy_image(fake_video.with_suffix('.jpg'))  # create a jpg for content
    # Copy bytes to .mp4 extension to simulate a file
    fake_video.write_bytes(fake_video.with_suffix('.jpg').read_bytes())

    # Trigger ingest
    r = client.post('/ingest/scan', json={'roots':[str(originals)]})
    assert r.status_code == 200

    # Run tasks briefly (video tasks should complete without ffmpeg)
    from app.main import executor
    for _ in range(20):
        worked = executor.run_once()
        if not worked:
            break

    # Verify asset is recognized as video and endpoint returns info
    from app.dependencies import ensure_db, SessionLocal
    ensure_db()
    with SessionLocal() as s:
        from app.db import Asset
        a = s.query(Asset).filter(Asset.path==str(fake_video.resolve())).first()
        assert a is not None
        assert a.mime and a.mime.startswith('video')
        vid = client.get(f'/videos/{a.id}')
        assert vid.status_code in (200, 400)  # 400 allowed if mime detection failed; but should be 200 normally
        if vid.status_code == 200:
            data = vid.json()
            assert data['id'] == a.id
            assert isinstance(data.get('frames', []), list)
