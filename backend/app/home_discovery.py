"""Additive offline discovery over the frozen TV v2 publication; no DB/model access.

Only an explicit, hash-bound, reviewed metadata snapshot is searchable. This
module never derives identities, geocodes, generates tags or exports live data.
"""
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import threading
from time import monotonic
import unicodedata

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .home_feed import (Configuration, HomeBoundary, Refused, bounded_read, direct_path,
                        exact, integer, literal, number, parameters, unique)
from .home_catalog import Publication, asset_result, create_home_catalog, digest, identity

PREFIX='/home/discovery/v1/'
FILTERS=('people','date','locations','media','tags','caption')
SOURCES=('manual','caption','image','caption_image','rule','unknown')
MAX_INDEX=128*1024*1024


def text(value, maximum, nonempty=False):
    if not literal(value,maximum) or (nonempty and not value.strip()): raise Refused()


def ids(value, maximum, roster=None):
    if (type(value) is not list or len(value)>maximum or not all(integer(i,1,2**31-1) for i in value)
            or len(set(value))!=len(value) or (roster is not None and not set(value)<=set(roster))): raise Refused()


def day(value):
    if value is None:return None
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise Refused()
    date.fromisoformat(value)
    return value


def fold(value):return unicodedata.normalize('NFKC',value).casefold()


def validate_index(value, catalog, catalog_sha256):
    exact(value,('version','revision','catalog_revision','catalog_sha256','enabled_filters','people','pinned_person_ids','tags','locations','assets'))
    if (type(value['version']) is not int or value['version']!=1
            or not integer(value['revision'],1,2**31-1) or type(value['catalog_revision']) is not int
            or value['catalog_revision']!=catalog['revision'] or value['catalog_sha256']!=catalog_sha256):raise Refused(503,'index_mismatch')
    enabled=value['enabled_filters']
    if type(enabled) is not list or not all(type(s) is str for s in enabled) or len(set(enabled))!=len(enabled) or not set(enabled)<=set(FILTERS) or 'media' not in enabled:raise Refused()
    rosters={}
    for field in ('people','tags','locations'):
        rows=value[field]
        if type(rows) is not list or len(rows)>5000:raise Refused()
        roster={}
        for row in rows:
            extra=('aliases',) if field=='people' else ('kind',) if field=='tags' else ()
            exact(row,('id','label',*extra))
            if not integer(row['id'],1,2**31-1) or row['id'] in roster:raise Refused()
            text(row['label'],256,True)
            if field=='people':
                if type(row['aliases']) is not list or len(row['aliases'])>8:raise Refused()
                for alias in row['aliases']:text(alias,128,True)
                if len(set(row['aliases']))!=len(row['aliases']):raise Refused()
            if field=='tags' and row['kind'] not in ('date','location','person','scene','custom','unknown'):raise Refused()
            roster[row['id']]=row
        rosters[field]=roster
    ids(value['pinned_person_ids'],32,rosters['people'])
    catalog_ids={a['id'] for a in catalog['assets']};seen=set()
    if type(value['assets']) is not list or len(value['assets'])>len(catalog_ids):raise Refused()
    for row in value['assets']:
        exact(row,('id','person_ids','people_provenance','taken_day','location_ids','location_provenance','tags','caption_text'))
        if not integer(row['id'],1,2**31-1) or row['id'] not in catalog_ids or row['id'] in seen:raise Refused()
        seen.add(row['id']);ids(row['person_ids'],100,rosters['people']);ids(row['location_ids'],32,rosters['locations'])
        if row['people_provenance'] not in (None,'reviewed_assignments') or (row['person_ids'] and row['people_provenance']!='reviewed_assignments'):raise Refused()
        if row['location_provenance'] not in (None,'reviewed_region') or (row['location_ids'] and row['location_provenance']!='reviewed_region'):raise Refused()
        day(row['taken_day'])
        if row['caption_text'] is not None:text(row['caption_text'],4096,True)
        if type(row['tags']) is not list or len(row['tags'])>100:raise Refused()
        seen_tags=set()
        for tag in row['tags']:
            exact(tag,('id','source'))
            if (not integer(tag['id'],1,2**31-1) or tag['id'] not in rosters['tags']
                    or tag['id'] in seen_tags or tag['source'] not in SOURCES):raise Refused()
            seen_tags.add(tag['id'])
    return value


class DiscoveryIndex:
    def __init__(self, publication, path, expected_sha256):
        self.publication=publication;self.path=direct_path(path);self.sha256=expected_sha256
        if not digest(expected_sha256) or path.is_relative_to(publication.config.media_root) or path in (publication.path,publication.config.manifest):raise ValueError('Separate hash-bound metadata file required')
        self.value=None;self.lock=threading.Lock()

    def load(self):
        catalog=self.publication.load()
        with self.lock:
            if self.value is None:
                before=identity(self.path);raw=bounded_read(self.path,MAX_INDEX)
                if hashlib.sha256(raw).hexdigest()!=self.sha256:raise Refused()
                value=validate_index(json.loads(raw,object_pairs_hook=unique),catalog,self.publication.pin['catalog_sha256'])
                if identity(self.path)!=before:raise Refused()
                self.value=value;self.pin=before
                self.rows={r['id']:r for r in value['assets']}
                self.folded={r['id']:fold(r['caption_text']) for r in value['assets'] if r['caption_text'] is not None}
                self.rosters={field:{r['id']:r for r in value[field]} for field in ('people','tags','locations')}
                self.counts={field:Counter() for field in ('people','tags','locations')};self.sources={}
                for r in value['assets']:
                    self.counts['people'].update(r['person_ids']);self.counts['locations'].update(r['location_ids'])
                    for tag in r['tags']:
                        self.counts['tags'][tag['id']]+=1
                        self.sources.setdefault(tag['id'],Counter())[tag['source']]+=1
            if identity(self.path)!=self.pin:raise Refused(503,'index_changed')
        return self.value,catalog

    def capabilities(self):
        value,catalog=self.load();rows=list(self.rows.values());total=len(catalog['assets'])
        counts={'people':sum(bool(r['person_ids']) for r in rows),'date':sum(r['taken_day'] is not None for r in rows),
                'locations':sum(bool(r['location_ids']) for r in rows),'tags':sum(bool(r['tags']) for r in rows),
                'caption':len(self.folded),'media':total}
        counts={key:count if key in value['enabled_filters'] else 0 for key,count in counts.items()}
        filters={key:{'enabled':key in value['enabled_filters'],'reason':None if key in value['enabled_filters'] else 'not_published',
                      'assets_with_values':counts[key],'assets_without_values':total-counts[key]} for key in FILTERS}
        for key in ('themes','topics'):
            filters[key]={'enabled':False,'reason':'no_reviewed_taxonomy','assets_with_values':0,'assets_without_values':total}
        days=[r['taken_day'] for r in rows if r['taken_day'] is not None] if 'date' in value['enabled_filters'] else []
        return {'filters':filters,'catalog_assets':total,'indexed_assets':len(rows),'index_complete':len(rows)==total,
                'metadata_completeness':'not_inferred','tag_generation_completeness':'unknown',
                'date_basis':'recorded_taken_at_calendar_date','location_basis':'reviewed_coarse_region',
                'people_basis':'reviewed_assignments','caption_match':'nfkc_casefold_literal_phrase',
                'filter_join':'and','people_modes':['any','all'],'tag_modes':['any','all'],
                'captured_date_bounds':{'from':min(days) if days else None,'to':max(days) if days else None}}

    def facet_item(self, field, row):
        result=dict(row,asset_count=self.counts[field][row['id']])
        if field=='people':result['provenance']='reviewed_assignments'
        elif field=='locations':result['provenance']='reviewed_region'
        else:result['provenance_counts']={key:self.sources.get(row['id'],{}).get(key,0) for key in SOURCES}
        return result

    def facets(self, facet, page, size, revision):
        value,catalog=self.load()
        if revision is not None and revision!=value['revision']:raise Refused(409,'discovery_changed')
        enabled=facet in value['enabled_filters']
        rows=sorted(self.rosters[facet].values(),key=lambda r:r['id']) if enabled else []
        offset=(page-1)*size
        pins=value['pinned_person_ids'] if 'people' in value['enabled_filters'] else []
        return {'version':1,'revision':value['revision'],'catalog_revision':catalog['revision'],
                'library':{'id':catalog['library_id'],'title':catalog['title']},'capabilities':self.capabilities(),
                'pinned_person_ids':pins,'pinned_people':[self.facet_item('people',self.rosters['people'][i]) for i in pins],
                'facet':facet,'page':page,'page_size':size,'total':len(rows),'has_more':offset+size<len(rows),
                'items':[self.facet_item(facet,row) for row in rows[offset:offset+size]]}

    def query(self, request):
        value,catalog=self.load()
        try:
            exact(request,('revision','page','page_size','filters'))
            if (not integer(request['revision'],1,2**31-1) or not integer(request['page'],1,100000)
                    or not integer(request['page_size'],1,100)):raise Refused()
            if request['revision']!=value['revision']:raise Refused(409,'discovery_changed')
            filters=request['filters']
            if type(filters) is not dict:raise Refused()
            if set(filters)-set(FILTERS):raise Refused(422,'unsupported_filter')
            if set(filters)-set(value['enabled_filters']):raise Refused(422,'capability_unavailable')
            normalized={}
            for field, selection in filters.items():
                if field in ('people','tags'):
                    exact(selection,('ids','match'));ids(selection['ids'],20,self.rosters[field])
                    if not selection['ids'] or selection['match'] not in ('any','all'):raise Refused()
                    normalized[field]={'ids':sorted(selection['ids']),'match':selection['match']}
                elif field=='locations':
                    ids(selection,20,self.rosters[field])
                    if not selection:raise Refused()
                    normalized[field]=sorted(selection)
                elif field=='media':
                    if type(selection) is not list or not 1<=len(selection)<=3 or not all(s in ('photo','video','unsupported') for s in selection) or len(set(selection))!=len(selection):raise Refused()
                    normalized[field]=sorted(selection)
                elif field=='date':
                    exact(selection,('from','to'));first,last=day(selection['from']),day(selection['to'])
                    if (first is None and last is None) or (first is not None and last is not None and first>last):raise Refused()
                    normalized[field]=selection
                else:
                    text(selection,512,True);normalized[field]=fold(selection.strip())
        except Refused as error:
            if error.status in (409,422):raise
            raise Refused(400,'invalid_request') from None
        except (ValueError,TypeError,KeyError):raise Refused(400,'invalid_request') from None
        if request['revision']!=value['revision']:raise Refused(409,'discovery_changed')
        found=[];start=monotonic()
        for position,asset in enumerate(catalog['assets']):
            if position%512==0 and monotonic()-start>2:raise Refused(503,'search_budget_exceeded')
            row=self.rows.get(asset['id'])
            if 'media' in normalized and asset['kind'] not in normalized['media']:continue
            if row is None and set(normalized)-{'media'}:continue
            matches=True
            for field in ('people','tags'):
                if field in normalized:
                    selected=set(normalized[field]['ids'])
                    present=set(row['person_ids'] if field=='people' else (t['id'] for t in row['tags']))
                    if not (selected<=present if normalized[field]['match']=='all' else bool(selected&present)):matches=False
            if not matches:continue
            if 'locations' in normalized and not set(normalized['locations'])&set(row['location_ids']):continue
            if 'date' in normalized:
                chosen=row['taken_day'];bounds=normalized['date']
                if chosen is None or (bounds['from'] is not None and chosen<bounds['from']) or (bounds['to'] is not None and chosen>bounds['to']):continue
            if 'caption' in normalized and normalized['caption'] not in self.folded.get(asset['id'],''):continue
            found.append(asset)
        offset=(request['page']-1)*request['page_size']
        fingerprint=hashlib.sha256(json.dumps({'revision':value['revision'],'catalog_revision':catalog['revision'],'filters':normalized},sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()
        return {'version':1,'revision':value['revision'],'catalog_revision':catalog['revision'],
                'library':{'id':catalog['library_id'],'title':catalog['title']},'filter_fingerprint':fingerprint,
                'page':request['page'],'page_size':request['page_size'],'total':len(found),'has_more':offset+request['page_size']<len(found),
                'items':[asset_result(a,catalog['revision']) for a in found[offset:offset+request['page_size']]]}


class DiscoveryComposition:
    """Path dispatch only; each child independently enforces its reviewed boundary."""
    def __init__(self, discovery, catalog):self.discovery,self.catalog=discovery,catalog
    async def __call__(self, scope, receive, send):
        child=self.discovery if scope.get('path','').startswith(PREFIX) else self.catalog
        await child(scope,receive,send)


def create_home_discovery(config, index_path: Path, index_sha256: str):
    if not isinstance(config,Configuration):raise ValueError('Explicit TV configuration required')
    index=DiscoveryIndex(Publication(config),index_path,index_sha256)
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

    @app.get('/home/discovery/v1/facets')
    async def facets(request: Request):
        def read():
            query=parameters(request,('facet','page','page_size','revision'));facet=query.get('facet','people')
            page=number(query.get('page','1'),5000);size=number(query.get('page_size','50'),100)
            revision=number(query['revision'],2**31-1) if 'revision' in query else None
            if facet not in ('people','tags','locations') or 'range' in request.headers or 'if-range' in request.headers:raise Refused(400,'invalid_request')
            if page>1 and revision is None:raise Refused(400,'revision_required')
            return index.facets(facet,page,size,revision)
        return await run_in_threadpool(perform,read)

    @app.post('/home/discovery/v1/search')
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
    return DiscoveryComposition(app,create_home_catalog(config))
