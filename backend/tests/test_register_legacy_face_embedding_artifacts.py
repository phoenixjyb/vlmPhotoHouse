import importlib.util
import sqlite3
from pathlib import Path

import numpy as np


def _load_script():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "register-legacy-face-embedding-artifacts.py"
    )
    spec = importlib.util.spec_from_file_location("legacy_artifact_registration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_database(tmp_path: Path) -> tuple[Path, Path, Path]:
    database = tmp_path / "metadata.sqlite"
    face_path = tmp_path / "face.npy"
    person_path = tmp_path / "person.npy"
    np.save(face_path, np.arange(512, dtype="float32"))
    np.save(person_path, np.arange(128, dtype="float32"))
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE persons (
                id INTEGER PRIMARY KEY,
                embedding_path TEXT,
                display_name TEXT,
                face_count INTEGER
            );
            CREATE TABLE face_detections (
                id INTEGER PRIMARY KEY,
                person_id INTEGER,
                embedding_path TEXT,
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
            CREATE TABLE person_embedding_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                model TEXT NOT NULL,
                model_version TEXT NOT NULL,
                dim INTEGER NOT NULL,
                source_face_count INTEGER NOT NULL,
                storage_path TEXT NOT NULL,
                vector_checksum TEXT,
                status TEXT NOT NULL,
                UNIQUE(person_id, model_version)
            );
            CREATE TABLE tasks (id INTEGER PRIMARY KEY, state TEXT);
            """
        )
        connection.execute(
            "INSERT INTO persons VALUES (1, ?, 'preserve-name', 1)",
            (str(person_path),),
        )
        connection.execute(
            "INSERT INTO face_detections VALUES (1, 1, ?, 'manual')",
            (str(face_path),),
        )
        connection.execute("INSERT INTO tasks VALUES (1, 'pending')")
        connection.commit()
    finally:
        connection.close()
    return database, face_path, person_path


def test_registration_is_dry_run_by_default_and_idempotent(tmp_path: Path):
    module = _load_script()
    database, face_path, person_path = _make_database(tmp_path)

    dry_run = module.register(database, tmp_path, apply=False)
    assert dry_run["registration"]["pending_face_artifacts"] == 1
    assert dry_run["registration"]["pending_person_artifacts"] == 1

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM face_embedding_artifacts"
        ).fetchone()[0] == 0
    finally:
        connection.close()

    applied = module.register(database, tmp_path, apply=True)
    assert applied["registration"]["inserted_face_artifacts"] == 1
    assert applied["registration"]["inserted_person_artifacts"] == 1

    repeated = module.register(database, tmp_path, apply=True)
    assert repeated["registration"]["inserted_face_artifacts"] == 0
    assert repeated["registration"]["inserted_person_artifacts"] == 0

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT model, model_version, dim, alignment, storage_path, status "
            "FROM face_embedding_artifacts"
        ).fetchone() == (
            "unknown-legacy",
            "legacy-unversioned-d512",
            512,
            None,
            str(face_path),
            "legacy",
        )
        assert connection.execute(
            "SELECT model_version, dim, storage_path, status "
            "FROM person_embedding_artifacts"
        ).fetchone() == (
            "legacy-unversioned-d128",
            128,
            str(person_path),
            "legacy",
        )
        assert connection.execute(
            "SELECT person_id, embedding_path, label_source "
            "FROM face_detections"
        ).fetchone() == (1, str(face_path), "manual")
        assert connection.execute(
            "SELECT display_name, embedding_path FROM persons"
        ).fetchone() == ("preserve-name", str(person_path))
        assert connection.execute("SELECT state FROM tasks").fetchone()[0] == "pending"
    finally:
        connection.close()
