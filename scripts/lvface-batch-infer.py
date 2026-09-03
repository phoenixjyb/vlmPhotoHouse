#!/usr/bin/env python3
"""Batch LVFace inference helper intended for the isolated LVFace Python env."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lvface-dir', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--cpu', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    sys.path.insert(0, str(args.lvface_dir / 'src'))
    from inference_onnx import LVFaceONNXInferencer

    requested_device = 'cpu' if args.cpu else 'cuda'
    actual_device = requested_device
    try:
        inferencer = LVFaceONNXInferencer(str(args.model), use_gpu=not args.cpu)
    except Exception:
        if args.cpu:
            raise
        inferencer = LVFaceONNXInferencer(str(args.model), use_gpu=False)
        actual_device = 'cpu-fallback'

    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    embeddings: dict[str, list[float]] = {}
    for item in manifest['items']:
        vector = np.asarray(
            inferencer.infer_from_image(str(item['path'])), dtype='float32'
        ).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if norm <= 0:
            raise RuntimeError(f"zero-norm embedding for item {item['id']}")
        embeddings[str(item['id'])] = (vector / norm).tolist()

    print(
        json.dumps(
            {
                'device': actual_device,
                'providers': inferencer.ort_session.get_providers(),
                'dimension': len(next(iter(embeddings.values()))) if embeddings else 0,
                'embeddings': embeddings,
            }
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
