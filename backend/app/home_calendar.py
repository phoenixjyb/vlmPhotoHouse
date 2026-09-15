"""Explicit calendar browsing over the same immutable Home tag/search snapshot."""
import calendar
from collections import defaultdict
from datetime import date
import hashlib
import json
import threading
from time import monotonic
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .home_feed import HomeBoundary, Refused, number, parameters
from .home_tag_discovery import TagIndex, create_home_tag_discovery

PATH = '/home/discovery/v3/calendar'
BINDING_FIELDS = ('revision','catalog_revision','library','capabilities','pinned_person_ids','pinned_people')

class CalendarIndex(TagIndex):
    def calendar(self, year, month, page, size, revision):
        started = monotonic()
        value, catalog = self.load()
        if revision != value['revision']: raise Refused(409,'discovery_changed')
        if 'date' not in value['enabled_filters']: raise Refused(400,'filter_unavailable')
        if month is not None and year is None: raise Refused(400,'invalid_request')
        facet = self.facets('people',1,50,revision)
        binding = hashlib.sha256(json.dumps({k:facet[k] for k in BINDING_FIELDS},
            sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        groups = defaultdict(list); dated = 0
        for i,row in enumerate(value['assets']):
            if i%256==0 and monotonic()-started>5: raise Refused(503,'discovery_unavailable')
            day = row['taken_day']
            if day is None: continue
            dated += 1
            if year is not None and int(day[:4]) != year: continue
            if month is not None and int(day[5:7]) != month: continue
            key = day if month is not None else day[:7] if year is not None else day[:4]
            groups[key].append(row['id'])
        keys = sorted(groups,reverse=True); items=[]
        for key in keys[(page-1)*size:page*size]:
            if monotonic()-started>5:raise Refused(503,'discovery_unavailable')
            y=int(key[:4]);m=int(key[5:7]) if len(key)>=7 else None
            start = key if len(key)==10 else key+'-01' if m else key+'-01-01'
            end = key if len(key)==10 else f'{key}-{calendar.monthrange(y,m)[1]:02}' if m else key+'-12-31'
            cover = None
            # Choose at most eight candidates; never walk all original files to choose a cover.
            for aid in sorted(groups[key],reverse=True)[:8]:
                item=self.media_sources.result(self.publication.asset(aid,catalog['revision']),catalog['revision'])
                if item['previews']['grid']['state'] in ('ready','on_demand'):
                    cover=item;break
            items.append(dict(key=key,from_date=start,through_date=end,count=len(groups[key]),cover=cover))
        self.load()
        if monotonic()-started>5:raise Refused(503,'discovery_unavailable')
        return dict(version=1,revision=revision,catalog_revision=catalog['revision'],binding=binding,
            library=facet['library'],level='day' if month is not None else 'month' if year is not None else 'year',
            year=year,month=month,page=page,page_size=size,total=len(keys),has_more=page*size<len(keys),
            dated_assets=dated,undated_assets=len(catalog['assets'])-dated,items=items)

class CalendarComposition:
    def __init__(self, calendar_app, legacy): self.calendar_app,self.legacy=calendar_app,legacy
    async def __call__(self,scope,receive,send):
        child=self.calendar_app if scope.get('path','').startswith(PATH) else self.legacy
        await child(scope,receive,send)

def create_home_calendar(config,sources,cache,index_path,index_sha256,legacy_path,legacy_sha256):
    legacy=create_home_tag_discovery(config,sources,cache,index_path,index_sha256,legacy_path,legacy_sha256)
    index=CalendarIndex(sources,index_path,index_sha256)
    app=FastAPI(openapi_url=None,docs_url=None,redoc_url=None,redirect_slashes=False)
    slots=threading.BoundedSemaphore(2)
    @app.get('/home/discovery/v3/calendar')
    async def calendar_view(request: Request):
        def read():
            if not slots.acquire(blocking=False): return JSONResponse({'error':'busy'},status_code=429,headers={'Retry-After':'2'})
            try:
                q=parameters(request,('year','month','page','page_size','revision'))
                if 'revision' not in q or 'range' in request.headers or 'if-range' in request.headers: raise Refused(400,'invalid_request')
                result=index.calendar(number(q['year'],9999) if 'year' in q else None,
                    number(q['month'],12) if 'month' in q else None,number(q.get('page','1'),1000),
                    number(q.get('page_size','12'),12),number(q['revision'],2**31-1))
                response=JSONResponse(result)
                if len(response.body)>524288: raise Refused()
                return response
            except Refused as e: return JSONResponse({'error':e.code},status_code=e.status)
            except (OSError,ValueError,TypeError,KeyError,RecursionError): return JSONResponse({'error':'discovery_unavailable'},status_code=503)
            finally: slots.release()
        return await run_in_threadpool(read)
    reviewed=frozenset((method,route.path,route.endpoint) for route in app.routes for method in route.methods)
    app.add_middleware(HomeBoundary,config=config,routes=app.routes,reviewed=reviewed)
    return CalendarComposition(app,legacy)
