"""Library-scoped bytes at legacy URLs, from one shared database/session policy.

Open the file under a short SQLite write reservation after current authorization.
Stream that descriptor, never reopen an authorized path later. Cached derivatives
only: missing previews do not trigger decoding, providers, writes or jobs.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from .service import AccessDenied, AccessService
from .transport import (AccessRoute, PRIVACY_HEADERS, TransportError,
                        credentials_from_request, _runtime, _single)


@dataclass(frozen=True)
class MediaRuntime:
    """Explicit roots only; construction must not stat media or read settings."""
    original_roots: tuple[Path, ...]
    derived_root: Path

    def __post_init__(self):
        if not self.original_roots or any(not isinstance(p, Path) or not p.is_absolute()
                for p in (*self.original_roots, self.derived_root)):
            raise ValueError('Explicit absolute original and derived roots required')

    def open_file(self, access, token, library, object_id, variant, size):
        """Policy, scoped lookup and stat/open share one reserved DB transaction.

        This is the shared service boundary; direct callers cannot bypass policy.
        Do not expose returned paths or replace the opened descriptor with a URL.
        """
        if (type(object_id) is not int or not 1 <= object_id <= 2**63-1
                or variant not in {'original', 'thumbnail', 'crop'}
                or type(size) is not int or not 64 <= size <= 1024):
            raise AccessDenied('Access denied')
        opened = None
        try:
            with access.connection_factory() as connection:
                service = AccessService(connection, clock=access.clock)
                # Serialize membership/account changes through stat/open, including
                # WAL mode. Do not retain this lock while streaming to a client.
                with service._transaction(write=True):
                    service._require(token, library,
                                     'media.original.read' if variant == 'original' else 'library.read')
                    if variant == 'crop':
                        row = service._one('''SELECT a.id, a.path FROM face_detections f
                            JOIN assets a ON a.id=f.asset_id
                            JOIN access_asset_libraries m ON m.asset_id=a.id
                            WHERE f.id=? AND m.library_id=? AND (a.status IS NULL OR a.status='active')''',
                            (object_id, library))
                    elif variant in {'original', 'thumbnail'}:
                        row = service._one('''SELECT a.id, a.path FROM assets a
                            JOIN access_asset_libraries m ON m.asset_id=a.id
                            WHERE a.id=? AND m.library_id=? AND (a.status IS NULL OR a.status='active')''',
                            (object_id, library))
                    else:
                        raise AccessDenied('Access denied')
                    if not row:
                        raise AccessDenied('Access denied')
                    if variant == 'original':
                        path, roots = Path(row['path']), self.original_roots
                    else:
                        folder = 'faces' if variant == 'crop' else 'thumbnails'
                        path = self.derived_root / folder / str(size) / f'{object_id}.jpg'
                        roots = (self.derived_root,)
                    # Every filesystem lookup is after current parent authorization.
                    resolved_roots = tuple(p.resolve(strict=True) for p in roots)
                    resolved = path.resolve(strict=True)
                    if not path.is_absolute() or not any(resolved.is_relative_to(p) for p in resolved_roots):
                        raise AccessDenied('Access denied')
                    flags = (os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_CLOEXEC', 0)
                             | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
                    descriptor = os.open(resolved, flags)
                    try:
                        opened = os.fdopen(descriptor, 'rb')
                    except BaseException:
                        os.close(descriptor)
                        raise
                    info = os.fstat(opened.fileno())
                    current = path.resolve(strict=True)
                    # Pin identity and containment again after open, before reading
                    # any bytes (including Windows where O_NOFOLLOW is unavailable).
                    if (not stat.S_ISREG(info.st_mode) or current != resolved
                            or not any(current.is_relative_to(p) for p in resolved_roots)):
                        raise AccessDenied('Access denied')
                    latest = os.stat(current)
                    if (latest.st_dev, latest.st_ino) != (info.st_dev, info.st_ino):
                        raise AccessDenied('Access denied')
                    extension = resolved.suffix.lower() if variant == 'original' else '.jpg'
            return opened, info, extension
        except BaseException:
            if opened is not None:
                opened.close()
            raise


MIME = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
        '.webp': 'image/webp', '.gif': 'image/gif', '.avif': 'image/avif',
        '.heic': 'image/heic', '.mp4': 'video/mp4', '.mov': 'video/quicktime', '.webm': 'video/webm'}


def byte_range(value, length):
    """Bounded single byte range. Multipart ranges are intentionally unsupported."""
    if len(value) > 100 or not re.fullmatch(r'bytes=[0-9]{0,20}-[0-9]{0,20}', value):
        raise TransportError(400, 'Invalid range')
    start, end = value[6:].split('-')
    if not start and not end:
        raise TransportError(400, 'Invalid range')
    if start:
        lower = int(start)
        upper = min(int(end) + 1, length) if end else length
    else:
        lower, upper = max(0, length - int(end)), length
    if lower >= upper:
        raise TransportError(416, 'Range not satisfiable')
    return lower, upper


class _FileLease:
    """Own a worker-opened descriptor even if its awaiting request is cancelled."""
    def __init__(self):
        self.lock = threading.Lock()
        self.closed = False
        self.handle = None

    def accept(self, result):
        # The worker publishes ownership before returning across the await. A
        # cancelled request has already closed this lease, so late results close
        # in the worker rather than being abandoned with an unobserved future.
        with self.lock:
            if self.closed:
                result[0].close()
            else:
                self.handle = result[0]
        return result

    def close(self):
        with self.lock:
            self.closed = True
            handle, self.handle = self.handle, None
        if handle is not None:
            handle.close()


class AuthorizedMediaResponse(Response):
    def __init__(self, request, token, library, object_id, variant, size, download):
        super().__init__()
        self.request, self.token, self.library = request, token, library
        self.object_id, self.variant, self.size, self.download = object_id, variant, size, download

    async def __call__(self, scope, receive, send):
        opened = None
        lease = _FileLease()
        try:
            try:
                access = _runtime(self.request, allow_query=True)
                media = getattr(self.request.app.state, 'media_runtime', None)
                if not isinstance(media, MediaRuntime):
                    raise TransportError(503, 'Access unavailable')
                # Deferred until response execution: an earlier route check is never
                # retained as permission to open a file after logout or revocation.
                def open_for_response():
                    return lease.accept(media.open_file(access, self.token, self.library,
                        self.object_id, self.variant, self.size))
                opened, info, extension = await run_in_threadpool(open_for_response)
                length = info.st_size
                # Metadata is not a content hash: advertise only a weak validator.
                # Conditional resume conservatively returns the complete response.
                etag = 'W/"' + hashlib.sha256(f'{info.st_mtime_ns}:{length}'.encode()).hexdigest() + '"'
                headers = dict(PRIVACY_HEADERS, **{'Accept-Ranges': 'bytes', 'ETag': etag,
                    'Content-Length': str(length)})
                lower, upper, status = 0, length, 200
                requested, conditional = _single(self.request, 'range'), _single(self.request, 'if-range')
                if requested is not None and conditional is None:
                    try:
                        lower, upper = byte_range(requested, length)
                    except TransportError as exc:
                        if exc.status == 416:
                            exc.content_range = f'bytes */{length}'
                        raise
                    status = 206
                    headers['Content-Range'] = f'bytes {lower}-{upper-1}/{length}'
                    headers['Content-Length'] = str(upper-lower)
                mime = MIME.get(extension, 'application/octet-stream')
                if self.download or mime == 'application/octet-stream':
                    safe_extension = extension if extension in MIME else '.bin'
                    headers['Content-Disposition'] = f'attachment; filename="asset-{self.object_id}{safe_extension}"'
                if scope['method'] == 'HEAD':
                    response = Response(status_code=status, media_type=mime, headers=headers)
                else:
                    await run_in_threadpool(opened.seek, lower)
                    async def chunks():
                        remaining = upper - lower
                        while remaining:
                            chunk = await run_in_threadpool(opened.read, min(65536, remaining))
                            if not chunk:
                                raise RuntimeError('Authorized media changed during response')
                            remaining -= len(chunk)
                            yield chunk
                    response = StreamingResponse(chunks(), status_code=status, media_type=mime, headers=headers)
                # Headers have not been sent yet. Failures during streaming cannot be
                # replaced with an error body or accidentally reopen a path.
            except AccessDenied:
                response = JSONResponse({'detail': 'Access denied'}, status_code=401, headers=PRIVACY_HEADERS)
            except TransportError as exc:
                error_headers = dict(PRIVACY_HEADERS)
                if exc.status == 416:
                    error_headers['Content-Range'] = exc.content_range
                response = JSONResponse({'detail': exc.message}, status_code=exc.status, headers=error_headers)
            except (FileNotFoundError, NotADirectoryError):
                response = JSONResponse({'detail': 'Media unavailable'}, status_code=404, headers=PRIVACY_HEADERS)
            except Exception:
                response = JSONResponse({'detail': 'Access unavailable'}, status_code=503, headers=PRIVACY_HEADERS)
            await response(scope, receive, send)
        finally:
            lease.close()


def media_response(request, object_id, variant):
    token, _ = credentials_from_request(request, allow_query=True)
    parameters = request.query_params
    allowed = {'library', 'download'} if variant == 'original' else {'library', 'size'}
    if (set(parameters) - allowed or any(len(parameters.getlist(k)) != 1 for k in parameters)
            or not parameters.get('library') or len(parameters['library']) > 128):
        raise TransportError(400, 'Invalid request')
    size = parameters.get('size', '256')
    if not re.fullmatch(r'[0-9]{2,4}', size) or not 64 <= int(size) <= 1024:
        raise TransportError(400, 'Invalid request')
    download = parameters.get('download', 'false')
    if download not in {'true', 'false'}:
        raise TransportError(400, 'Invalid request')
    return AuthorizedMediaResponse(request, token, parameters['library'], object_id,
                                   variant, int(size), download == 'true')


class MediaRoute(AccessRoute):
    allow_query = True


router = APIRouter(route_class=MediaRoute)


@router.get('/assets/{asset_id}/media')
@router.head('/assets/{asset_id}/media')
async def original(asset_id: int, request: Request):
    return media_response(request, asset_id, 'original')


@router.get('/assets/{asset_id}/thumbnail')
@router.head('/assets/{asset_id}/thumbnail')
async def thumbnail(asset_id: int, request: Request):
    return media_response(request, asset_id, 'thumbnail')


@router.get('/faces/{face_id}/crop')
@router.head('/faces/{face_id}/crop')
async def crop(face_id: int, request: Request):
    return media_response(request, face_id, 'crop')
