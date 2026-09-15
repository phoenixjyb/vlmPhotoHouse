"""Explicit discovery/v3 tag lookup; legacy discovery and media remain composed."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from .home_discovery import validate_index, fold, text, MAX_INDEX
from .home_discovery_delivery import DeliveryIndex, create_home_discovery_delivery
from .home_feed import Refused, bounded_read, exact, integer, unique
from .home_catalog import identity

MAX_TAGS = 10000

def validate_tag_index(value, catalog, digest):
    if type(value) is not dict or type(value.get('version')) is not int or value['version'] != 2:
        raise Refused()
    tags = value.get('tags'); assets = value.get('assets')
    if type(tags) is not list or len(tags) > MAX_TAGS or type(assets) is not list or len(assets)>len(catalog['assets']):
        raise Refused()
    roster = set()
    for tag in tags:
        exact(tag, ('id','label','kind'))
        if not integer(tag['id'],1,2**31-1) or tag['id'] in roster or tag['kind'] not in ('date','location','person','scene','custom','unknown'):
            raise Refused()
        text(tag['label'],256,True);roster.add(tag['id'])
    shadow=[]
    for asset in assets:
        if type(asset) is not dict or type(asset.get('tags')) is not list or len(asset['tags'])>100:raise Refused()
        seen=set()
        for tag in asset['tags']:
            exact(tag,('id','source'))
            if not integer(tag['id'],1,2**31-1) or tag['id'] not in roster or tag['id'] in seen or tag['source'] not in ('manual','caption','image','caption_image','rule','unknown'):raise Refused()
            seen.add(tag['id'])
        shadow.append(dict(asset,tags=[]))
    # Reuse the frozen validation for every non-tag field; never mutate the caller.
    validate_index(dict(value,version=1,tags=[],assets=shadow),catalog,digest)
    return value

class TagIndex(DeliveryIndex):
    def load(self):
        catalog=self.publication.load()
        with self.lock:
            if self.value is None:
                before=identity(self.path);raw=bounded_read(self.path,MAX_INDEX)
                if hashlib.sha256(raw).hexdigest()!=self.sha256:raise Refused()
                value=validate_tag_index(json.loads(raw,object_pairs_hook=unique),catalog,self.publication.pin['catalog_sha256'])
                if identity(self.path)!=before:raise Refused()
                self.value=value;self.pin=before
                self.rows={r['id']:r for r in value['assets']}
                self.folded={r['id']:fold(r['caption_text']) for r in value['assets'] if r['caption_text'] is not None}
                self.rosters={f:{r['id']:r for r in value[f]} for f in ('people','tags','locations')}
                self.counts={f:Counter() for f in ('people','tags','locations')};self.sources={}
                for r in value['assets']:
                    self.counts['people'].update(r['person_ids']);self.counts['locations'].update(r['location_ids'])
                    for tag in r['tags']:
                        self.counts['tags'][tag['id']]+=1
                        self.sources.setdefault(tag['id'],Counter())[tag['source']]+=1
            if identity(self.path)!=self.pin:raise Refused(503,'index_changed')
        self.media_sources.load()
        return self.value,catalog

    def facets(self,facet,page,size,revision,query=''):
        if type(query) is not str or query != query.strip() or len(query.encode('utf-8'))>128 or any(ord(c)<32 for c in query):
            raise Refused(400,'invalid_request')
        if facet!='tags' and query:raise Refused(400,'invalid_request')
        result=super().facets(facet,page,size,revision)
        if facet=='tags':
            rows=[r for r in sorted(self.rosters['tags'].values(),key=lambda r:r['id'])
                  if 'tags' in self.value['enabled_filters'] and fold(query) in fold(r['label'])]
            offset=(page-1)*size
            result.update(total=len(rows),has_more=offset+size<len(rows),items=[self.facet_item('tags',r) for r in rows[offset:offset+size]])
        return dict(result,version=3,query=query)

    def query(self,request):return dict(super().query(request),version=3)

class TagComposition:
    def __init__(self,tags,legacy):self.tags,self.legacy=tags,legacy
    async def __call__(self,scope,receive,send):
        child=self.tags if scope.get('path','').startswith('/home/discovery/v3/') else self.legacy
        await child(scope,receive,send)

import asyncio
import threading
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .home_feed import Configuration, HomeBoundary, number, parameters
from .home_originals import SourceIndex
from .home_discovery_delivery import read_body, BODY_SECONDS

def create_home_tag_discovery(config, sources, cache, index_path: Path, index_sha256: str, legacy_path: Path, legacy_sha256: str):
    if not isinstance(config, Configuration) or not isinstance(sources, SourceIndex):
        raise ValueError('Explicit Home configuration and source policy required')
    if sources.publication.config != config:
        raise ValueError('Discovery and media must use the same publication and audience')
    index = TagIndex(sources, index_path, index_sha256)
    app=FastAPI(openapi_url=None,docs_url=None,redoc_url=None,redirect_slashes=False)
    slots=threading.BoundedSemaphore(2)
    body_slots=threading.BoundedSemaphore(2)

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

    @app.get('/home/discovery/v3/facets')
    async def facets(request: Request):
        def read():
            query=parameters(request,('facet','page','page_size','revision','q'));facet=query.get('facet','people')
            page=number(query.get('page','1'),5000);size=number(query.get('page_size','50'),100)
            revision=number(query['revision'],2**31-1) if 'revision' in query else None
            if facet not in ('people','tags','locations') or 'range' in request.headers or 'if-range' in request.headers:raise Refused(400,'invalid_request')
            if page>1 and revision is None:raise Refused(400,'revision_required')
            return index.facets(facet,page,size,revision,query.get('q',''))
        return await run_in_threadpool(perform,read)

    @app.post('/home/discovery/v3/search')
    async def search(request: Request):
        if (request.query_params or request.headers.getlist('content-type')!=['application/json']
                or 'range' in request.headers or 'if-range' in request.headers):
            return JSONResponse({'error':'invalid_request'},status_code=400)
        if not body_slots.acquire(blocking=False):
            return JSONResponse({'error':'busy'},status_code=429,headers={'Retry-After':'2'})
        try:
            raw=await asyncio.wait_for(read_body(request),timeout=BODY_SECONDS)
        except asyncio.TimeoutError:
            return JSONResponse({'error':'request_timeout'},status_code=408)
        except Refused as error:
            return JSONResponse({'error':error.code},status_code=error.status)
        finally: body_slots.release()
        try:body=json.loads(raw,object_pairs_hook=unique)
        except (ValueError,Refused,RecursionError):return JSONResponse({'error':'invalid_request'},status_code=400)
        return await run_in_threadpool(perform,lambda:index.query(body))

    reviewed=frozenset((method,route.path,route.endpoint) for route in app.routes for method in route.methods)
    app.add_middleware(HomeBoundary,config=config,routes=app.routes,reviewed=reviewed)
    return TagComposition(app, create_home_discovery_delivery(config, sources, cache, legacy_path, legacy_sha256))
