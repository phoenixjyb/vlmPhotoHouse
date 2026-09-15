"""Opt-in reviewed Home search with v3 media. No live indexing or deployment.

The frozen discovery/v1 implementation and examples remain unchanged. Version 2
uses its same filter semantics and immutable metadata admission, returning v3
items from the exact same publication as the media child.
"""
import json
import threading
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .home_discovery import DiscoveryIndex
from .home_feed import Configuration, HomeBoundary, Refused, number, parameters, unique
from .home_originals import SourceIndex, create_home_originals

PREFIX = '/home/discovery/v2/'

class DeliveryIndex(DiscoveryIndex):
    def __init__(self, sources, index_path, index_sha256):
        super().__init__(sources.publication, index_path, index_sha256)
        self.media_sources = sources

    def load(self):
        value, catalog = super().load()
        # Both inputs are pinned to one shared Publication instance. Recheck the
        # source-index identity on every search/facet request, even after a hit.
        self.media_sources.load()
        return value, catalog

    def facets(self, *args):
        return dict(super().facets(*args), version=2)

    def query(self, request):
        response = super().query(request)
        revision = response['catalog_revision']
        self.media_sources.load()
        items = [self.media_sources.result(self.publication.asset(a['id'], revision), revision)
                 for a in response['items']]
        self.load()
        return dict(response, version=2, items=items)

class DeliveryComposition:
    def __init__(self, discovery, media):
        self.discovery, self.media = discovery, media
    async def __call__(self, scope, receive, send):
        child = self.discovery if scope.get('path', '').startswith(PREFIX) else self.media
        await child(scope, receive, send)

def create_home_discovery_delivery(config, sources, cache, index_path: Path, index_sha256: str):
    if not isinstance(config, Configuration) or not isinstance(sources, SourceIndex):
        raise ValueError('Explicit Home configuration and source policy required')
    if sources.publication.config != config:
        raise ValueError('Discovery and media must use the same publication and audience')
    index = DeliveryIndex(sources, index_path, index_sha256)
    app=FastAPI(openapi_url=None,docs_url=None,redoc_url=None,redirect_slashes=False)
    slots=threading.BoundedSemaphore(2)

    def perform(action):
        if not slots.acquire(blocking=False):return JSONResponse({'error':'busy'},status_code=429,headers={'Retry-After':'2'})
        try:
            body=action();response=JSONResponse(body)
            if len(response.body)>524288:raise Refused()
            return response
        except Refused as error:
            code='discovery_unavailable' if error.code=='feed_unavailable' else error.code
            return JSONResponse({'error':code},status_code=error.status)
        except (OSError,ValueError,TypeError,KeyError,RecursionError):return JSONResponse({'error':'discovery_unavailable'},status_code=503)
        finally:slots.release()

    @app.get('/home/discovery/v2/facets')
    async def facets(request: Request):
        def read():
            query=parameters(request,('facet','page','page_size','revision'));facet=query.get('facet','people')
            page=number(query.get('page','1'),5000);size=number(query.get('page_size','50'),100)
            revision=number(query['revision'],2**31-1) if 'revision' in query else None
            if facet not in ('people','tags','locations') or 'range' in request.headers or 'if-range' in request.headers:raise Refused(400,'invalid_request')
            if page>1 and revision is None:raise Refused(400,'revision_required')
            return index.facets(facet,page,size,revision)
        return await run_in_threadpool(perform,read)

    @app.post('/home/discovery/v2/search')
    async def search(request: Request):
        if (request.query_params or request.headers.getlist('content-type')!=['application/json']
                or 'range' in request.headers or 'if-range' in request.headers):
            return JSONResponse({'error':'invalid_request'},status_code=400)
        raw=bytearray()
        async for part in request.stream():
            if len(raw)+len(part)>16384:return JSONResponse({'error':'request_too_large'},status_code=413)
            raw.extend(part)
        try:body=json.loads(raw,object_pairs_hook=unique)
        except (ValueError,Refused,RecursionError):return JSONResponse({'error':'invalid_request'},status_code=400)
        return await run_in_threadpool(perform,lambda:index.query(body))

    reviewed=frozenset((method,route.path,route.endpoint) for route in app.routes for method in route.methods)
    app.add_middleware(HomeBoundary,config=config,routes=app.routes,reviewed=reviewed)
    return DeliveryComposition(app, create_home_originals(config, sources, cache))
