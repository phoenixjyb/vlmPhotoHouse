import importlib.util
import json
import sqlite3
from pathlib import Path

import numpy as np


def _load_script():
    path = (
        Path(__file__).resolve().parents[2]
        / 'scripts'
        / 'run-aligned-face-shadow-canary.py'
    )
    spec = importlib.util.spec_from_file_location('aligned_shadow_canary', path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_database(tmp_path: Path) -> Path:
    database = tmp_path / 'metadata.sqlite'
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE face_detections (
                id INTEGER PRIMARY KEY,
                person_id INTEGER,
                embedding_path TEXT,
                landmarks_json TEXT,
                landmark_model TEXT,
                label_source TEXT
            );
            CREATE TABLE face_embedding_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                face_id INTEGER NOT NULL,
                model TEXT NOT NULL,
                model_version TEXT NOT NULL,
                dim INTEGER NOT NULL,
                alignment TEXT,
                storage_path TEXT NOT NULL,
                vector_checksum TEXT,
                status TEXT NOT NULL,
                UNIQUE(face_id, model_version)
            );
            CREATE TABLE tasks (id INTEGER PRIMARY KEY, state TEXT);
            INSERT INTO face_detections
                (id, person_id, embedding_path, label_source)
                VALUES (7, 3, 'derived/face_embeddings/7.npy', 'manual');
            INSERT INTO tasks VALUES (1, 'pending');
            """
        )
        connection.commit()
    finally:
        connection.close()
    return database


def test_persist_shadow_is_versioned_and_idempotent(tmp_path: Path):
    module = _load_script()
    database = _make_database(tmp_path)
    records = [
        {
            'face_id': 7,
            'aligned': np.arange(512, dtype='float32'),
            'aligned_png_bytes': b'bounded-test-crop',
            'landmarks': [[float(i), float(i + 1)] for i in range(5)],
            'landmark_model': 'TestDetector',
        }
    ]

    first = module._persist_shadow_artifacts(
        database,
        tmp_path,
        records,
        model='LVFace-B_Glint360K.onnx',
        model_version='lvface-b-glint360k-aligned-d512-v1',
    )
    assert first['inserted_artifacts'] == 1
    assert first['landmark_rows_filled'] == 1
    assert first['new_files'] == 2

    second = module._persist_shadow_artifacts(
        database,
        tmp_path,
        records,
        model='LVFace-B_Glint360K.onnx',
        model_version='lvface-b-glint360k-aligned-d512-v1',
    )
    assert second['inserted_artifacts'] == 0
    assert second['landmark_rows_filled'] == 0
    assert second['new_files'] == 0

    connection = sqlite3.connect(database)
    try:
        face = connection.execute(
            'SELECT person_id, embedding_path, label_source, landmarks_json, '
            'landmark_model FROM face_detections WHERE id = 7'
        ).fetchone()
        assert face[:3] == (3, 'derived/face_embeddings/7.npy', 'manual')
        assert json.loads(face[3]) == records[0]['landmarks']
        assert face[4] == 'TestDetector'
        artifact = connection.execute(
            'SELECT model_version, dim, alignment, storage_path, status '
            'FROM face_embedding_artifacts WHERE face_id = 7'
        ).fetchone()
        assert artifact == (
            'lvface-b-glint360k-aligned-d512-v1',
            512,
            'insightface-5pt-arcface-112',
            'derived/face_embeddings/lvface-b-glint360k-aligned-d512-v1/7.npy',
            'shadow',
        )
        assert connection.execute('SELECT state FROM tasks').fetchone()[0] == 'pending'
    finally:
        connection.close()
