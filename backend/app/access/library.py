"""Bounded library reads through the same current account/membership policy.

Only migrated metadata and explicit asset mappings are read. No ORM/configuration,
filesystem, vector index, model, provider or processing side effects are imported.
"""
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .service import AccessDenied, AccessService
from .transport import AccessRoute, TransportError, _runtime, credentials_from_request


class LibraryRoute(AccessRoute):
    allow_query = True


router = APIRouter(route_class=LibraryRoute)
SOURCE = ''' FROM assets a JOIN access_asset_libraries scope ON scope.asset_id=a.id
    WHERE scope.library_id=? AND (a.status IS NULL OR a.status='active')'''
FIELDS = 'a.id,a.mime,a.width,a.height,a.duration_sec,a.taken_at'
# Shared mobile response budget, measured with the actual JSON wire serializer.
CAPTION_RESPONSE_BYTES = 512 * 1024


def _asset(row, library_id):
    asset_id, mime, width, height, duration, taken_at = row
    return {'id': str(asset_id), 'kind': 'video' if (mime or '').startswith('video/') else
            'image' if (mime or '').startswith('image/') else 'other',
            'width': width, 'height': height, 'duration_sec': duration, 'taken_at': taken_at,
            'thumbnail_url': f'/assets/{asset_id}/thumbnail?' + urlencode({'library': library_id})}


class LibraryReads:
    def __init__(self, service):
        self.access = service

    def gallery(self, token, library_id, *, page=1, page_size=50):
        if type(page) is not int or not 1 <= page <= 100000 or type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError('Invalid pagination')
        with self.access._transaction():
            member = self.access._require(token, library_id, 'library.read')
            db = self.access.db
            total = db.execute('SELECT count(*)' + SOURCE, (library_id,)).fetchone()[0]
            rows = db.execute('SELECT ' + FIELDS + SOURCE +
                ' ORDER BY a.taken_at DESC,a.id DESC LIMIT ? OFFSET ?',
                (library_id, page_size, (page - 1) * page_size)).fetchall()
            return {'library_id': library_id, 'page': page, 'page_size': page_size,
                    'total': total, 'originals_allowed': bool(member['originals']),
                    'items': [_asset(row, library_id) for row in rows]}

    def detail(self, token, library_id, asset_id):
        with self.access._transaction():
            member = self.access._require(token, library_id, 'library.read')
            row = self.access.db.execute('SELECT ' + FIELDS + SOURCE + ' AND a.id=?',
                                         (library_id, asset_id)).fetchone()
            if row is None:
                raise AccessDenied('Access denied')
            return {'library_id': library_id, 'originals_allowed': bool(member['originals']),
                    'asset': _asset(row, library_id)}

    def captions(self, token, library_id, asset_id):
        with self.access._transaction():
            self.access._require(token, library_id, 'library.read')
            if self.access.db.execute('SELECT a.id' + SOURCE + ' AND a.id=?',
                                      (library_id, asset_id)).fetchone() is None:
                raise AccessDenied('Access denied')
            # Parent approval above and child join below share one SQLite snapshot.
            # Bound both row count and text; no model/debug/path metadata is returned.
            rows = self.access.db.execute('''SELECT c.id,substr(c.text,1,8192),length(c.text),
                c.user_edited,c.created_at,c.updated_at FROM captions c
                JOIN assets a ON a.id=c.asset_id
                JOIN access_asset_libraries scope ON scope.asset_id=a.id
                WHERE scope.library_id=? AND a.id=? AND (a.status IS NULL OR a.status='active')
                AND c.superseded=0 ORDER BY c.user_edited DESC,c.id DESC LIMIT 21''',
                (library_id, asset_id)).fetchall()
            result = {'library_id': library_id, 'asset_id': str(asset_id),
                      'has_more': bool(rows), 'items': []}
            for r in rows[:20]:
                result['items'].append({'id': str(r[0]), 'text': r[1], 'truncated': r[2] > 8192,
                    'user_edited': bool(r[3]), 'created_at': r[4], 'updated_at': r[5]})
                result['has_more'] = len(rows) > len(result['items'])
                # UTF-8 and JSON escaping can exceed a character-count budget.
                # Keep an ordered prefix of whole rows. Text truncation retains
                # its existing meaning; has_more also reports omitted rows.
                if len(JSONResponse(result).body) > CAPTION_RESPONSE_BYTES:
                    result['items'].pop()
                    result['has_more'] = True
                    break
            return result


def _read(runtime, action, *args, **kwargs):
    if action not in {'gallery', 'detail', 'captions'}:
        raise AccessDenied('Access denied')
    with runtime.connection_factory() as connection:
        reads = LibraryReads(AccessService(connection, clock=runtime.clock))
        return getattr(reads, action)(*args, **kwargs)


def _query(request, allowed):
    if len(request.scope.get('query_string', b'')) > 1024:
        raise TransportError(400, 'Invalid request')
    pairs = list(request.query_params.multi_items())
    if len(pairs) != len(dict(pairs)) or set(dict(pairs)) - allowed:
        raise TransportError(400, 'Invalid request')
    query = dict(pairs)
    library = query.get('library', '')
    if not library or len(library) > 128 or any(ord(c) < 32 for c in library):
        raise TransportError(400, 'Invalid request')
    return query


def _integer(value, maximum):
    if not value.isascii() or not value.isdecimal() or len(value) > 19 or not 1 <= int(value) <= maximum:
        raise TransportError(400, 'Invalid request')
    return int(value)


@router.get('/assets')
async def gallery(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page', 'page_size'})
    result = await run_in_threadpool(_read, _runtime(request, allow_query=True), 'gallery', token,
        query['library'], page=_integer(query.get('page', '1'), 100000),
        page_size=_integer(query.get('page_size', '50'), 100))
    return JSONResponse(result)


@router.get('/assets/detail/{asset_id}')
async def detail(asset_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    result = await run_in_threadpool(_read, _runtime(request, allow_query=True), 'detail', token,
                                    query['library'], _integer(asset_id, 2**63-1))
    return JSONResponse(result)


@router.get('/assets/{asset_id}/captions')
async def captions(asset_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    result = await run_in_threadpool(_read, _runtime(request, allow_query=True), 'captions', token,
                                    query['library'], _integer(asset_id, 2**63-1))
    return JSONResponse(result)
