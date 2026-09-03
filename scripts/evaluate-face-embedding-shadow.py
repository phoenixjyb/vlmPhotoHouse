#!/usr/bin/env python3
"""Evaluate PhotoHouse face embeddings without changing labels or storage.

The evaluation uses manually assigned faces as references. It performs
leave-one-out classification for those manual examples, compares existing DNN
assignments with manual centroids where possible, and estimates acceptance for
currently unassigned faces. Output is aggregate JSON only; names, media paths,
and individual face or person identifiers are never printed.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np


DEFAULT_THRESHOLDS = (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)


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
    parser.add_argument("--dimension", type=int, default=512)
    parser.add_argument("--min-reference-faces", type=int, default=2)
    parser.add_argument("--margin", type=float, default=0.02)
    return parser.parse_args()


def _resolve_embedding_path(value: str, data_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    normalized = value.replace("\\", "/")
    if normalized.lower().startswith("derived/"):
        return data_root / Path(normalized)
    return path


def _load_vector(value: str, data_root: Path, dimension: int) -> np.ndarray | None:
    path = _resolve_embedding_path(value, data_root)
    if not path.exists():
        return None
    try:
        vector = np.asarray(np.load(path, mmap_mode="r", allow_pickle=False), dtype="float32").reshape(-1)
    except Exception:
        return None
    if int(vector.size) != dimension:
        return None
    norm = float(np.linalg.norm(vector))
    if norm <= 0:
        return None
    return vector / norm


def _percentiles(values: Iterable[float]) -> dict[str, float | int | None]:
    array = np.asarray(list(values), dtype="float32")
    if not array.size:
        return {"count": 0, "p05": None, "p25": None, "p50": None, "p75": None, "p95": None}
    return {
        "count": int(array.size),
        "p05": round(float(np.percentile(array, 5)), 6),
        "p25": round(float(np.percentile(array, 25)), 6),
        "p50": round(float(np.percentile(array, 50)), 6),
        "p75": round(float(np.percentile(array, 75)), 6),
        "p95": round(float(np.percentile(array, 95)), 6),
    }


def _normalized_centroid(vectors: list[np.ndarray]) -> np.ndarray | None:
    if not vectors:
        return None
    centroid = np.mean(np.stack(vectors), axis=0).astype("float32")
    norm = float(np.linalg.norm(centroid))
    return centroid / norm if norm > 0 else None


def evaluate(
    database: Path,
    data_root: Path,
    dimension: int,
    min_reference_faces: int,
    margin: float,
) -> dict[str, object]:
    database = database.resolve()
    uri = f"file:{database.as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        manual_vectors: dict[int, list[np.ndarray]] = defaultdict(list)
        manual_rows = connection.execute(
            "SELECT person_id, embedding_path FROM face_detections "
            "WHERE person_id IS NOT NULL AND label_source = 'manual' "
            "AND embedding_path IS NOT NULL AND TRIM(embedding_path) <> ''"
        )
        manual_dimension_counts: Counter[int] = Counter()
        manual_unreadable = 0
        for person_id, embedding_path in manual_rows:
            path = _resolve_embedding_path(str(embedding_path), data_root)
            try:
                raw = np.load(path, mmap_mode="r", allow_pickle=False)
                manual_dimension_counts[int(raw.size)] += 1
            except Exception:
                manual_unreadable += 1
                continue
            vector = _load_vector(str(embedding_path), data_root, dimension)
            if vector is not None:
                manual_vectors[int(person_id)].append(vector)

        eligible = {
            person_id: vectors
            for person_id, vectors in manual_vectors.items()
            if len(vectors) >= min_reference_faces
        }
        centroids = {
            person_id: centroid
            for person_id, vectors in eligible.items()
            if (centroid := _normalized_centroid(vectors)) is not None
        }

        genuine_scores: list[float] = []
        impostor_scores: list[float] = []
        margins: list[float] = []
        top1_correct = 0
        loo_records: list[tuple[float, float, bool]] = []
        for person_id, vectors in eligible.items():
            for index, vector in enumerate(vectors):
                own = _normalized_centroid(vectors[:index] + vectors[index + 1 :])
                if own is None:
                    continue
                own_score = float(np.dot(vector, own))
                other_scores = [
                    float(np.dot(vector, centroid))
                    for other_id, centroid in centroids.items()
                    if other_id != person_id
                ]
                best_other = max(other_scores) if other_scores else -1.0
                is_correct = own_score > best_other
                genuine_scores.append(own_score)
                impostor_scores.append(best_other)
                margins.append(own_score - best_other)
                top1_correct += int(is_correct)
                loo_records.append((own_score, own_score - best_other, is_correct))

        threshold_results: dict[str, dict[str, float | int]] = {}
        for threshold in DEFAULT_THRESHOLDS:
            accepted = [
                record
                for record in loo_records
                if record[0] >= threshold and record[1] >= margin
            ]
            correct = sum(int(record[2]) for record in accepted)
            threshold_results[f"{threshold:.2f}"] = {
                "accepted": len(accepted),
                "coverage": round(len(accepted) / len(loo_records), 6) if loo_records else 0.0,
                "precision": round(correct / len(accepted), 6) if accepted else 0.0,
            }

        def score_rows(sql: str) -> dict[str, object]:
            evaluated = 0
            current_assignment_in_reference_set = 0
            top1_agrees = 0
            best_scores: list[float] = []
            score_margins: list[float] = []
            accepted_by_threshold = Counter()
            for person_id, embedding_path in connection.execute(sql):
                vector = _load_vector(str(embedding_path), data_root, dimension)
                if vector is None or not centroids:
                    continue
                scores = sorted(
                    (
                        (float(np.dot(vector, centroid)), candidate_id)
                        for candidate_id, centroid in centroids.items()
                    ),
                    reverse=True,
                )
                evaluated += 1
                best_score, best_person = scores[0]
                second_score = scores[1][0] if len(scores) > 1 else -1.0
                score_margin = best_score - second_score
                best_scores.append(best_score)
                score_margins.append(score_margin)
                if person_id is not None and int(person_id) in centroids:
                    current_assignment_in_reference_set += 1
                    top1_agrees += int(best_person == int(person_id))
                for threshold in DEFAULT_THRESHOLDS:
                    if best_score >= threshold and score_margin >= margin:
                        accepted_by_threshold[f"{threshold:.2f}"] += 1
            return {
                "evaluated": evaluated,
                "current_assignment_in_reference_set": current_assignment_in_reference_set,
                "top1_agrees_with_current": top1_agrees,
                "agreement_rate": round(
                    top1_agrees / current_assignment_in_reference_set, 6
                )
                if current_assignment_in_reference_set
                else None,
                "best_score": _percentiles(best_scores),
                "top1_margin": _percentiles(score_margins),
                "accepted_by_threshold": dict(sorted(accepted_by_threshold.items())),
            }

        dnn = score_rows(
            "SELECT person_id, embedding_path FROM face_detections "
            "WHERE person_id IS NOT NULL AND label_source = 'dnn' "
            "AND embedding_path IS NOT NULL AND TRIM(embedding_path) <> ''"
        )
        unassigned = score_rows(
            "SELECT person_id, embedding_path FROM face_detections "
            "WHERE person_id IS NULL AND embedding_path IS NOT NULL "
            "AND TRIM(embedding_path) <> ''"
        )

        return {
            "audit_mode": "sqlite mode=ro, immutable=1, query_only=ON",
            "dimension": dimension,
            "minimum_reference_faces": min_reference_faces,
            "acceptance_margin": margin,
            "manual_reference": {
                "dimension_counts": dict(sorted(manual_dimension_counts.items())),
                "unreadable": manual_unreadable,
                "eligible_people": len(centroids),
                "eligible_faces": sum(len(vectors) for vectors in eligible.values()),
            },
            "manual_leave_one_out": {
                "evaluated": len(loo_records),
                "top1_correct": top1_correct,
                "top1_accuracy": round(top1_correct / len(loo_records), 6)
                if loo_records
                else None,
                "genuine_score": _percentiles(genuine_scores),
                "best_impostor_score": _percentiles(impostor_scores),
                "genuine_minus_impostor_margin": _percentiles(margins),
                "thresholds": threshold_results,
            },
            "existing_dnn_assignments": dnn,
            "unassigned_faces": unassigned,
        }
    finally:
        connection.close()


def main() -> int:
    args = _parse_args()
    result = evaluate(
        args.database,
        args.data_root,
        args.dimension,
        args.min_reference_faces,
        args.margin,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
