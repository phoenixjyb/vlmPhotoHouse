import os, time, hashlib
from pathlib import Path
from PIL import Image


def create_dummy_image(path: Path, color=(128,128,128)):
    from PIL import Image
    im = Image.new('RGB', (400,300), color=color)
    im.save(path, 'JPEG')


def test_ingest_and_tasks_flow(client, temp_env_root):
    # create a few images
    originals = Path(temp_env_root['originals'])
    for i in range(3):
        create_dummy_image(originals / f'img_{i}.jpg', color=(10*i, 20, 30))
    # trigger ingest
    r = client.post('/ingest/scan', json={'roots':[str(originals)]})
    assert r.status_code == 200
    data = r.json()
    # updated key: new_assets replaces ingested
    assert data['new_assets'] >= 3
    # Manually run tasks via executor (inline worker disabled in tests)
    from app.main import executor
    # Run until no tasks or safety limit
    for _ in range(100):
        worked = executor.run_once()
        if not worked:
            break
    # Search should return assets (total replaces count)
    search = client.get('/search', params={'q':'img_'}).json()
    assert search['total'] >=3
    # Faces & persons endpoints reachable after face tasks
    persons = client.get('/persons').json()
    assert 'persons' in persons
