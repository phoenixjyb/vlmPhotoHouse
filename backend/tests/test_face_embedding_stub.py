import os, uuid, numpy as np
from pathlib import Path
from fastapi.testclient import TestClient
import app.main as app_main
from app.db import Asset, Task, FaceDetection
from PIL import Image

def test_face_embedding_stub_deterministic(client: TestClient, temp_env_root):
    os.environ['FACE_EMBED_PROVIDER'] = 'stub'
    os.environ['FACE_EMBED_DIM'] = '64'
    # Clear settings cache and reinitialize executor/engine with test overrides
    app_main.get_settings.cache_clear()  # type: ignore
    app_main.get_settings()
    app_main.reinit_executor_for_tests()
    SessionLocal = app_main.SessionLocal  # type: ignore
    executor = app_main.executor  # type: ignore
    # Ensure schema exists on new engine
    app_main.init_db()
    # Reload tasks module to refresh DERIVED_DIR using overridden DERIVED_PATH
    import importlib, app.tasks as tasks_mod
    importlib.reload(tasks_mod)
    # Replace executor with new one if tasks module defines globals (safety)
    executor = app_main.executor  # still valid
    # Create fake asset & face crop
    originals_dir = Path(temp_env_root['originals'])
    img_path = originals_dir / f'stub_face_{uuid.uuid4().hex}.jpg'
    Image.new('RGB',(120,120),(123,40,200)).save(img_path)
    # Create DB records + crop
    from app.config import get_settings as _gs
    settings = _gs()
    with SessionLocal() as s:
        asset = Asset(path=str(img_path), hash_sha256=uuid.uuid4().hex)
        s.add(asset); s.flush()
        face = FaceDetection(asset_id=asset.id, bbox_x=10, bbox_y=10, bbox_w=60, bbox_h=60, embedding_path=None)
        s.add(face); s.flush()
        crop_path = Path(settings.derived_path) / 'faces' / '256' / f'{face.id}.jpg'
        crop_path.parent.mkdir(parents=True, exist_ok=True)
        Image.open(img_path).crop((10,10,70,70)).resize((256,256)).save(crop_path)
        s.add(Task(type='face_embed', priority=120, payload_json={'face_id': face.id}))
        s.commit()
        face_id = face.id
    # Poll executor until embedding created
    for _ in range(10):
        executor.run_once()
        with SessionLocal() as s:
            f = s.get(FaceDetection, face_id)
            if f and f.embedding_path:
                break
    with SessionLocal() as s:
        f = s.get(FaceDetection, face_id)
        if not f or not f.embedding_path:
            t = s.query(Task).filter(Task.type=='face_embed').order_by(Task.id.desc()).first()
            raise AssertionError(f'Embedding not produced. Task state={t.state if t else None} last_error={t.last_error if t else None}')
        vec1 = np.load(f.embedding_path)
    # Force recompute: clear embedding_path & delete file
    import os as _os
    with SessionLocal() as s:
        f = s.get(FaceDetection, face_id)
        first_vec = vec1.copy()
        emb_path = f.embedding_path
        f.embedding_path = None
        s.add(Task(type='face_embed', priority=120, payload_json={'face_id': face_id}))
        s.commit()
    if emb_path and Path(emb_path).exists():
        Path(emb_path).unlink()
    for _ in range(10):
        executor.run_once()
        with SessionLocal() as s:
            f2 = s.get(FaceDetection, face_id)
            if f2 and f2.embedding_path:
                break
    with SessionLocal() as s:
        f2 = s.get(FaceDetection, face_id)
        if not f2 or not f2.embedding_path:
            t = s.query(Task).filter(Task.type=='face_embed').order_by(Task.id.desc()).first()
            raise AssertionError(f'Recompute embedding missing. Task state={t.state if t else None} last_error={t.last_error if t else None}')
        vec2 = np.load(f2.embedding_path)
    assert np.allclose(first_vec, vec2), 'Stub embedding not deterministic'
