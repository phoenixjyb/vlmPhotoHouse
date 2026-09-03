"""Five-point similarity alignment for face-recognition inputs."""

from __future__ import annotations

from typing import Sequence

import numpy as np
from PIL import Image


ARCFACE_112_TEMPLATE = np.asarray(
    [
        (38.2946, 51.6963),
        (73.5318, 51.5014),
        (56.0252, 71.7366),
        (41.5493, 92.3655),
        (70.7299, 92.2041),
    ],
    dtype=np.float64,
)


def estimate_similarity_matrix(
    source_landmarks: Sequence[Sequence[float]],
    target_landmarks: np.ndarray = ARCFACE_112_TEMPLATE,
) -> np.ndarray:
    """Return a 3x3 similarity matrix mapping source points to target points."""
    source = np.asarray(source_landmarks, dtype=np.float64)
    target = np.asarray(target_landmarks, dtype=np.float64)
    if source.shape != (5, 2) or target.shape != (5, 2):
        raise ValueError("face alignment requires exactly five 2D landmarks")
    if not np.isfinite(source).all() or not np.isfinite(target).all():
        raise ValueError("face landmarks must contain only finite coordinates")

    design = np.zeros((10, 4), dtype=np.float64)
    values = np.zeros(10, dtype=np.float64)
    for index, ((x, y), (u, v)) in enumerate(zip(source, target)):
        design[index * 2] = (x, -y, 1.0, 0.0)
        design[index * 2 + 1] = (y, x, 0.0, 1.0)
        values[index * 2] = u
        values[index * 2 + 1] = v

    a, b, translate_x, translate_y = np.linalg.lstsq(
        design, values, rcond=None
    )[0]
    matrix = np.asarray(
        [
            (a, -b, translate_x),
            (b, a, translate_y),
            (0.0, 0.0, 1.0),
        ],
        dtype=np.float64,
    )
    if abs(float(np.linalg.det(matrix[:2, :2]))) < 1e-10:
        raise ValueError("face landmarks produce a degenerate alignment")
    return matrix


def align_face_112(
    image: Image.Image,
    landmarks: Sequence[Sequence[float]],
) -> Image.Image:
    """Warp an upright source image to the standard ArcFace 112x112 template."""
    source_to_target = estimate_similarity_matrix(landmarks)
    target_to_source = np.linalg.inv(source_to_target)
    coefficients = tuple(float(value) for value in target_to_source[:2, :].reshape(-1))
    return image.convert("RGB").transform(
        (112, 112),
        Image.Transform.AFFINE,
        coefficients,
        resample=Image.Resampling.BILINEAR,
    )
