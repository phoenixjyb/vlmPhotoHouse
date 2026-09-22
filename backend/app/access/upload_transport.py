"""Member upload transport.

The route exists whenever the app is built, but answers `503` unless an incoming root was
configured: `app.state.upload_runtime` is `None` by default, so no existing deployment changes
behaviour. The capability itself (`upload.submit`) is enforced in the service, not here, so a
direct caller of the service boundary cannot bypass it either.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .transport import (TransportError, _runtime, _single,
                        credentials_from_request)
from .upload import MAX_UPLOAD_BYTES, UploadRuntime
from .library import LibraryRoute, _integer

router = APIRouter(route_class=LibraryRoute)


def runtime(request, *, allow_query=False):
    access = _runtime(request, allow_query=allow_query)
    result = getattr(request.app.state, 'upload_runtime', None)
    if not isinstance(result, UploadRuntime) or result.access is not access:
        raise TransportError(503, 'Access unavailable')
    return result


async def payload(request):
    """Read the raw body, applying the cap while streaming and not only from the header.

    A declared `Content-Length` over the cap is refused before any body is read; a chunked body
    with no length is refused as soon as the accumulated bytes cross it. Neither path buffers an
    oversize body in order to discover that it is oversize.
    """
    if _single(request, 'content-encoding') is not None:
        raise TransportError(400, 'Invalid request')
    if (_single(request, 'content-type') or '').split(';')[0].strip().lower() != 'application/octet-stream':
        raise TransportError(400, 'Invalid request')
    declared = _single(request, 'content-length')
    if declared is not None:
        if not declared.isascii() or not declared.isdecimal():
            raise TransportError(400, 'Invalid request')
        if int(declared) > MAX_UPLOAD_BYTES:
            raise TransportError(413, 'Upload too large')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_UPLOAD_BYTES:
            raise TransportError(413, 'Upload too large')
    return bytes(raw)


@router.post('/uploads')
async def create_upload(request: Request):
    """Accept one photo into the caller's own incoming folder, in no library.

    The batch identifier is supplied by the caller and strictly validated, so one upload session
    is one review unit and one "this batch → library X" action. The server does not invent it:
    a per-request identifier would put every photo in its own folder and destroy that grouping.
    """
    upload = runtime(request)
    token, _mode = credentials_from_request(request)
    filename = _single(request, 'x-upload-filename')
    batch = _single(request, 'x-upload-batch')
    if filename is None or batch is None:
        raise TransportError(400, 'Invalid request')
    data = await payload(request)
    result = await run_in_threadpool(upload.store, token, data, filename, batch)
    return JSONResponse(result, status_code=201)


@router.get('/uploads')
async def own_uploads(request: Request):
    upload = runtime(request, allow_query=True)
    token, _mode = credentials_from_request(request, allow_query=True)
    pairs = list(request.query_params.multi_items())
    if len(pairs) != len(dict(pairs)) or set(dict(pairs)) - {'page'}:
        raise TransportError(400, 'Invalid request')
    page = _integer(dict(pairs).get('page', '1'), 100000)
    return JSONResponse(await run_in_threadpool(upload.history, token, page=page))
