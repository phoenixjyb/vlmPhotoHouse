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
import secrets
import stat
import struct

from .service import AccessDenied

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 64 * 1024 * 1024
MAX_ORIGINAL_NAME = 200
BATCH_PATTERN = re.compile(r'[0-9a-f]{32}')


def _identity(record):
    return (record.st_dev, record.st_ino, record.st_size, record.st_mtime_ns)


def _verify_candidate(path, data):
    """A retry may reuse complete bytes, never a symlink or a partial old write."""
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size != len(data):
        raise OSError('Upload candidate is not reusable')
    with path.open('rb') as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise OSError('Upload candidate changed')
        digest = hashlib.sha256()
        remaining = len(data)
        while remaining:
            chunk = stream.read(min(65536, remaining))
            if not chunk:
                raise OSError('Upload candidate is incomplete')
            digest.update(chunk)
            remaining -= len(chunk)
        if stream.read(1) or digest.digest() != hashlib.sha256(data).digest():
            raise OSError('Upload candidate differs')
    if _identity(path.lstat()) != _identity(before):
        raise OSError('Upload candidate changed')


def _stage_candidate(root, data):
    """Complete the bounded bulk write before taking the SQLite writer lock."""
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / ('.upload-' + secrets.token_hex(16) + '.pending')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        temporary.unlink()
        raise
    return temporary


def _publish_candidate(temporary, path, data):
    """Called under the writer lock also held by promotion and unassignment."""
    if path.parent.resolve() != path.parent:
        raise OSError('Upload destination requires review')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.resolve() != path.parent:
        raise OSError('Upload destination changed')
    try:
        os.link(temporary, path)  # Complete bytes become visible, with no overwrite.
    except FileExistsError:
        _verify_candidate(path, data)


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

        Bulk bytes are staged outside the write transaction. Under the SQLite writer
        lock, select authoritative provenance and publish a complete file before recording
        its row. Promotion uses the same lock, so neither its commit nor rollback can race
        publication. A DB failure can still leave a reviewable final orphan, never a dangling
        row. Capability is re-checked after staging and inside the recording transaction.
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

        temporary = _stage_candidate(self.incoming_root, data)
        try:
            with access.connection_factory() as connection:
                service = AccessService(connection, clock=access.clock)
                with service._transaction(write=True):
                    existing = service._incoming_upload(token, digest)
                    if existing:
                        # Use stored provenance even after a name/batch change. Never
                        # create a second final file merely to discard it afterwards.
                        path = Path(existing['path'])
                        expected = self.incoming_root / existing['incoming_label'] / existing['batch'] / (digest + suffix)
                        if (path != expected or not path.is_relative_to(self.incoming_root)
                                or '..' in path.parts or existing['bytes'] != len(data)
                                or existing['mime'] != mime
                                or (existing['width'], existing['height']) != size):
                            raise OSError('Stored upload path requires review')
                    else:
                        path = self.incoming_root / label / batch / (digest + suffix)
                    _publish_candidate(temporary, path, data)
                    result = service._record_upload_in_transaction(token, label, batch, path,
                        filename, digest, len(data), mime, size)
            return result
        finally:
            # Only this request's unique staging name is removed. A final file left
            # after DB failure remains reviewable, and canonical files are never deleted.
            temporary.unlink()

    def history(self, token, *, page=1):
        """Own receipts only, with current library access checked in one snapshot.

        This read never stats incoming files, prepares media or retries jobs. Receipt
        acceptance and library visibility are separate facts; no processing state is
        inferred from a missing thumbnail or caption.
        """
        from .service import AccessService, AccessDenied
        from .transport import TransportError

        if type(page) is not int or not 1 <= page <= 100000:
            raise ValueError('Invalid page')
        with self.access.connection_factory() as connection:
            service = AccessService(connection, clock=self.access.clock)
            with service._transaction():
                account = service._session(token)['account_id']
                if not service._may_submit(account):
                    raise AccessDenied('Access denied')
                total = connection.execute('SELECT count(*) FROM access_uploads WHERE account_id=?',
                                           (account,)).fetchone()[0]
                if not 0 <= total <= 2147483647:
                    raise TransportError(503, 'Upload history unavailable')
                rows = connection.execute('''SELECT u.asset_id,u.created_at,u.bytes,u.state,
                    a.status,a.mime,scope.library_id FROM access_uploads u
                    JOIN assets a ON a.id=u.asset_id
                    LEFT JOIN access_asset_libraries scope ON scope.asset_id=a.id
                    WHERE u.account_id=? ORDER BY u.id DESC LIMIT 10 OFFSET ?''',
                    (account, (page-1)*10)).fetchall()
                items = []
                for asset, created, size, receipt, status, mime, mapped in rows:
                    if (type(asset) is not int or not 1 <= asset <= 2**63-1
                            or type(created) is not int or not 0 <= created <= 253402300799
                            or type(size) is not int or not 1 <= size <= MAX_UPLOAD_BYTES
                            or mime not in {'image/jpeg', 'image/png'}):
                        raise TransportError(503, 'Upload history unavailable')
                    state, library = 'unavailable', None
                    if status in (None, 'active'):
                        if receipt == 'incoming' and mapped is None:
                            state = 'awaiting_review'
                        elif receipt == 'assigned' and mapped is not None:
                            try:
                                service._require(token, mapped, 'library.read')
                                state, library = 'available', mapped
                            except AccessDenied:
                                pass
                    items.append(dict(asset_id=str(asset), created_at=created, bytes=size,
                                      kind='image', state=state, library_id=library))
                return dict(page=page, page_size=10, total=total, items=items)
