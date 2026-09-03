#!/usr/bin/env python3
"""Register existing face and person vectors as immutable legacy artifacts.

The default mode is a read-only dry run. Pass ``--apply`` only after the
versioned-artifact migration has been applied and a verified database backup
exists. The command never changes active embedding paths, labels, assignments,
or task rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


LEGACY_MODEL = "unknown-legacy"
LEGACY_VERSIONS = {
    128: "legacy-unversioned-d128",
    512: "legacy-unversioned-d512",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(r"E:\VLM_DATA\databases\metadata.sqlite"),
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(r"E:\VLM_DATA"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Insert missing artifact rows in one transaction.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON receipt path.")
    return parser.parse_args()


def _resolve_path(value: str, data_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    normalized = value.replace("\\", "/")
    if normalized.lower().startswith("derived/"):
        return data_root / Path(normalized)
    return path


def _inspect_vector(path: Path) -> tuple[int, str]:
    vector = np.load(path, mmap_mode="r", allow_pickle=False)
    dimension = int(vector.size)
    if dimension not in LEGACY_VERSIONS:
        raise ValueError(f"unsupported legacy dimension {dimension}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return dimension, digest.hexdigest()


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def _collect(
    connection: sqlite3.Connection, data_root: Path
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    face_items: list[dict[str, object]] = []
    person_items: list[dict[str, object]] = []
    dimensions: Counter[int] = Counter()
    errors: list[dict[str, object]] = []

    for face_id, value in connection.execute(
        "SELECT id, embedding_path FROM face_detections "
        "WHERE embedding_path IS NOT NULL AND TRIM(embedding_path) <> '' "
        "ORDER BY id"
    ):
        path = _resolve_path(str(value), data_root)
        try:
            dimension, checksum = _inspect_vector(path)
        except Exception as exc:
            errors.append({"kind": "face", "id": int(face_id), "error": str(exc)})
            continue
        dimensions[dimension] += 1
        face_items.append(
            {
                "subject_id": int(face_id),
                "model_version": LEGACY_VERSIONS[dimension],
                "dim": dimension,
                "storage_path": str(value),
                "vector_checksum": checksum,
            }
        )

    for person_id, value, source_face_count in connection.execute(
        "SELECT p.id, p.embedding_path, COUNT(f.id) "
        "FROM persons p LEFT JOIN face_detections f ON f.person_id = p.id "
        "WHERE p.embedding_path IS NOT NULL AND TRIM(p.embedding_path) <> '' "
        "GROUP BY p.id, p.embedding_path ORDER BY p.id"
    ):
        path = _resolve_path(str(value), data_root)
        try:
            dimension, checksum = _inspect_vector(path)
        except Exception as exc:
            errors.append(
                {"kind": "person", "id": int(person_id), "error": str(exc)}
            )
            continue
        dimensions[dimension] += 1
        person_items.append(
            {
                "subject_id": int(person_id),
                "model_version": LEGACY_VERSIONS[dimension],
                "dim": dimension,
                "source_face_count": int(source_face_count),
                "storage_path": str(value),
                "vector_checksum": checksum,
            }
        )

    return face_items, person_items, {
        "dimensions": dict(sorted(dimensions.items())),
        "errors": errors,
    }


def _existing_rows(
    connection: sqlite3.Connection, table: str, id_column: str
) -> dict[tuple[int, str], tuple[object, ...]]:
    return {
        (int(row[0]), str(row[1])): tuple(row[2:])
        for row in connection.execute(
            f"SELECT {id_column}, model_version, model, dim, storage_path, "
            f"vector_checksum, status FROM {table}"
        )
    }


def register(
    database: Path, data_root: Path, *, apply: bool
) -> dict[str, object]:
    database = database.resolve()
    uri = f"file:{database.as_posix()}?mode={'rw' if apply else 'ro'}"
    connection = sqlite3.connect(uri, uri=True)
    if not apply:
        connection.execute("PRAGMA query_only=ON")
    try:
        tables = _tables(connection)
        required_source = {"face_detections", "persons"}
        if not required_source <= tables:
            missing = sorted(required_source - tables)
            raise RuntimeError(f"missing source tables: {', '.join(missing)}")

        face_items, person_items, inspection = _collect(connection, data_root)
        artifact_tables = {
            "face_embedding_artifacts",
            "person_embedding_artifacts",
        }
        schema_ready = artifact_tables <= tables
        result: dict[str, object] = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "apply" if apply else "dry-run",
            "database": str(database),
            "legacy_model": LEGACY_MODEL,
            "schema_ready": schema_ready,
            "source": {
                "face_vectors": len(face_items),
                "person_vectors": len(person_items),
                **inspection,
            },
            "invariants": {
                "active_embedding_paths_changed": 0,
                "assignments_changed": 0,
                "labels_changed": 0,
                "tasks_changed": 0,
            },
        }
        if inspection["errors"]:
            raise RuntimeError(
                f"refusing registration: {len(inspection['errors'])} vector errors"
            )
        if not schema_ready:
            if apply:
                raise RuntimeError("artifact tables are missing; apply migration first")
            result["registration"] = {
                "ready_to_apply": False,
                "reason": "artifact tables are missing; apply migration first",
            }
            return result

        existing_faces = _existing_rows(
            connection, "face_embedding_artifacts", "face_id"
        )
        existing_persons = _existing_rows(
            connection, "person_embedding_artifacts", "person_id"
        )
        mismatches: list[dict[str, object]] = []
        pending_faces: list[dict[str, object]] = []
        pending_persons: list[dict[str, object]] = []

        for item in face_items:
            key = (int(item["subject_id"]), str(item["model_version"]))
            expected = (
                LEGACY_MODEL,
                item["dim"],
                item["storage_path"],
                item["vector_checksum"],
                "legacy",
            )
            if key not in existing_faces:
                pending_faces.append(item)
            elif existing_faces[key] != expected:
                mismatches.append({"kind": "face", "id": key[0]})

        for item in person_items:
            key = (int(item["subject_id"]), str(item["model_version"]))
            expected = (
                LEGACY_MODEL,
                item["dim"],
                item["storage_path"],
                item["vector_checksum"],
                "legacy",
            )
            if key not in existing_persons:
                pending_persons.append(item)
            elif existing_persons[key] != expected:
                mismatches.append({"kind": "person", "id": key[0]})

        result["registration"] = {
            "ready_to_apply": not mismatches,
            "existing_face_artifacts": len(face_items) - len(pending_faces),
            "existing_person_artifacts": len(person_items) - len(pending_persons),
            "pending_face_artifacts": len(pending_faces),
            "pending_person_artifacts": len(pending_persons),
            "mismatches": mismatches,
        }
        if mismatches:
            raise RuntimeError(
                f"refusing registration: {len(mismatches)} existing rows mismatch"
            )

        if apply:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                "INSERT INTO face_embedding_artifacts "
                "(face_id, model, model_version, dim, alignment, storage_path, "
                "vector_checksum, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        item["subject_id"],
                        LEGACY_MODEL,
                        item["model_version"],
                        item["dim"],
                        None,
                        item["storage_path"],
                        item["vector_checksum"],
                        "legacy",
                    )
                    for item in pending_faces
                ],
            )
            connection.executemany(
                "INSERT INTO person_embedding_artifacts "
                "(person_id, model, model_version, dim, source_face_count, "
                "storage_path, vector_checksum, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        item["subject_id"],
                        LEGACY_MODEL,
                        item["model_version"],
                        item["dim"],
                        item["source_face_count"],
                        item["storage_path"],
                        item["vector_checksum"],
                        "legacy",
                    )
                    for item in pending_persons
                ],
            )
            connection.commit()
            result["registration"]["inserted_face_artifacts"] = len(pending_faces)
            result["registration"]["inserted_person_artifacts"] = len(
                pending_persons
            )
        return result
    except Exception:
        if connection.in_transaction and apply:
            connection.rollback()
        raise
    finally:
        connection.close()


def main() -> int:
    args = _parse_args()
    report = register(args.database, args.data_root, apply=args.apply)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
