"""Member uploads: bounded bytes into a per-member incoming folder, in no library.

An accepted upload writes an `assets` row and an `access_uploads` provenance row, and
deliberately **no** `access_asset_libraries` row. The photo is therefore in no library and is
invisible to every member until an operator promotes and assigns it.

The incoming root must sit **outside** every configured original root. That is what makes an
unassigned upload unservable by construction rather than by an authorization decision: the
media route resolves an original from the stored path and requires it to sit under a configured
root, so bytes here are unreachable even if a policy check were wrong.

No image library is imported. Dimensions come from a bounded header parse, which is all the
pixel cap and the asset row need, and which keeps this module free of the decoder that a
decompression bomb would target.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import struct

from .service import AccessDenied

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 64 * 1024 * 1024
MAX_ORIGINAL_NAME = 200
BATCH_PATTERN = re.compile(r'[0-9a-f]{32}')

# Leading bytes decide the type. The declared filename is advisory and never selects it.
SIGNATURES = ((b'\xff\xd8\xff', 'image/jpeg', '.jpg'),
              (b'\x89PNG\r\n\x1a\n', 'image/png', '.png'))


def sniff(data: bytes):
    """Return (mime, suffix) from the leading bytes, or refuse."""
    if not isinstance(data, bytes) or not data:
        raise AccessDenied('Access denied')
    for magic, mime, suffix in SIGNATURES:
        if data.startswith(magic):
            return mime, suffix
    raise AccessDenied('Access denied')


def _png_dimensions(data):
    # 8-byte signature, 4-byte length, 'IHDR', then width and height as big-endian u32.
    if len(data) < 24 or data[12:16] != b'IHDR':
        return None
    width, height = struct.unpack('>II', data[16:24])
    return width, height


def _jpeg_dimensions(data):
    # Walk the segment chain to a start-of-frame. Bounded: a malformed length cannot loop
    # forever because every step must advance by at least the two length bytes.
    index, end = 2, len(data)
    while index + 9 <= end:
        if data[index] != 0xFF:
            return None
        marker = data[index + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        length = struct.unpack('>H', data[index + 2:index + 4])[0]
        if length < 2 or index + 2 + length > end:
            return None
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height, width = struct.unpack('>HH', data[index + 5:index + 9])
            return width, height
        index += 2 + length
    return None


def dimensions(data: bytes, mime: str):
    """Bounded header parse; None when the header is unreadable."""
    return _png_dimensions(data) if mime == 'image/png' else _jpeg_dimensions(data)


@dataclass(frozen=True)
class UploadRuntime:
    """Explicit roots only; construction must not stat anything or read settings.

    The incoming root is required to sit **outside** every original root, and that is checked
    here rather than trusted to the caller. It is what makes an unassigned upload unservable by
    construction: the media route resolves an original from the stored path and requires it to
    sit under a configured original root, so bytes here are unreachable even if a policy check
    were later wrong.
    """

    access: object
    incoming_root: Path
    original_roots: tuple[Path, ...]

    def __post_init__(self):
        if not isinstance(self.incoming_root, Path) or not self.incoming_root.is_absolute():
            raise ValueError('Explicit absolute incoming root required')
        if not self.original_roots or any(not isinstance(p, Path) or not p.is_absolute()
                                          for p in self.original_roots):
            raise ValueError('Explicit absolute original roots required')
        incoming = self.incoming_root.resolve()
        for root in self.original_roots:
            resolved = root.resolve()
            if incoming.is_relative_to(resolved) or resolved.is_relative_to(incoming):
                raise ValueError('The incoming root must sit outside every original root')

    def store(self, token, data, filename, batch):
        """Accept one upload and return its public result.

        The file is written **outside** the write transaction, so a 25 MiB write never holds
        the SQLite write lock, and **before** the rows, so a database failure leaves an orphan
        file in the incoming folder rather than a row pointing at a file that does not exist.
        An orphan is reviewable; a dangling row is not. The capability is re-checked inside
        the write transaction, so a revocation during the write is still honoured.
        """
        from .service import AccessService

        access = self.access
        if not isinstance(data, bytes) or not data or len(data) > MAX_UPLOAD_BYTES:
            raise AccessDenied('Access denied')
        if not isinstance(filename, str) or not filename or len(filename) > MAX_ORIGINAL_NAME:
            raise AccessDenied('Access denied')
        if not isinstance(batch, str) or BATCH_PATTERN.fullmatch(batch) is None:
            raise AccessDenied('Access denied')
        mime, suffix = sniff(data)
        size = dimensions(data, mime)
        if size is None or size[0] < 1 or size[1] < 1 or size[0] * size[1] > MAX_PIXELS:
            raise AccessDenied('Access denied')
        digest = hashlib.sha256(data).hexdigest()

        with access.connection_factory() as connection:
            service = AccessService(connection, clock=access.clock)
            _account_id, label = service.uploader(token)

        directory = self.incoming_root / label / batch
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (digest + suffix)
        if not path.exists():
            # O_EXCL so a racing writer cannot be silently overwritten, and 0600 so the bytes
            # are not group or world readable while they await review.
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, 'wb') as handle:
                    handle.write(data)
            except BaseException:
                path.unlink(missing_ok=True)
                raise

        with access.connection_factory() as connection:
            service = AccessService(connection, clock=access.clock)
            return service.record_upload(token, label, batch, path, filename,
                                         digest, len(data), mime, size)
