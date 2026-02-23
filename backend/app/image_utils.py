from __future__ import annotations

from PIL import Image, ImageOps

# EXIF orientation tag id
_ORIENTATION_TAG = 274


def safe_exif_transpose(image: Image.Image) -> Image.Image:
    """Best-effort EXIF orientation correction.

    Some files contain malformed EXIF rational values that make
    ImageOps.exif_transpose() raise during EXIF serialization.
    This helper falls back to a manual orientation transform.
    """
    try:
        return ImageOps.exif_transpose(image)
    except Exception:
        pass

    try:
        orientation = image.getexif().get(_ORIENTATION_TAG)
    except Exception:
        orientation = None

    transpose_enum = Image.Transpose
    method_map = {
        2: transpose_enum.FLIP_LEFT_RIGHT,
        3: transpose_enum.ROTATE_180,
        4: transpose_enum.FLIP_TOP_BOTTOM,
        5: transpose_enum.TRANSPOSE,
        6: transpose_enum.ROTATE_270,
        7: transpose_enum.TRANSVERSE,
        8: transpose_enum.ROTATE_90,
    }

    method = method_map.get(orientation)
    if method is None:
        return image

    try:
        return image.transpose(method)
    except Exception:
        return image

