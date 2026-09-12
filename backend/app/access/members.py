"""Owner-scoped member readback and revision-bound revocation only."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import _integer
from .transport import AccessRoute, TransportError, _body, _runtime, credentials_from_request


class MemberRoute(AccessRoute):
    allow_query = True


router = APIRouter(route_class=MemberRoute)


@router.get('/libraries/{library_id}/members')
async def members(library_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    if len(request.scope.get('query_string', b'')) > 1024:
        raise TransportError(400, 'Invalid request')
    pairs = list(request.query_params.multi_items())
    if len(pairs) != len(dict(pairs)) or set(dict(pairs)) - {'page', 'page_size'}:
        raise TransportError(400, 'Invalid request')
    query = dict(pairs)
    result = await run_in_threadpool(_runtime(request, allow_query=True).call, 'list_memberships', token,
        library_id, page=_integer(query.get('page', '1'), 100000),
        page_size=_integer(query.get('page_size', '50'), 100))
    return JSONResponse(result)


@router.post('/libraries/{library_id}/members/{account_id}/revoke')
async def revoke(library_id: str, account_id: str, request: Request):
    token, _ = credentials_from_request(request)
    body = await _body(request, {'revision'})
    await run_in_threadpool(_runtime(request).call, 'revoke_membership', token, library_id,
                            account_id, expected_revision=_integer(body['revision'], 2**63-1))
    return JSONResponse({'ok': True})
