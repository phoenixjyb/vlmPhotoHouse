#!/usr/bin/env python3
"""One-shot strict CUDA inference child for approved face processing.

This module intentionally has no database, network, worker-loop, or fallback
provider integration. The parent owns authorization and physical GPU selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
from typing import Any

from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

MAX_INPUT_BYTES = 256 * 1024**2
MAX_PIXELS = 64_000_000
MAX_FACES = 64
CROP_SIZE = 256
VECTOR_DIM = 512
MAX_RECEIPT_BYTES = 64 * 1024


class Refused(ValueError):
    """Invalid or unsafe child invocation or inference result."""


def _path(value: str | Path, *, directory: bool = False) -> Path:
    raw = str(value)
    path = Path(value)
    if (not path.is_absolute() or path == Path(path.anchor) or '..' in path.parts
            or len(raw) > 4096 or any(ord(ch) < 32 for ch in raw)
            or path.anchor.startswith(('//', '\\\\'))):
        raise Refused('explicit_absolute_path_required')
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or path.resolve(strict=True) != path:
            raise Refused('symlink_path_refused')
    except OSError as exc:
        raise Refused('path_unavailable') from exc
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise Refused('directory_required')
    elif not stat.S_ISREG(info.st_mode):
        raise Refused('regular_file_required')
    return path


def _read_image(path: Path) -> tuple[Image.Image, str]:
    before = path.stat(follow_symlinks=False)
    pin = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    if not 0 < before.st_size <= MAX_INPUT_BYTES:
        raise Refused('input_size_out_of_bounds')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != pin:
            raise Refused('input_changed')
        while chunk := stream.read(4 * 1024**2):
            digest.update(chunk)
        stream.seek(0)
        previous_pixel_limit = Image.MAX_IMAGE_PIXELS
        # Inspect declared dimensions ourselves before decoding so our bounded
        # rejection reason does not depend on Pillow's lower warning threshold.
        Image.MAX_IMAGE_PIXELS = None
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        try:
            try:
                image = Image.open(stream)
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                raise Refused('input_image_invalid_or_too_large') from exc
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                raise Refused('input_pixel_count_out_of_bounds')
            try:
                image.load()
                image = ImageOps.exif_transpose(image).convert('RGB')
            except (OSError, Image.DecompressionBombError) as exc:
                raise Refused('input_image_invalid_or_too_large') from exc
        finally:
            Image.MAX_IMAGE_PIXELS = previous_pixel_limit
    after = path.stat(follow_symlinks=False)
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != pin:
        raise Refused('input_changed')
    return image, digest.hexdigest()


def _cuda_provider(provider: Any) -> None:
    effective = getattr(provider, 'effective_execution_provider', None)
    if effective is None:
        # LVFace exposes the complete ONNX Runtime provider list as a string.
        effective = getattr(provider, 'effective_provider', None)
    if isinstance(effective, str):
        effective = effective.split(',')
    if not effective or effective[0] != 'CUDAExecutionProvider':
        raise Refused('cuda_execution_provider_not_effective')
    requested = getattr(provider, 'requested_device', 'cuda')
    if requested != 'cuda':
        raise Refused('logical_cuda_device_required')


def _finite_number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise Refused('invalid_inference_value') from exc
    if not math.isfinite(number):
        raise Refused('non_finite_inference_value')
    return number


def _detect(image: Image.Image, digest: str, stage: Path, receipt: Path,
            *, provider: Any, model_root: Path) -> dict[str, Any]:
    _cuda_provider(provider)
    detected = provider.detect(image)
    if len(detected) > MAX_FACES:
        raise Refused('face_count_out_of_bounds')
    faces = []
    for index, face in enumerate(detected):
        x, y, width, height = (_finite_number(getattr(face, key))
                               for key in ('x', 'y', 'w', 'h'))
        if width <= 0 or height <= 0:
            raise Refused('invalid_face_box')
        left = max(0, min(image.width, math.floor(x)))
        top = max(0, min(image.height, math.floor(y)))
        right = max(0, min(image.width, math.ceil(x + width)))
        bottom = max(0, min(image.height, math.ceil(y + height)))
        if right <= left or bottom <= top:
            raise Refused('face_box_outside_image')
        crop_name = f'face-{index:02d}.jpg'
        crop_path = stage / crop_name
        if crop_path.exists() or crop_path.is_symlink():
            raise Refused('output_already_exists')
        crop = image.crop((left, top, right, bottom)).resize((CROP_SIZE, CROP_SIZE), Image.Resampling.LANCZOS)
        crop.save(crop_path, format='JPEG', quality=90, optimize=False)
        landmarks = getattr(face, 'landmarks', None)
        points = None
        if landmarks is not None:
            if len(landmarks) > 5:
                raise Refused('landmark_count_out_of_bounds')
            points = [[_finite_number(p[0]), _finite_number(p[1])] for p in landmarks]
        faces.append({'crop': crop_name, 'bbox': [left, top, right - left, bottom - top],
                      'landmarks': points})
    return {
        'operation': 'detect', 'provider': 'CUDAExecutionProvider',
        'effective_device': 'cuda:0', 'input_sha256': digest,
        'model_root': str(model_root), 'faces': faces,
        'outputs': [face['crop'] for face in faces],
    }


def _embed(image: Image.Image, digest: str, stage: Path,
           *, provider: Any, model_path: Path) -> dict[str, Any]:
    _cuda_provider(provider)
    import numpy as np

    vector = np.asarray(provider.embed_face(image), dtype=np.float32)
    if vector.shape != (VECTOR_DIM,) or not np.isfinite(vector).all():
        raise Refused('embedding_shape_or_values_invalid')
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 0:
        raise Refused('embedding_norm_invalid')
    vector = np.asarray(vector / norm, dtype=np.float32)
    if not np.isfinite(vector).all():
        raise Refused('embedding_values_invalid')
    output = stage / 'embedding.npy'
    if output.exists() or output.is_symlink():
        raise Refused('output_already_exists')
    np.save(output, vector, allow_pickle=False)
    return {
        'operation': 'embed', 'provider': 'CUDAExecutionProvider',
        'effective_device': 'cuda', 'input_sha256': digest,
        'model_path': str(model_path), 'dimension': VECTOR_DIM,
        'norm': float(np.linalg.norm(vector)), 'outputs': ['embedding.npy'],
    }


def run(operation: str, image_path: str | Path | None, stage_path: str | Path,
        receipt_path: str | Path, *, insightface_root: str | Path | None = None,
        model_path: str | Path | None = None, detector: Any = None,
        embedder: Any = None) -> dict[str, Any]:
    """Run one operation. Injected providers are solely for isolated CPU tests."""
    if operation not in ('detect', 'embed', 'probe'):
        raise Refused('unsupported_operation')
    stage = _path(stage_path, directory=True)
    image_file = _path(image_path) if image_path is not None else None
    receipt = Path(receipt_path)
    if not receipt.is_absolute() or '..' in receipt.parts:
        raise Refused('receipt_must_be_inside_stage')
    try:
        receipt = receipt.resolve(strict=False)
        receipt.relative_to(stage)
    except (OSError, ValueError) as exc:
        raise Refused('receipt_must_be_inside_stage') from exc
    if receipt == stage or receipt.exists() or receipt.is_symlink():
        raise Refused('receipt_must_be_new_file')
    if operation == 'probe':
        if image_file is not None or insightface_root is None or model_path is None:
            raise Refused('probe_requires_models_and_no_family_image')
        root = _path(insightface_root, directory=True)
        checkpoint = _path(model_path)
        os.environ['INSIGHTFACE_ROOT'] = str(root)
        if detector is None:
            from app.face_detection_service import InsightFaceDetectionProvider
            detector = InsightFaceDetectionProvider('cuda', strict=True)
        if embedder is None:
            from app.face_embedding_service import LVFaceEmbeddingProvider
            embedder = LVFaceEmbeddingProvider(str(checkpoint), 'cuda', VECTOR_DIM, strict=True)
        _cuda_provider(detector)
        _cuda_provider(embedder)
        import numpy as np
        synthetic = Image.new('RGB', (CROP_SIZE, CROP_SIZE), color=(96, 128, 160))
        detector.detect(synthetic)
        probe_vector = np.asarray(embedder.embed_face(synthetic), dtype=np.float32)
        if probe_vector.shape != (VECTOR_DIM,) or not np.isfinite(probe_vector).all():
            raise Refused('probe_embedding_invalid')
        manifest = {
            'operation': 'probe', 'provider': 'CUDAExecutionProvider',
            'effective_device': 'cuda:0', 'embedding_device': 'cuda',
            'outputs': [],
        }
    else:
        if image_file is None:
            raise Refused('image_required')
        image, digest = _read_image(image_file)

        if operation == 'detect':
            if model_path is not None or (detector is None and insightface_root is None):
                raise Refused('insightface_root_required_for_detect')
            root = _path(insightface_root, directory=True) if insightface_root is not None else stage
            if detector is None:
                os.environ['INSIGHTFACE_ROOT'] = str(root)
                from app.face_detection_service import InsightFaceDetectionProvider
                detector = InsightFaceDetectionProvider('cuda', strict=True)
            manifest = _detect(image, digest, stage, receipt, provider=detector, model_root=root)
        else:
            if insightface_root is not None or (embedder is None and model_path is None):
                raise Refused('model_path_required_for_embed')
            checkpoint = _path(model_path) if model_path is not None else stage
            if embedder is None:
                from app.face_embedding_service import LVFaceEmbeddingProvider
                embedder = LVFaceEmbeddingProvider(str(checkpoint), 'cuda', VECTOR_DIM, strict=True)
            manifest = _embed(image, digest, stage, provider=embedder, model_path=checkpoint)

    payload = json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(payload) > MAX_RECEIPT_BYTES:
        raise Refused('receipt_too_large')
    with receipt.open('xb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('detect', 'embed', 'probe'))
    parser.add_argument('--image')
    parser.add_argument('--stage', required=True)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--insightface-root')
    parser.add_argument('--model-path')
    args = parser.parse_args(argv)
    try:
        run(args.operation, args.image, args.stage, args.receipt,
            insightface_root=args.insightface_root, model_path=args.model_path)
    except Exception as exc:
        # Keep errors bounded and avoid echoing local paths or provider internals.
        reason = exc.args[0] if isinstance(exc, Refused) and exc.args else 'inference_failed'
        print(json.dumps({'error': str(reason)[:96]}, separators=(',', ':')), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
