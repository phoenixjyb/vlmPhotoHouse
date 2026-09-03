from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.face_alignment import (
    ARCFACE_112_TEMPLATE,
    align_face_112,
    estimate_similarity_matrix,
)
from app.face_embedding_artifacts import (
    LVFACE_B_GLINT360K_NATIVE_512,
    face_embedding_path,
    load_normalized_embedding,
    person_embedding_path,
)


def test_similarity_matrix_maps_source_landmarks_to_template():
    source = (ARCFACE_112_TEMPLATE * 1.25) + np.asarray((17.0, -9.0))
    matrix = estimate_similarity_matrix(source)
    homogeneous = np.column_stack((source, np.ones(5)))
    mapped = (matrix @ homogeneous.T).T[:, :2]
    assert np.allclose(mapped, ARCFACE_112_TEMPLATE, atol=1e-5)


def test_align_face_112_has_expected_size():
    image = Image.new('RGB', (160, 160), color=(100, 120, 140))
    aligned = align_face_112(image, ARCFACE_112_TEMPLATE)
    assert aligned.size == (112, 112)
    assert aligned.mode == 'RGB'


def test_alignment_rejects_invalid_landmark_count():
    with pytest.raises(ValueError, match='exactly five'):
        estimate_similarity_matrix([(1.0, 2.0)] * 4)


def test_versioned_embedding_paths_are_scoped_and_safe(tmp_path: Path):
    face_path = face_embedding_path(
        tmp_path, LVFACE_B_GLINT360K_NATIVE_512, face_id=42
    )
    person_path = person_embedding_path(
        tmp_path, LVFACE_B_GLINT360K_NATIVE_512, person_id=7
    )
    assert face_path == (
        tmp_path
        / 'face_embeddings'
        / LVFACE_B_GLINT360K_NATIVE_512
        / '42.npy'
    )
    assert person_path == (
        tmp_path
        / 'person_embeddings'
        / LVFACE_B_GLINT360K_NATIVE_512
        / '7.npy'
    )
    with pytest.raises(ValueError, match='unsafe embedding version'):
        face_embedding_path(tmp_path, '../escape', face_id=42)


def test_load_normalized_embedding_enforces_dimension(tmp_path: Path):
    path = tmp_path / 'vector.npy'
    np.save(path, np.asarray([3.0, 4.0], dtype='float32'))
    vector = load_normalized_embedding(path, expected_dim=2)
    assert np.allclose(vector, np.asarray([0.6, 0.8], dtype='float32'))
    with pytest.raises(ValueError, match='expected 3, got 2'):
        load_normalized_embedding(path, expected_dim=3)


def test_face_task_persists_landmarks_and_writes_separate_aligned_crop(
    temp_env_root, monkeypatch
):
    import uuid

    import app.main as app_main
    import app.tasks as tasks_module
    from app.db import Asset, FaceDetection, Task
    from app.face_detection_service import DetectedFace
    from sqlalchemy import inspect

    derived_root = Path(temp_env_root['derived'])
    monkeypatch.setattr(tasks_module, 'DERIVED_DIR', derived_root)

    class LandmarkDetector:
        def detect(self, _image):
            return [
                DetectedFace(
                    x=20.0,
                    y=20.0,
                    w=100.0,
                    h=110.0,
                    landmarks=tuple(tuple(point) for point in ARCFACE_112_TEMPLATE),
                )
            ]

    import app.face_detection_service as detection_module

    monkeypatch.setattr(
        detection_module,
        'get_face_detection_provider',
        lambda: LandmarkDetector(),
    )

    image_path = Path(temp_env_root['originals']) / 'alignment-source.jpg'
    Image.new('RGB', (160, 160), color=(90, 110, 130)).save(image_path)

    with app_main.SessionLocal() as session:
        schema = inspect(session.get_bind())
        assert 'face_embedding_artifacts' in schema.get_table_names()
        assert 'person_embedding_artifacts' in schema.get_table_names()
        face_columns = {
            column['name'] for column in schema.get_columns('face_detections')
        }
        assert {'landmarks_json', 'landmark_model'} <= face_columns

        asset = Asset(path=str(image_path), hash_sha256=uuid.uuid4().hex)
        session.add(asset)
        session.flush()
        task = Task(type='face', payload_json={'asset_id': asset.id})
        session.add(task)
        session.flush()
        app_main.executor._handle_face(session, task)
        face = (
            session.query(FaceDetection)
            .filter(FaceDetection.asset_id == asset.id)
            .one()
        )
        face_id = face.id
        assert face.landmarks_json == ARCFACE_112_TEMPLATE.tolist()
        assert face.landmark_model == 'LandmarkDetector'

    legacy_crop = derived_root / 'faces' / '256' / f'{face_id}.jpg'
    aligned_crop = derived_root / 'faces' / 'aligned-112' / f'{face_id}.png'
    assert legacy_crop.exists()
    assert aligned_crop.exists()
    with Image.open(aligned_crop) as aligned:
        assert aligned.size == (112, 112)
