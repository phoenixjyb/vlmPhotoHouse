"""Candidate protected discovery transport; enabled only by an explicit factory.

No default-app imports, filesystem/index discovery, prepared media or model work.
"""
import asyncio
from contextlib import suppress
from dataclasses import dataclass
import json
import math
import re
import threading
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

from . import discovery as d
from .service import AccessService, AccessDenied
from .transport import AccessRuntime, TransportError, PRIVACY_HEADERS, _runtime, _single, credentials_from_request

MAX_BODY = 20 * 1024
BODY_SECONDS = 2


@dataclass(frozen=True)
class DiscoveryRuntime:
    access: AccessRuntime
    provider: object
    budget: d.ReadBudget

    def __post_init__(self):
        if not isinstance(self.access, AccessRuntime) or not isinstance(self.budget, d.ReadBudget) or not callable(self.provider.get):
            raise ValueError('Explicit access, reviewed provider and shared budget required')

    def authorize(self, token, library):
        with self.access.connection_factory() as connection:
            AccessService(connection, clock=self.access.clock).require(token, library, 'library.read')

    def call(self, operation, token, library, cancelled, values):
        with self.access.connection_factory() as connection:
            service = d.DiscoveryReads(AccessService(connection, clock=self.access.clock), self.provider, self.budget)
            # Fixed dispatch, never a caller-selected service method.
            method = service.facets if operation == 'facets' else service.search
            return method(token, library, cancelled=cancelled, **values)


def runtime(request):
    access = _runtime(request, allow_query=True)
    result = getattr(request.app.state, 'discovery_runtime', None)
    if not isinstance(result, DiscoveryRuntime) or result.access is not access:
        raise d.DiscoveryUnavailable()
    return result


def failure(status, code, detail, headers=None):
    return JSONResponse({'error': code, 'detail': detail}, status_code=status, headers=headers)


class DiscoveryRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def guarded(request):
            try:
                _runtime(request, allow_query=True)
                response = await handler(request)
            except TransportError as e:
                code = {401:'access_denied',403:'access_denied',408:'request_timeout',413:'request_too_large',503:'discovery_unavailable'}.get(e.status,'invalid_request')
                response = failure(e.status, code, e.message)
            except AccessDenied:
                response = failure(401, 'access_denied', 'Access denied')
            except d.DiscoveryInvalid:
                response = failure(400, 'invalid_request', 'Invalid discovery request')
            except d.DiscoveryChanged:
                response = failure(409, 'discovery_changed', 'Refresh discovery state')
            except d.DiscoveryBusy:
                response = failure(429, 'discovery_busy', 'Discovery busy', {'Retry-After':'2'})
            except d.DiscoveryCancelled:
                response = failure(499, 'request_cancelled', 'Request cancelled')
            except Exception:
                # Never expose SQL, paths, provider exceptions or request contents.
                response = failure(503, 'discovery_unavailable', 'Discovery unavailable')
            for name, value in PRIVACY_HEADERS.items(): response.headers[name] = value
            return response
        return guarded


router = APIRouter(route_class=DiscoveryRoute)


def integer(value, maximum):
    if not re.fullmatch(r'[1-9][0-9]{0,5}', value) or int(value)>maximum: raise d.DiscoveryInvalid()
    return int(value)


def query(request):
    raw = request.scope.get('query_string', b'')
    try:
        text = raw.decode('ascii')
        if re.search(r'%(?![0-9a-fA-F]{2})', text): raise ValueError()
        pairs = parse_qsl(text, keep_blank_values=True, strict_parsing=True, errors='strict', max_num_fields=5)
        values = dict(pairs)
        if len(values)!=len(pairs) or set(values)-{'facet','page','page_size','binding','q'}: raise ValueError()
        result = {'facet':values.get('facet','people'), 'page':integer(values.get('page','1'),5000),
                  'page_size':integer(values.get('page_size','50'),100)}
        if 'binding' in values: result['binding']=values['binding']
        if 'q' in values:
            if result['facet'] != 'locations': raise ValueError()
            d.text(values['q'],128,nonempty=False);result['q']=values['q']
        return result
    except (ValueError, UnicodeError): raise d.DiscoveryInvalid() from None


def unique(pairs):
    result = {}
    for key,value in pairs:
        if key in result: raise ValueError()
        result[key]=value
    return result


def reject_constant(_): raise ValueError()


def bounded_structure(value, depth=0, count=None):
    if count is None: count=[0]
    count[0]+=1
    if depth>6 or count[0]>1024: raise ValueError()
    if type(value) is str:
        value.encode('utf-8')
        if len(value.encode('utf-8'))>4096: raise ValueError()
    elif type(value) is dict:
        for key,item in value.items():
            bounded_structure(key,depth+1,count);bounded_structure(item,depth+1,count)
    elif type(value) is list:
        for item in value: bounded_structure(item,depth+1,count)


async def body(request):
    if request.scope.get('query_string') or _single(request,'content-encoding') is not None:
        raise d.DiscoveryInvalid()
    content_type=(_single(request,'content-type') or '').lower().replace(' ','')
    if content_type not in ('application/json','application/json;charset=utf-8'): raise d.DiscoveryInvalid()
    length=_single(request,'content-length')
    if length is not None and (not re.fullmatch(r'[0-9]{1,5}',length) or int(length)>MAX_BODY):
        raise TransportError(413,'Request too large')
    raw=bytearray()
    try:
        async with asyncio.timeout(BODY_SECONDS):
            async for chunk in request.stream():
                if len(raw)+len(chunk)>MAX_BODY: raise TransportError(413,'Request too large')
                raw.extend(chunk)
    except TimeoutError: raise TransportError(408,'Request timed out') from None
    try:
        if length is not None and len(raw)!=int(length): raise ValueError()
        result=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=reject_constant)
        bounded_structure(result)
        if type(result) is not dict or set(result)!={'binding','filters','page','page_size','fingerprint'}: raise ValueError()
        return result
    except (ValueError,UnicodeError,RecursionError): raise d.DiscoveryInvalid() from None


async def invoke(request, engine, operation, token, library, values):
    cancelled=threading.Event()
    async def watch():
        while not cancelled.is_set():
            if await request.is_disconnected():
                cancelled.set();return
            await asyncio.sleep(.025)
    watcher=asyncio.create_task(watch())
    try:
        result=await run_in_threadpool(engine.call,operation,token,library,cancelled.is_set,values)
        if operation == 'search':
            # Missing/invalid descriptive dimensions do not become trusted native
            # integers. No byte access or media capability is inferred here.
            for item in result['items']:
                for field in ('width','height'):
                    value=item[field]
                    if type(value) is not int or not 1<=value<=1000000: item[field]=None
                value=item['duration_sec']
                if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1e9): item['duration_sec']=None
        response=JSONResponse(dict(version=1,**result))
        if len(response.body)>min(512*1024,engine.budget.response_bytes): raise d.DiscoveryUnavailable()
        return response
    finally:
        cancelled.set();watcher.cancel()
        with suppress(asyncio.CancelledError): await watcher


async def admitted(request, library):
    token,_=credentials_from_request(request,allow_query=True)
    engine=runtime(request)
    # Deny membership before parsing/disclosing discovery inputs. The actual read
    # reauthorizes inside its own source snapshot after body receipt.
    await run_in_threadpool(engine.authorize,token,library)
    return token,engine


@router.get('/libraries/{library_id}/discovery/v1/facets')
async def facets(library_id: str, request: Request):
    token,engine=await admitted(request,library_id)
    if _single(request,'transfer-encoding') is not None or _single(request,'content-length') not in (None,'0'):
        raise d.DiscoveryInvalid()
    return await invoke(request,engine,'facets',token,library_id,query(request))


@router.post('/libraries/{library_id}/discovery/v1/search')
async def search(library_id: str, request: Request):
    token,engine=await admitted(request,library_id)
    return await invoke(request,engine,'search',token,library_id,await body(request))
