"""Independent v2 TV catalog over an offline publication, never the live database.

The control file is checked for every admission. Catalog and prepared media are
immutable for the lifetime of this app; a new revision needs a stopped release
switch. Byte ranges are served only from hash-bound prepared MP4 chunks.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from .home_feed import (Configuration, HomeBoundary, LIMITS, Refused, bounded_read,
                        exact, integer, jpeg_dimensions, literal, number,
                        parameters, unique)

MAX_CATALOG = 64 * 1024 * 1024
MAX_ASSETS = 100000
CHUNK_BYTES = 4 * 1024 * 1024
MAX_VIDEO = 32 * 1024**3
MISSING = ('not_prepared', 'source_missing', 'unsupported', 'preparation_failed')


def digest(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_preview(value, variant):
    if type(value) is dict and value.get('state') == 'unavailable':
        exact(value, ('state', 'reason'))
        if value['reason'] not in MISSING: raise Refused()
        return
    exact(value, ('state', 'width', 'height', 'bytes', 'sha256'))
    edge, pixels, maximum = LIMITS[variant]
    if (value['state'] != 'ready' or not integer(value['width'], 1, edge)
            or not integer(value['height'], 1, edge)
            or value['width'] * value['height'] > pixels
            or not integer(value['bytes'], 1, maximum) or not digest(value['sha256'])):
        raise Refused()


def validate_video(value):
    if type(value) is dict and value.get('state') == 'unavailable':
        exact(value, ('state', 'reason'))
        if value['reason'] not in MISSING: raise Refused()
        return
    exact(value, ('state', 'mime', 'video_codec', 'audio_codec', 'width', 'height',
                  'duration_ms', 'bytes', 'sha256', 'chunks_sha256'))
    if (value['state'] != 'ready' or value['mime'] != 'video/mp4'
            or value['video_codec'] != 'h264' or value['audio_codec'] not in ('aac', None)
            or not integer(value['width'], 1, 1920) or not integer(value['height'], 1, 1920)
            or value['width'] * value['height'] > 1920 * 1080
            or not integer(value['duration_ms'], 1, 86400000)
            or not integer(value['bytes'], 1, MAX_VIDEO)
            or not digest(value['sha256']) or not digest(value['chunks_sha256'])):
        raise Refused()


def validate_catalog(value):
    exact(value, ('version', 'revision', 'library_id', 'title', 'assets'))
    if (type(value['version']) is not int or value['version'] != 2
            or not integer(value['revision'], 1, 2**31-1)
            or type(value['library_id']) is not str
            or not re.fullmatch('[a-z0-9-]{1,64}', value['library_id'])
            or not literal(value['title'], 256) or type(value['assets']) is not list
            or len(value['assets']) > MAX_ASSETS):
        raise Refused()
    previous = 2**31
    for asset in value['assets']:
        exact(asset, ('id', 'kind', 'label', 'width', 'height', 'previews', 'video'))
        if (not integer(asset['id'], 1, previous-1) or asset['kind'] not in ('photo', 'video', 'unsupported')
                or not literal(asset['label'], 256)
                or any(n is not None and not integer(n, 1, 1000000) for n in (asset['width'], asset['height']))):
            raise Refused()
        previous = asset['id']
        exact(asset['previews'], LIMITS)
        for variant in LIMITS: validate_preview(asset['previews'][variant], variant)
        if asset['kind'] == 'video': validate_video(asset['video'])
        elif asset['video'] is not None: raise Refused()
    return value


def identity(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.resolve(strict=True) != path:
        raise Refused()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


class Publication:
    def __init__(self, config):
        self.config = config
        self.path = config.manifest.parent / 'catalog.json'
        if self.path == config.manifest or self.path.is_relative_to(config.media_root):
            raise ValueError('Catalog must be separate from control and media')
        self.lock = threading.Lock()
        self.catalog = None

    def control(self):
        value = json.loads(bounded_read(self.config.manifest, 4096), object_pairs_hook=unique)
        exact(value, ('version', 'enabled', 'revision', 'catalog_sha256'))
        if (type(value['version']) is not int or value['version'] != 2
                or type(value['enabled']) is not bool or not integer(value['revision'], 1, 2**31-1)
                or not digest(value['catalog_sha256'])): raise Refused()
        if not value['enabled']: raise Refused(403, 'feed_disabled')
        return value

    def load(self):
        control = self.control()
        with self.lock:
            if self.catalog is None:
                before = identity(self.path)
                raw = bounded_read(self.path, MAX_CATALOG)
                if hashlib.sha256(raw).hexdigest() != control['catalog_sha256']: raise Refused()
                catalog = validate_catalog(json.loads(raw, object_pairs_hook=unique))
                if catalog['revision'] != control['revision'] or identity(self.path) != before: raise Refused()
                self.catalog, self.pin, self.file_identity = catalog, control, before
                self.by_id = {a['id']: a for a in catalog['assets']}
            if control != self.pin or identity(self.path) != self.file_identity:
                raise Refused(503, 'publication_changed')
        return self.catalog

    def asset(self, aid, revision):
        catalog = self.load()
        if revision != catalog['revision']: raise Refused(409, 'feed_changed')
        asset = self.by_id.get(aid)
        if asset is None: raise Refused(404, 'asset_unavailable')
        return asset


def asset_result(asset, revision):
    value = dict(asset, originals_allowed=False)
    value['previews'] = {}
    for variant, meta in asset['previews'].items():
        value['previews'][variant] = dict(meta)
        if meta['state'] == 'ready':
            value['previews'][variant]['url'] = f"/home/v2/assets/{asset['id']}/preview?variant={variant}&revision={revision}"
    value['video'] = None if asset['video'] is None else {k: v for k, v in asset['video'].items() if k != 'chunks_sha256'}
    if value['video'] and value['video']['state'] == 'ready':
        value['video']['url'] = f"/home/v2/assets/{asset['id']}/video?revision={revision}"
    return value


def byte_range(header, size):
    """RFC single byte range, bounded parsing; multi/malformed/empty => 416."""
    if header is None: return 0, size-1, 200
    match = re.fullmatch(r'bytes=([0-9]{0,12})-([0-9]{0,12})', header)
    if not match or not any(match.groups()): raise Refused(416, 'range_not_satisfiable')
    first, last = match.groups()
    if not first:
        suffix = int(last)
        if suffix == 0: raise Refused(416, 'range_not_satisfiable')
        return max(0, size-suffix), size-1, 206
    start = int(first); end = min(int(last), size-1) if last else size-1
    if start >= size or end < start: raise Refused(416, 'range_not_satisfiable')
    return start, end, 206


class VideoReader:
    def __init__(self, config, aid, meta):
        self.path = config.media_root / 'video' / f'{aid}.mp4'
        chunks = bounded_read(config.media_root / 'video' / f'{aid}.chunks.json', 1024*1024)
        if hashlib.sha256(chunks).hexdigest() != meta['chunks_sha256']: raise Refused()
        self.hashes = json.loads(chunks)
        if (type(self.hashes) is not list or len(self.hashes) != (meta['bytes']+CHUNK_BYTES-1)//CHUNK_BYTES
                or not all(digest(h) for h in self.hashes)): raise Refused()
        self.pin = identity(self.path)
        if self.pin[2] != meta['bytes']: raise Refused()
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        self.stream = os.fdopen(os.open(self.path, flags), 'rb')
        info = os.fstat(self.stream.fileno())
        if (not stat.S_ISREG(info.st_mode)
                or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != self.pin):
            self.close(); raise Refused()

    def close(self):
        self.stream.close()

    def chunk(self, index):
        if identity(self.path) != self.pin: raise Refused()
        self.stream.seek(index * CHUNK_BYTES)
        data = self.stream.read(CHUNK_BYTES)
        if hashlib.sha256(data).hexdigest() != self.hashes[index] or identity(self.path) != self.pin:
            raise Refused()
        return data


class LeasedStream(StreamingResponse):
    """Release even on disconnect/error before the iterator starts, on all ASGI versions."""
    def __init__(self, *args, cleanup, **kwargs):
        super().__init__(*args, **kwargs)
        self.cleanup = cleanup

    async def __call__(self, scope, receive, send):
        try: await super().__call__(scope, receive, send)
        finally: self.cleanup()


def create_home_catalog(config):
    if not isinstance(config, Configuration): raise ValueError('Explicit TV configuration required')
    publication = Publication(config)
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, redirect_slashes=False)
    slots = threading.BoundedSemaphore(4)

    def perform(action):
        if not slots.acquire(blocking=False):
            return JSONResponse({'error': 'busy'}, status_code=429, headers={'Retry-After': '2'})
        leased = False
        try:
            response = action()
            leased = isinstance(response, LeasedStream)
            return response
        except Refused as error:
            return JSONResponse({'error': error.code}, status_code=error.status)
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            return JSONResponse({'error': 'feed_unavailable'}, status_code=503)
        finally:
            if not leased: slots.release()

    @app.get('/home/v2/catalog')
    async def catalog(request: Request):
        def read():
            query = parameters(request, ('page', 'page_size', 'revision'))
            page = number(query.get('page', '1'), MAX_ASSETS)
            size = number(query.get('page_size', '50'), 100)
            revision = number(query['revision'], 2**31-1) if 'revision' in query else None
            if page > 1 and revision is None: raise Refused(400, 'revision_required')
            if 'range' in request.headers or 'if-range' in request.headers: raise Refused(400, 'invalid_request')
            value = publication.load()
            if revision is not None and revision != value['revision']: raise Refused(409, 'feed_changed')
            assets = value['assets']; offset = (page-1)*size
            response = JSONResponse({'version': 2, 'revision': value['revision'],
                'library': {'id': value['library_id'], 'title': value['title']},
                'page': page, 'page_size': size, 'total': len(assets), 'has_more': offset+size < len(assets),
                'items': [asset_result(a, value['revision']) for a in assets[offset:offset+size]]})
            if len(response.body) > 524288: raise Refused()
            return response
        return await run_in_threadpool(perform, read)

    @app.get('/home/v2/assets/{asset_id}/preview')
    @app.head('/home/v2/assets/{asset_id}/preview')
    async def preview(asset_id: str, request: Request):
        def read():
            query = parameters(request, ('variant', 'revision'))
            aid = number(asset_id, 2**31-1); revision = number(query.get('revision'), 2**31-1)
            variant = query.get('variant')
            if variant not in LIMITS or 'range' in request.headers or 'if-range' in request.headers:
                raise Refused(400, 'invalid_request')
            meta = publication.asset(aid, revision)['previews'][variant]
            if meta['state'] != 'ready': raise Refused(404, 'preview_unavailable')
            try: data = bounded_read(config.media_root / variant / f'{aid}.jpg', meta['bytes'])
            except FileNotFoundError: raise Refused(404, 'preview_unavailable') from None
            if (len(data) != meta['bytes'] or hashlib.sha256(data).hexdigest() != meta['sha256']
                    or jpeg_dimensions(data) != (meta['width'], meta['height'])): raise Refused()
            return Response(data, media_type='image/jpeg', headers={'Accept-Ranges': 'none'})
        return await run_in_threadpool(perform, read)

    @app.get('/home/v2/assets/{asset_id}/video')
    @app.head('/home/v2/assets/{asset_id}/video')
    async def video(asset_id: str, request: Request):
        def read():
            query = parameters(request, ('revision',))
            aid = number(asset_id, 2**31-1); revision = number(query.get('revision'), 2**31-1)
            meta = publication.asset(aid, revision)['video']
            if meta is None or meta['state'] != 'ready': raise Refused(404, 'video_unavailable')
            # No conditional fallback to a full file or multipart ranges.
            if 'if-range' in request.headers or (request.method == 'GET' and len(request.headers.getlist('range')) > 1):
                raise Refused(400, 'invalid_request')
            try: start, end, status = byte_range(request.headers.get('range') if request.method == 'GET' else None, meta['bytes'])
            except Refused:
                return JSONResponse({'error': 'range_not_satisfiable'}, status_code=416,
                                    headers={'Content-Range': f"bytes */{meta['bytes']}", 'Accept-Ranges': 'bytes'})
            reader = None
            try:
                reader = VideoReader(config, aid, meta)
                first = reader.chunk(start // CHUNK_BYTES)  # Fail before headers on the first requested chunk.
                headers = {'Content-Length': str(end-start+1), 'Accept-Ranges': 'bytes'}
                if status == 206: headers['Content-Range'] = f"bytes {start}-{end}/{meta['bytes']}"
                if request.method == 'HEAD':
                    reader.close()
                    return Response(status_code=status, media_type='video/mp4', headers=headers)
                def chunks():
                    for index in range(start//CHUNK_BYTES, end//CHUNK_BYTES+1):
                        publication.asset(aid, revision)  # Disable/change stops further admitted chunks.
                        data = first if index == start//CHUNK_BYTES else reader.chunk(index)
                        lo = max(start-index*CHUNK_BYTES, 0); hi = min(end-index*CHUNK_BYTES+1, len(data))
                        yield data[lo:hi]
                def cleanup():
                    try: reader.close()
                    finally: slots.release()
                return LeasedStream(chunks(), status_code=status, media_type='video/mp4', headers=headers, cleanup=cleanup)
            except BaseException:
                if reader is not None: reader.close()
                raise
        return await run_in_threadpool(perform, read)

    reviewed = frozenset((method, route.path, route.endpoint) for route in app.routes for method in route.methods)
    app.add_middleware(HomeBoundary, config=config, routes=app.routes, reviewed=reviewed)
    return app
