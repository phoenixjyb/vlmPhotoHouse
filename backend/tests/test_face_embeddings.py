import os, uuid, numpy as np
from fastapi.testclient import TestClient
from app.main import SessionLocal, executor
from app.db import Asset, Task, FaceDetection


def _create_asset(path: str):
    with SessionLocal() as s:
        a = Asset(path=path, hash_sha256=uuid.uuid4().hex)
        s.add(a)
        s.commit()
        return a.id


def test_face_embedding_deterministic(client: TestClient, temp_env_root):
    # Create a dummy image file
    import PIL.Image as Image
    img_path = os.path.join(temp_env_root['originals'], f"face_{uuid.uuid4().hex}.jpg")
    Image.new('RGB', (400,400), (123,50,200)).save(img_path)
    asset_id = _create_asset(img_path)
    # Add face task then process
    with SessionLocal() as s:
        s.add(Task(type='face', priority=120, payload_json={'asset_id': asset_id}))
        s.commit()
    # Run executor until face + face_embed tasks processed
    for _ in range(50):
        worked = executor.run_once()
        # break early if face_embed done
        with SessionLocal() as s:
            f = s.query(FaceDetection).filter(FaceDetection.asset_id==asset_id).first()
            if f and f.embedding_path and os.path.exists(f.embedding_path):
                break
    with SessionLocal() as s:
        f = s.query(FaceDetection).filter(FaceDetection.asset_id==asset_id).first()
        assert f and f.embedding_path, 'face embedding not generated'
        vec1 = np.load(f.embedding_path)
    # Re-run embedding task for same face (should no-op/deterministic)
    with SessionLocal() as s:
        s.add(Task(type='face_embed', priority=110, payload_json={'face_id': f.id}))
        s.commit()
    for _ in range(10):
        executor.run_once()
    vec2 = np.load(f.embedding_path)
    assert vec1.shape == vec2.shape
    # Since deterministic, vectors should be identical
    assert np.allclose(vec1, vec2)
