#!/usr/bin/env python3
"""Read-only inventory for PhotoHouse face and person embeddings.

The command never imports the PhotoHouse application, so it cannot run Alembic,
create tables, enqueue tasks, or start workers. SQLite is opened with both
``mode=ro`` and ``immutable=1`` and every NumPy array is memory-mapped read-only.
Only aggregate counts and vector shapes are emitted; names and media paths are
intentionally excluded.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np


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
    return parser.parse_args()


def _resolve_embedding_path(value: str, data_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    normalized = value.replace("\\", "/")
    if normalized.lower().startswith("derived/"):
        return data_root / Path(normalized)
    return path


def _inspect_embedding_rows(
    rows: Iterable[tuple[str]], data_root: Path
) -> dict[str, object]:
    dimensions: Counter[int] = Counter()
    shapes: Counter[str] = Counter()
    checked = 0
    missing = 0
    invalid = 0

    for (value,) in rows:
        if not value:
            continue
        checked += 1
        path = _resolve_embedding_path(str(value), data_root)
        if not path.exists():
            missing += 1
            continue
        try:
            vector = np.load(path, mmap_mode="r", allow_pickle=False)
            dimensions[int(vector.size)] += 1
            shapes[str(tuple(vector.shape))] += 1
        except Exception:
            invalid += 1

    return {
        "rows_checked": checked,
        "dimensions": dict(sorted(dimensions.items())),
        "shapes": dict(sorted(shapes.items())),
        "missing_files": missing,
        "invalid_files": invalid,
    }


def _inspect_face_embedding_rows(
    rows: Iterable[tuple[str, str | None, int | None]], data_root: Path
) -> dict[str, object]:
    dimensions: Counter[int] = Counter()
    shapes: Counter[str] = Counter()
    dimensions_by_assignment: dict[str, Counter[int]] = {
        "assigned": Counter(),
        "unassigned": Counter(),
    }
    dimensions_by_label_source: dict[str, Counter[int]] = {}
    parent_directories: Counter[str] = Counter()
    checked = 0
    missing = 0
    invalid = 0

    for value, label_source, person_id in rows:
        if not value:
            continue
        checked += 1
        path = _resolve_embedding_path(str(value), data_root)
        parent_directories[path.parent.name or "(none)"] += 1
        if not path.exists():
            missing += 1
            continue
        try:
            vector = np.load(path, mmap_mode="r", allow_pickle=False)
            dimension = int(vector.size)
            dimensions[dimension] += 1
            shapes[str(tuple(vector.shape))] += 1
            assignment = "assigned" if person_id is not None else "unassigned"
            dimensions_by_assignment[assignment][dimension] += 1
            source = str(label_source) if label_source is not None else "null"
            dimensions_by_label_source.setdefault(source, Counter())[dimension] += 1
        except Exception:
            invalid += 1

    return {
        "rows_checked": checked,
        "dimensions": dict(sorted(dimensions.items())),
        "shapes": dict(sorted(shapes.items())),
        "dimensions_by_assignment": {
            key: dict(sorted(value.items()))
            for key, value in dimensions_by_assignment.items()
        },
        "dimensions_by_label_source": {
            key: dict(sorted(value.items()))
            for key, value in sorted(dimensions_by_label_source.items())
        },
        "parent_directories": dict(sorted(parent_directories.items())),
        "missing_files": missing,
        "invalid_files": invalid,
    }


def audit(database: Path, data_root: Path) -> dict[str, object]:
    database = database.resolve()
    stat = database.stat()
    wal_path = Path(f"{database}-wal")
    shm_path = Path(f"{database}-shm")
    uri = f"file:{database.as_posix()}?mode=ro&immutable=1"

    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        result: dict[str, object] = {
            "audit_mode": "sqlite mode=ro, immutable=1, query_only=ON",
            "database": {
                "size_bytes": stat.st_size,
                "modified_utc": datetime.fromtimestamp(
                    stat.st_mtime, timezone.utc
                ).isoformat(),
                "wal_present": wal_path.exists(),
                "wal_size_bytes": wal_path.stat().st_size if wal_path.exists() else 0,
                "shm_present": shm_path.exists(),
            },
            "tables_present": sorted(
                name
                for name in (
                    "alembic_version",
                    "face_detections",
                    "persons",
                    "face_assignment_events",
                    "face_embedding_artifacts",
                    "person_embedding_artifacts",
                    "tasks",
                )
                if name in tables
            ),
        }

        if "alembic_version" in tables:
            result["alembic_version"] = [
                row[0]
                for row in connection.execute(
                    "SELECT version_num FROM alembic_version"
                )
            ]

        if "face_detections" in tables:
            face_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(face_detections)")
            }
            result["face_schema"] = {
                "landmarks_json_present": "landmarks_json" in face_columns,
                "landmark_model_present": "landmark_model" in face_columns,
            }
            result["faces"] = {
                "total": connection.execute(
                    "SELECT COUNT(*) FROM face_detections"
                ).fetchone()[0],
                "with_embedding_path": connection.execute(
                    "SELECT COUNT(*) FROM face_detections "
                    "WHERE embedding_path IS NOT NULL "
                    "AND TRIM(embedding_path) <> ''"
                ).fetchone()[0],
                "with_landmarks": connection.execute(
                    "SELECT COUNT(*) FROM face_detections "
                    "WHERE landmarks_json IS NOT NULL"
                ).fetchone()[0]
                if "landmarks_json" in face_columns
                else 0,
                "assigned": connection.execute(
                    "SELECT COUNT(*) FROM face_detections WHERE person_id IS NOT NULL"
                ).fetchone()[0],
                "unassigned_with_embedding": connection.execute(
                    "SELECT COUNT(*) FROM face_detections "
                    "WHERE person_id IS NULL AND embedding_path IS NOT NULL "
                    "AND TRIM(embedding_path) <> ''"
                ).fetchone()[0],
                "label_sources": {
                    str(source): count
                    for source, count in connection.execute(
                        "SELECT COALESCE(label_source, 'null'), COUNT(*) "
                        "FROM face_detections "
                        "GROUP BY COALESCE(label_source, 'null')"
                    )
                },
            }
            result["face_embedding_files"] = _inspect_face_embedding_rows(
                connection.execute(
                    "SELECT embedding_path, label_source, person_id "
                    "FROM face_detections "
                    "WHERE embedding_path IS NOT NULL "
                    "AND TRIM(embedding_path) <> ''"
                ),
                data_root,
            )

        if "face_embedding_artifacts" in tables:
            result["face_embedding_artifacts"] = {
                "total": connection.execute(
                    "SELECT COUNT(*) FROM face_embedding_artifacts"
                ).fetchone()[0],
                "by_version_dim_status": [
                    {
                        "model": str(model),
                        "model_version": str(version),
                        "dim": int(dimension),
                        "status": str(status),
                        "count": int(count),
                    }
                    for model, version, dimension, status, count in connection.execute(
                        "SELECT model, model_version, dim, status, COUNT(*) "
                        "FROM face_embedding_artifacts "
                        "GROUP BY model, model_version, dim, status "
                        "ORDER BY model_version, dim, status"
                    )
                ],
            }

        if "persons" in tables:
            result["persons"] = {
                "total": connection.execute(
                    "SELECT COUNT(*) FROM persons"
                ).fetchone()[0],
                "named": connection.execute(
                    "SELECT COUNT(*) FROM persons "
                    "WHERE display_name IS NOT NULL AND TRIM(display_name) <> ''"
                ).fetchone()[0],
                "with_embedding_path": connection.execute(
                    "SELECT COUNT(*) FROM persons "
                    "WHERE embedding_path IS NOT NULL "
                    "AND TRIM(embedding_path) <> ''"
                ).fetchone()[0],
            }
            result["person_embedding_files"] = _inspect_embedding_rows(
                connection.execute(
                    "SELECT embedding_path FROM persons "
                    "WHERE embedding_path IS NOT NULL "
                    "AND TRIM(embedding_path) <> ''"
                ),
                data_root,
            )

        if "person_embedding_artifacts" in tables:
            result["person_embedding_artifacts"] = {
                "total": connection.execute(
                    "SELECT COUNT(*) FROM person_embedding_artifacts"
                ).fetchone()[0],
                "by_version_dim_status": [
                    {
                        "model": str(model),
                        "model_version": str(version),
                        "dim": int(dimension),
                        "status": str(status),
                        "count": int(count),
                    }
                    for model, version, dimension, status, count in connection.execute(
                        "SELECT model, model_version, dim, status, COUNT(*) "
                        "FROM person_embedding_artifacts "
                        "GROUP BY model, model_version, dim, status "
                        "ORDER BY model_version, dim, status"
                    )
                ],
            }

        if "face_assignment_events" in tables:
            result["assignment_events"] = {
                "total": connection.execute(
                    "SELECT COUNT(*) FROM face_assignment_events"
                ).fetchone()[0],
                "sources": {
                    str(source): count
                    for source, count in connection.execute(
                        "SELECT COALESCE(source, 'null'), COUNT(*) "
                        "FROM face_assignment_events "
                        "GROUP BY COALESCE(source, 'null')"
                    )
                },
            }

        if "tasks" in tables:
            result["active_face_tasks"] = {
                str(task_type): count
                for task_type, count in connection.execute(
                    "SELECT type, COUNT(*) FROM tasks "
                    "WHERE state IN ('pending', 'running') "
                    "AND (type LIKE 'face%' OR type LIKE 'person%') "
                    "GROUP BY type"
                )
            }

        return result
    finally:
        connection.close()


def main() -> int:
    args = _parse_args()
    result = audit(args.database, args.data_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
