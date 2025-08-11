import os, time
from fastapi.testclient import TestClient
from app.main import app, SessionLocal
from app.db import Task
from app.tasks import TaskExecutor
from app.config import get_settings

client = TestClient(app)

def _seed_faces(n=40):
    # Create fake faces with embeddings to trigger recluster meaningful progress
    import numpy as np
    from app.db import FaceDetection, Person
    from app.tasks import DERIVED_DIR, EMBED_DIM
    with SessionLocal() as s:
        for i in range(n):
            f = FaceDetection(asset_id=1, bbox_x=0, bbox_y=0, bbox_w=10, bbox_h=10, person_id=None, embedding_path=None)
            s.add(f)
            s.flush()
            vec = np.random.rand(EMBED_DIM).astype('float32')
            emb_path = DERIVED_DIR / 'face_embeddings' / f'{f.id}.npy'
            np.save(emb_path, vec)
            f.embedding_path = str(emb_path)
        s.commit()

def test_recluster_progress_and_cancel(monkeypatch):
    _seed_faces(60)
    monkeypatch.setenv('PERSON_RECLUSTER_PER_FACE_SLEEP', '0.01')
    # fire recluster
    r = client.post('/persons/recluster')
    assert r.status_code == 200
    task_id = r.json()['task_id']
    # Immediately request cancel
    c = client.post(f'/tasks/{task_id}/cancel')
    assert c.status_code == 200
    # Run executor loop manually to process recluster task
    settings = get_settings()
    executor = TaskExecutor(SessionLocal, settings)
    deadline = time.time() + 5
    final = None
    while time.time() < deadline:
        executor.run_once()
        t = client.get(f'/tasks/{task_id}').json()['task']
        if t['state'] in ('done','failed','canceled'):
            final = t
            break
        time.sleep(0.02)
    assert final is not None
    # Either canceled early or finished quickly; ensure progress fields present
    assert final['progress_current'] is not None
    assert final['progress_total'] is not None
    # If canceled, cancel_requested should be true
    if final['state'] == 'canceled':
        assert final['cancel_requested'] is True
