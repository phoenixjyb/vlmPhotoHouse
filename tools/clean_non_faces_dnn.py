#!/usr/bin/env python3
"""
Clean false face detections using InsightFace (SCRFD) verification on stored crops.

Default safety behavior:
- Only checks unassigned faces.
- Protects faces attached to named persons.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Remove non-face detections using DNN verification")
    p.add_argument("--db", type=Path, default=None, help="Path to metadata.sqlite/app.db")
    p.add_argument("--derived-root", type=Path, default=None, help="Path to derived directory")
    p.add_argument("--config", type=Path, default=Path("config/drive_e_paths.json"))
    p.add_argument("--model-pack", default="buffalo_l", help="InsightFace model pack")
    p.add_argument("--det-size", type=int, default=640, help="Detector input size")
    p.add_argument("--min-score", type=float, default=0.45, help="Minimum detector score on crop")
    p.add_argument("--limit", type=int, default=0, help="Max rows to evaluate (0 = all)")
    p.add_argument("--batch-commit", type=int, default=250, help="Commit cadence for deletes")
    p.add_argument("--include-assigned", action="store_true", help="Also verify assigned faces")
    p.add_argument("--no-protect-named", action="store_true", help="Allow deleting faces assigned to named people")
    p.add_argument("--no-prune-empty-unnamed", action="store_true", help="Do not delete unnamed persons with 0 faces")
    p.add_argument("--cpu", action="store_true", help="Force CPU provider")
    p.add_argument("--dry-run", action="store_true", help="Report only, do not delete rows/files")
    return p.parse_args()


def load_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.db and args.derived_root:
        return args.db, args.derived_root

    if args.config.exists():
        with args.config.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        db = Path(args.db or cfg.get("databases", {}).get("metadata", "E:/VLM_DATA/databases/metadata.sqlite"))
        derived = Path(args.derived_root or cfg.get("derived", {}).get("captions", "E:/VLM_DATA/derived/captions")).parent
        return db, derived

    db = Path(args.db or "E:/VLM_DATA/databases/metadata.sqlite")
    derived = Path(args.derived_root or "E:/VLM_DATA/derived")
    return db, derived


def init_detector(model_pack: str, det_size: int, force_cpu: bool):
    from insightface.app import FaceAnalysis  # type: ignore
    import onnxruntime as ort  # type: ignore

    providers = ["CPUExecutionProvider"]
    ctx_id = -1
    if not force_cpu and "CUDAExecutionProvider" in ort.get_available_providers():
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        ctx_id = 0

    app = FaceAnalysis(name=model_pack, allowed_modules=["detection"], providers=providers)
    app.prepare(ctx_id=ctx_id, det_size=(det_size, det_size))
    return app, providers


def has_face(detector, crop_path: Path, min_score: float) -> bool:
    if not crop_path.exists():
        return False
    with Image.open(crop_path) as im:
        rgb = np.asarray(im.convert("RGB"))
    bgr = rgb[:, :, ::-1]
    faces = detector.get(bgr)
    if not faces:
        return False
    for f in faces:
        score = float(getattr(f, "det_score", 1.0))
        if score >= min_score:
            return True
    return False


def iter_faces(conn: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    q = """
    SELECT fd.id, fd.person_id, fd.embedding_path, p.display_name
    FROM face_detections fd
    LEFT JOIN persons p ON p.id = fd.person_id
    ORDER BY fd.id
    """
    cur = conn.execute(q)
    for row in cur:
        yield row


def main() -> int:
    args = parse_args()
    db_path, derived_root = load_paths(args)
    protect_named = not args.no_protect_named
    prune_empty_unnamed = not args.no_prune_empty_unnamed

    if not db_path.exists():
        print(f"DB not found: {db_path}")
        return 1

    print("clean_non_faces_dnn")
    print(f"db={db_path}")
    print(f"derived_root={derived_root}")
    print(f"min_score={args.min_score} det_size={args.det_size} model_pack={args.model_pack}")
    print(f"include_assigned={args.include_assigned} protect_named={protect_named} dry_run={args.dry_run}")

    detector, providers = init_detector(args.model_pack, args.det_size, args.cpu)
    print(f"detector_providers={providers}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    total = 0
    checked = 0
    skipped_assigned = 0
    skipped_named = 0
    missing_crop = 0
    deleted = 0
    kept = 0
    affected_person_ids: set[int] = set()
    start = time.time()

    for row in iter_faces(conn):
        total += 1
        if args.limit and checked >= args.limit:
            break

        face_id = int(row["id"])
        person_id = row["person_id"]
        display_name = (row["display_name"] or "").strip() if row["display_name"] is not None else ""
        emb_path = row["embedding_path"]

        if (not args.include_assigned) and person_id is not None:
            skipped_assigned += 1
            continue
        if protect_named and display_name:
            skipped_named += 1
            continue

        checked += 1
        crop_path = derived_root / "faces" / "256" / f"{face_id}.jpg"
        valid = has_face(detector, crop_path, args.min_score)
        if valid:
            kept += 1
        else:
            if not crop_path.exists():
                missing_crop += 1
            if not args.dry_run:
                cur.execute("DELETE FROM face_detections WHERE id=?", (face_id,))
                # Remove crop files across all configured sizes.
                faces_root = derived_root / "faces"
                if faces_root.exists():
                    for p in faces_root.glob(f"*/{face_id}.jpg"):
                        try:
                            p.unlink(missing_ok=True)
                        except Exception:
                            pass
                if emb_path:
                    try:
                        Path(str(emb_path)).unlink(missing_ok=True)
                    except Exception:
                        pass
            deleted += 1
            if person_id is not None:
                affected_person_ids.add(int(person_id))

        if checked % args.batch_commit == 0:
            elapsed = time.time() - start
            rate = checked / elapsed if elapsed > 0 else 0.0
            print(f"checked={checked} kept={kept} deleted={deleted} missing_crop={missing_crop} rate={rate:.1f}/s")
            if not args.dry_run:
                conn.commit()

    if not args.dry_run:
        if affected_person_ids:
            for pid in sorted(affected_person_ids):
                cur.execute(
                    "UPDATE persons SET face_count=(SELECT COUNT(*) FROM face_detections WHERE person_id=?) WHERE id=?",
                    (pid, pid),
                )
        if prune_empty_unnamed:
            cur.execute(
                """
                DELETE FROM persons
                WHERE (display_name IS NULL OR TRIM(display_name) = '')
                  AND id IN (
                    SELECT p.id
                    FROM persons p
                    LEFT JOIN face_detections fd ON fd.person_id = p.id
                    GROUP BY p.id
                    HAVING COUNT(fd.id) = 0
                  )
                """
            )
        conn.commit()

    elapsed = time.time() - start
    rate = checked / elapsed if elapsed > 0 else 0.0
    print("done")
    print(f"total_rows={total}")
    print(f"checked={checked} skipped_assigned={skipped_assigned} skipped_named={skipped_named}")
    print(f"kept={kept} deleted={deleted} missing_crop={missing_crop}")
    print(f"affected_person_ids={len(affected_person_ids)}")
    print(f"elapsed_sec={elapsed:.1f} rate={rate:.1f}/s")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
