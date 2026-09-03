#!/usr/bin/env python3
"""Compare legacy crops with landmark-aligned LVFace embeddings in shadow mode.

The live database is opened immutable/read-only. Source photos are read in place,
aligned crops exist only in a temporary directory, and no labels, embeddings,
tasks, or person assignments are changed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--lvface-dir', type=Path, required=True)
    parser.add_argument('--lvface-python', type=Path, required=True)
    parser.add_argument('--model-name', default='LVFace-B_Glint360K.onnx')
    parser.add_argument('--people', type=int, default=8)
    parser.add_argument('--faces-per-person', type=int, default=4)
    parser.add_argument('--match-iou', type=float, default=0.40)
    parser.add_argument('--cuda-visible-devices', default='0')
    parser.add_argument('--output', type=Path)
    parser.add_argument(
        '--persist-shadow',
        action='store_true',
        help=(
            'Persist aligned crops, versioned vectors, landmarks, and shadow '
            'artifact rows. Active paths and assignments remain unchanged.'
        ),
    )
    return parser.parse_args()


def _resolve_path(value: str, data_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    normalized = value.replace('\\', '/')
    if normalized.lower().startswith('derived/'):
        return data_root / Path(normalized)
    return path


def _load_vector(value: str, data_root: Path, dimension: int = 512):
    path = _resolve_path(value, data_root)
    try:
        vector = np.asarray(
            np.load(path, mmap_mode='r', allow_pickle=False), dtype='float32'
        ).reshape(-1)
    except Exception:
        return None
    if int(vector.size) != dimension:
        return None
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 0 else None


def _iou(a, b) -> float:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (aw * ah) + (bw * bh) - intersection
    return intersection / union if union > 0 else 0.0


def _pick_evenly(rows: list[dict], count: int) -> list[dict]:
    if len(rows) <= count:
        return rows
    indexes = np.linspace(0, len(rows) - 1, num=count, dtype=int)
    return [rows[int(index)] for index in indexes]


def _centroid(vectors: list[np.ndarray]):
    if not vectors:
        return None
    value = np.mean(np.stack(vectors), axis=0).astype('float32')
    norm = float(np.linalg.norm(value))
    return value / norm if norm > 0 else None


def _evaluate(records: list[dict], key: str) -> dict[str, object]:
    groups: dict[int, list[np.ndarray]] = defaultdict(list)
    for record in records:
        groups[record['person_id']].append(record[key])

    centroids = {
        person_id: centroid
        for person_id, vectors in groups.items()
        if (centroid := _centroid(vectors)) is not None
    }
    genuine: list[float] = []
    impostor: list[float] = []
    margins: list[float] = []
    correct = 0
    evaluated = 0
    for person_id, vectors in groups.items():
        for index, vector in enumerate(vectors):
            own = _centroid(vectors[:index] + vectors[index + 1 :])
            if own is None:
                continue
            own_score = float(np.dot(vector, own))
            other_scores = [
                float(np.dot(vector, value))
                for candidate, value in centroids.items()
                if candidate != person_id
            ]
            best_other = max(other_scores) if other_scores else -1.0
            genuine.append(own_score)
            impostor.append(best_other)
            margins.append(own_score - best_other)
            correct += int(own_score > best_other)
            evaluated += 1

    def summary(values: list[float]) -> dict[str, float | None]:
        if not values:
            return {'p25': None, 'p50': None, 'p75': None}
        return {
            'p25': round(float(np.percentile(values, 25)), 6),
            'p50': round(float(np.percentile(values, 50)), 6),
            'p75': round(float(np.percentile(values, 75)), 6),
        }

    return {
        'evaluated': evaluated,
        'top1_correct': correct,
        'top1_accuracy': round(correct / evaluated, 6) if evaluated else None,
        'genuine_score': summary(genuine),
        'best_impostor_score': summary(impostor),
        'genuine_minus_impostor_margin': summary(margins),
    }


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _npy_bytes(vector: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.save(stream, np.asarray(vector, dtype='float32'), allow_pickle=False)
    return stream.getvalue()


def _persist_shadow_artifacts(
    database: Path,
    data_root: Path,
    records: list[dict],
    *,
    model: str,
    model_version: str,
) -> dict[str, object]:
    alignment = 'insightface-5pt-arcface-112'
    prepared = []
    for record in records:
        face_id = int(record['face_id'])
        crop_bytes = record['aligned_png_bytes']
        vector_bytes = _npy_bytes(record['aligned'])
        crop_path = data_root / 'derived' / 'faces' / 'aligned-112' / f'{face_id}.png'
        vector_path = (
            data_root
            / 'derived'
            / 'face_embeddings'
            / model_version
            / f'{face_id}.npy'
        )
        prepared.append(
            {
                'face_id': face_id,
                'landmarks': record['landmarks'],
                'landmark_model': record['landmark_model'],
                'crop_path': crop_path,
                'crop_bytes': crop_bytes,
                'vector_path': vector_path,
                'vector_bytes': vector_bytes,
                'vector_checksum': _sha256_bytes(vector_bytes),
                'storage_path': vector_path.relative_to(data_root).as_posix(),
            }
        )

    connection = sqlite3.connect(
        f'file:{database.resolve().as_posix()}?mode=rw', uri=True
    )
    created_paths: list[Path] = []
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if 'face_embedding_artifacts' not in tables:
            raise RuntimeError('face_embedding_artifacts table is missing')

        existing = {
            int(row[0]): tuple(row[1:])
            for row in connection.execute(
                'SELECT face_id, model, dim, alignment, storage_path, '
                'vector_checksum, status FROM face_embedding_artifacts '
                'WHERE model_version = ?',
                (model_version,),
            )
        }
        for item in prepared:
            face_id = item['face_id']
            expected = (
                model,
                512,
                alignment,
                item['storage_path'],
                item['vector_checksum'],
                'shadow',
            )
            if face_id in existing and existing[face_id] != expected:
                raise RuntimeError(
                    f'existing shadow artifact differs for face_id={face_id}'
                )
            for path_key, bytes_key in (
                ('crop_path', 'crop_bytes'),
                ('vector_path', 'vector_bytes'),
            ):
                path = item[path_key]
                expected_bytes = item[bytes_key]
                if path.exists() and path.read_bytes() != expected_bytes:
                    raise RuntimeError(f'existing shadow file differs: {path}')

        for item in prepared:
            for path_key, bytes_key in (
                ('crop_path', 'crop_bytes'),
                ('vector_path', 'vector_bytes'),
            ):
                path = item[path_key]
                if not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open('xb') as stream:
                        stream.write(item[bytes_key])
                    created_paths.append(path)

        connection.execute('BEGIN IMMEDIATE')
        inserted = 0
        landmark_updates = 0
        for item in prepared:
            cursor = connection.execute(
                'UPDATE face_detections SET landmarks_json = ?, landmark_model = ? '
                'WHERE id = ? AND landmarks_json IS NULL',
                (
                    json.dumps(item['landmarks']),
                    item['landmark_model'],
                    item['face_id'],
                ),
            )
            landmark_updates += max(0, int(cursor.rowcount))
            cursor = connection.execute(
                'INSERT OR IGNORE INTO face_embedding_artifacts '
                '(face_id, model, model_version, dim, alignment, storage_path, '
                'vector_checksum, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    item['face_id'],
                    model,
                    model_version,
                    512,
                    alignment,
                    item['storage_path'],
                    item['vector_checksum'],
                    'shadow',
                ),
            )
            inserted += max(0, int(cursor.rowcount))
        connection.commit()
        return {
            'requested_records': len(prepared),
            'inserted_artifacts': inserted,
            'existing_artifacts': len(prepared) - inserted,
            'landmark_rows_filled': landmark_updates,
            'new_files': len(created_paths),
            'model': model,
            'model_version': model_version,
            'alignment': alignment,
            'status': 'shadow',
            'active_embedding_paths_changed': 0,
            'assignments_changed': 0,
            'labels_changed': 0,
            'tasks_changed': 0,
        }
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        for path in reversed(created_paths):
            try:
                path.unlink()
            except OSError:
                pass
        raise
    finally:
        connection.close()


def main() -> int:
    args = _parse_args()
    if args.persist_shadow and not args.output:
        raise ValueError('--output is required with --persist-shadow')
    os.environ['CUDA_VISIBLE_DEVICES'] = args.cuda_visible_devices
    os.environ.setdefault('ORT_CUDA_DEVICE_ID', '0')

    backend_root = Path(__file__).resolve().parents[1] / 'backend'
    sys.path.insert(0, str(backend_root))
    from app.face_alignment import align_face_112
    from app.face_detection_service import InsightFaceDetectionProvider
    from app.image_utils import safe_exif_transpose

    database = args.database.resolve()
    connection = sqlite3.connect(
        f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True
    )
    connection.execute('PRAGMA query_only=ON')
    try:
        grouped: dict[int, list[dict]] = defaultdict(list)
        rows = connection.execute(
            "SELECT f.id, f.person_id, a.path, f.bbox_x, f.bbox_y, f.bbox_w, "
            "f.bbox_h, f.embedding_path FROM face_detections f "
            "JOIN assets a ON a.id = f.asset_id "
            "WHERE f.person_id IS NOT NULL AND f.label_source = 'manual' "
            "AND f.embedding_path IS NOT NULL ORDER BY f.person_id, f.id"
        )
        for face_id, person_id, asset_path, x, y, w, h, embedding_path in rows:
            vector = _load_vector(str(embedding_path), args.data_root)
            if vector is None:
                continue
            grouped[int(person_id)].append(
                {
                    'face_id': int(face_id),
                    'person_id': int(person_id),
                    'asset_path': str(asset_path),
                    'bbox': (float(x), float(y), float(w), float(h)),
                    'current': vector,
                }
            )
    finally:
        connection.close()

    eligible = [
        (person_id, rows)
        for person_id, rows in grouped.items()
        if len(rows) >= args.faces_per_person
    ]
    eligible.sort(key=lambda item: (-len(item[1]), item[0]))
    selected = [
        row
        for _person_id, rows in eligible[: args.people]
        for row in _pick_evenly(rows, args.faces_per_person)
    ]
    if not selected:
        raise RuntimeError('no eligible manual 512-d face groups found')

    detector = InsightFaceDetectionProvider('cuda')
    model_path = args.lvface_dir / 'models' / args.model_name
    helper = Path(__file__).with_name('lvface-batch-infer.py')
    failures = Counter()
    records: list[dict] = []

    with tempfile.TemporaryDirectory(prefix='photohouse-face-shadow-') as temp_value:
        temp_root = Path(temp_value)
        manifest_items = []
        detector_model = type(detector).__name__
        for index, row in enumerate(selected):
            source_path = Path(row['asset_path'])
            if not source_path.exists():
                failures['missing_source'] += 1
                continue
            try:
                with Image.open(source_path) as raw:
                    upright = safe_exif_transpose(raw).convert('RGB')
                    detections = detector.detect(upright)
                    candidates = [
                        (_iou(row['bbox'], (d.x, d.y, d.w, d.h)), d)
                        for d in detections
                        if d.landmarks is not None and len(d.landmarks) == 5
                    ]
                    if not candidates:
                        failures['no_landmarks'] += 1
                        continue
                    match_score, match = max(candidates, key=lambda item: item[0])
                    if match_score < args.match_iou:
                        failures['iou_below_threshold'] += 1
                        continue
                    aligned = align_face_112(upright, match.landmarks)
                    aligned_path = temp_root / f'{index}.png'
                    aligned.save(aligned_path, 'PNG')
            except Exception:
                failures['image_or_detection_error'] += 1
                continue
            record = {
                'anonymous_id': str(index),
                'face_id': row['face_id'],
                'person_id': row['person_id'],
                'current': row['current'],
                'landmarks': [
                    [float(x), float(y)] for x, y in match.landmarks
                ],
                'landmark_model': detector_model,
                'aligned_path': aligned_path,
            }
            records.append(record)
            manifest_items.append({'id': str(index), 'path': str(aligned_path)})

        manifest_path = temp_root / 'manifest.json'
        if not manifest_items:
            raise RuntimeError('none of the selected faces could be landmark-aligned')
        manifest_path.write_text(
            json.dumps({'items': manifest_items}), encoding='utf-8'
        )
        environment = os.environ.copy()
        try:
            import torch

            torch_lib = Path(torch.__file__).parent / 'lib'
            if torch_lib.is_dir():
                environment['PATH'] = str(torch_lib) + os.pathsep + environment.get('PATH', '')
        except Exception:
            pass
        process = subprocess.run(
            [
                str(args.lvface_python),
                str(helper),
                '--lvface-dir',
                str(args.lvface_dir),
                '--model',
                str(model_path),
                '--manifest',
                str(manifest_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
            env=environment,
        )
        batch = json.loads(process.stdout)

        if args.persist_shadow:
            for record in records:
                record['aligned_png_bytes'] = record['aligned_path'].read_bytes()

    usable_records = []
    for record in records:
        raw_aligned = batch['embeddings'].get(record['anonymous_id'])
        if raw_aligned is None:
            continue
        aligned = np.asarray(raw_aligned, dtype='float32').reshape(-1)
        if aligned.size != 512:
            failures['unexpected_embedding_dimension'] += 1
            continue
        record['aligned'] = aligned
        usable_records.append(record)

    report = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'mode': (
            'persisted versioned shadow artifacts; active paths and assignments unchanged'
            if args.persist_shadow
            else 'immutable database; temporary aligned crops; no writes'
        ),
        'requested': len(selected),
        'aligned_and_embedded': len(usable_records),
        'people_represented': len({row['person_id'] for row in usable_records}),
        'failures': dict(sorted(failures.items())),
        'model': args.model_name,
        'model_dimension': batch['dimension'],
        'inference_device': batch['device'],
        'execution_providers': batch['providers'],
        'current_unaligned_512': _evaluate(usable_records, 'current'),
        'shadow_aligned_512': _evaluate(usable_records, 'aligned'),
    }
    if args.persist_shadow:
        report['persistence'] = _persist_shadow_artifacts(
            database,
            args.data_root.resolve(),
            usable_records,
            model=args.model_name,
            model_version='lvface-b-glint360k-aligned-d512-v1',
        )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + '\n', encoding='utf-8')
    print(rendered)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
