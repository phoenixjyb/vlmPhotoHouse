"""Shared identities and path rules for versioned face-embedding artifacts."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np


LVFACE_B_GLINT360K_NATIVE_512 = "lvface-b-glint360k-aligned-d512-v1"
LEGACY_UNVERSIONED_128 = "legacy-unversioned-d128"
LEGACY_UNVERSIONED_512 = "legacy-unversioned-d512"

_SAFE_VERSION = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")


def _validated_version(version: str) -> str:
    normalized = version.strip().lower()
    if not _SAFE_VERSION.fullmatch(normalized):
        raise ValueError(f"unsafe embedding version: {version!r}")
    return normalized


def face_embedding_path(derived_root: Path, version: str, face_id: int) -> Path:
    if face_id <= 0:
        raise ValueError("face_id must be positive")
    return (
        Path(derived_root)
        / "face_embeddings"
        / _validated_version(version)
        / f"{face_id}.npy"
    )


def person_embedding_path(
    derived_root: Path, version: str, person_id: int
) -> Path:
    if person_id <= 0:
        raise ValueError("person_id must be positive")
    return (
        Path(derived_root)
        / "person_embeddings"
        / _validated_version(version)
        / f"{person_id}.npy"
    )


def load_normalized_embedding(path: Path, expected_dim: int) -> np.ndarray:
    vector = np.asarray(
        np.load(path, mmap_mode="r", allow_pickle=False), dtype="float32"
    ).reshape(-1)
    if int(vector.size) != expected_dim:
        raise ValueError(
            f"embedding dimension mismatch: expected {expected_dim}, got {vector.size}"
        )
    norm = float(np.linalg.norm(vector))
    if norm <= 0:
        raise ValueError("embedding vector has zero norm")
    return vector / norm
