"""Opt-in v3 delivery over a selected v2 catalog and a pinned private source index.

No database discovery, path URLs, public mount, or extension-only video admission.
The old v2 feed remains immutable and available on its existing deployment.
"""
import hashlib
import json
import os
from pathlib import Path
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .home_feed import HomeBoundary, LIMITS, Refused, bounded_read, exact, number, parameters, unique
from .home_catalog import (Publication, VideoReader, LeasedStream, CHUNK_BYTES, MAX_VIDEO,
                           asset_result, byte_range, digest, identity, integer)
from .photo_delivery import PHOTO_BYTES, PHOTO_PIXELS, PhotoCache, source_pin


class SourceIndex:
    def __init__(self, publication, path, sha256, roots, *, originals_allowed=False):
        if not digest(sha256) or type(originals_allowed) is not bool or not roots: raise ValueError('Explicit source policy required')
        self.publication, self.path, self.sha256, self.roots = publication, path, sha256, tuple(roots)
        from .home_feed import direct_path
        for root in self.roots: direct_path(root)
        direct_path(path)
        if any(path.is_relative_to(root) for root in self.roots): raise ValueError('Index must be outside originals')
        self.originals_allowed = originals_allowed
        self.entries = None
        self.lock = threading.Lock()

    def load(self):
        catalog = self.publication.load()
        with self.lock:
            if self.entries is None:
                before = identity(self.path)
                raw = bounded_read(self.path, 64*1024**2)
                if hashlib.sha256(raw).hexdigest() != self.sha256: raise Refused()
                data = json.loads(raw, object_pairs_hook=unique)
                exact(data, ('version','catalog_sha256','assets'))
                if type(data['version']) is not int or data['version'] != 1 or data['catalog_sha256'] != self.publication.pin['catalog_sha256'] or type(data['assets']) is not list: raise Refused()
                entries = {}
                for e in data['assets']:
                    exact(e, ('id','path','identity','kind','mime','width','height','duration_ms','audio_codec'))
                    if (not integer(e['id'],1,2**31-1) or e['id'] in entries or e['id'] not in self.publication.by_id
                        or e['kind'] != self.publication.by_id[e['id']]['kind']
                        or type(e['identity']) is not list or len(e['identity']) != 4
                        or any(type(v) is not int or v<0 for v in e['identity'])
                        or type(e['path']) is not str): raise Refused()
                    w,h=e['width'],e['height']
                    if not integer(w,1,32768) or not integer(h,1,32768): raise Refused()
                    if e['kind']=='photo':
                        if e['mime'] not in ('image/jpeg','image/png') or w*h>PHOTO_PIXELS or not 0<e['identity'][2]<=PHOTO_BYTES or e['duration_ms'] is not None or e['audio_codec'] is not None: raise Refused()
                    elif e['kind']=='video':
                        if e['mime']!='video/mp4' or max(w,h)>1920 or w*h>2073600 or not 0<e['identity'][2]<=MAX_VIDEO or not integer(e['duration_ms'],1,86400000) or e['audio_codec'] not in ('aac',None): raise Refused()
                    else: raise Refused()
                    # Validate path syntax here, existence on byte admission; one missing
                    # original must not prevent the rest of the catalog from browsing.
                    from .home_feed import direct_path
                    direct_path(Path(e['path']))
                    if not any(Path(e['path']).is_relative_to(p) for p in self.roots): raise Refused()
                    entries[e['id']]=e
                if identity(self.path)!=before: raise Refused()
                self.entries,self.pin=entries,before
            if identity(self.path)!=self.pin: raise Refused(503,'source_index_changed')
        return catalog

    def entry(self, aid, revision):
        self.load(); self.publication.asset(aid,revision)
        return self.entries.get(aid)

    def result(self, asset, revision):
        value=asset_result(asset,revision)
        for p in value['previews'].values():
            if 'url' in p:p['url']=p['url'].replace('/v2/','/v3/')
        if value['video'] and 'url' in value['video']:value['video']['url']=value['video']['url'].replace('/v2/','/v3/')
        value['original']=None
        e=self.entries.get(asset['id'])
        if e:
            if e['kind']=='photo':
                for variant,p in value['previews'].items():
                    if p['state']=='unavailable':
                        value['previews'][variant]={'state':'on_demand','url':f"/home/v3/assets/{asset['id']}/preview?variant={variant}&revision={revision}"}
                if self.originals_allowed:
                    value['original']={'mime':e['mime'],'bytes':e['identity'][2],'width':e['width'],'height':e['height'],
                        'url':f"/home/v3/assets/{asset['id']}/original?revision={revision}"}
                    value['originals_allowed']=True
            elif self.originals_allowed and value['video']['state']=='unavailable':
                value['video']={'state':'direct','mime':'video/mp4','video_codec':'h264','audio_codec':e['audio_codec'],
                    'width':e['width'],'height':e['height'],'duration_ms':e['duration_ms'],'bytes':e['identity'][2],
                    'url':f"/home/v3/assets/{asset['id']}/video?revision={revision}"}
                value['originals_allowed']=True
        return value


class OriginalReader:
    def __init__(self, entry, roots):
        self.path=Path(entry['path']);self.roots=roots;self.pin=entry['identity']
        source_pin(self.path,roots,self.pin)
        flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)
        self.stream=os.fdopen(os.open(self.path,flags),'rb')
        info=os.fstat(self.stream.fileno())
        if list((info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns))!=self.pin:
            self.close();raise Refused(409,'source_changed')
    def chunk(self,index):
        source_pin(self.path,self.roots,self.pin)
        self.stream.seek(index*CHUNK_BYTES);raw=self.stream.read(min(CHUNK_BYTES,self.pin[2]-index*CHUNK_BYTES))
        source_pin(self.path,self.roots,self.pin)
        return raw
    def close(self):self.stream.close()


def create_home_originals(config, sources, cache):
    if cache.root.is_relative_to(config.media_root) or config.media_root.is_relative_to(cache.root) or config.manifest.is_relative_to(cache.root) or sources.path.is_relative_to(cache.root):
        raise ValueError('Cache must be separate from existing publication and index')
    app=FastAPI(openapi_url=None,docs_url=None,redoc_url=None,redirect_slashes=False)
    slots=threading.BoundedSemaphore(4)
    def perform(action):
        if not slots.acquire(False):return JSONResponse({'error':'busy'},429,headers={'Retry-After':'2'})
        leased=False
        try:
            response=action();leased=isinstance(response,LeasedStream);return response
        except Refused as e:return JSONResponse({'error':e.code},e.status,headers={'Retry-After':'2'} if e.status==429 else {})
        except (OSError,ValueError,TypeError,KeyError):return JSONResponse({'error':'media_unavailable'},503)
        finally:
            if not leased:slots.release()

    @app.get('/home/v3/catalog')
    async def catalog(request:Request):
        def read():
            q=parameters(request,('page','page_size','revision'));page=number(q.get('page','1'),100000);size=number(q.get('page_size','50'),100)
            revision=number(q['revision'],2**31-1) if 'revision' in q else None
            if page>1 and revision is None:raise Refused(400,'revision_required')
            if 'range' in request.headers or 'if-range' in request.headers:raise Refused(400,'invalid_request')
            c=sources.load()
            if revision is not None and revision!=c['revision']:raise Refused(409,'feed_changed')
            offset=(page-1)*size;assets=c['assets']
            result=JSONResponse({'version':3,'revision':c['revision'],'library':{'id':c['library_id'],'title':c['title']},
                'page':page,'page_size':size,'total':len(assets),'has_more':offset+size<len(assets),
                'items':[sources.result(a,c['revision']) for a in assets[offset:offset+size]]})
            if len(result.body)>524288:raise Refused()
            return result
        return await run_in_threadpool(perform,read)

    @app.get('/home/v3/assets/{asset_id}/preview')
    @app.head('/home/v3/assets/{asset_id}/preview')
    async def preview(asset_id:str,request:Request):
        def read():
            q=parameters(request,('variant','revision'));aid=number(asset_id,2**31-1);rev=number(q.get('revision'),2**31-1);v=q.get('variant')
            if v not in LIMITS or 'range' in request.headers or 'if-range' in request.headers:raise Refused(400,'invalid_request')
            e=sources.entry(aid,rev);asset=sources.publication.asset(aid,rev);meta=asset['previews'][v]
            if meta['state']=='ready':
                raw=bounded_read(config.media_root/v/f'{aid}.jpg',meta['bytes'])
                if hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise Refused()
            elif e and e['kind']=='photo':raw=cache.render(Path(e['path']),sources.roots,e['identity'],v)
            else:raise Refused(404,'preview_unavailable')
            PhotoCache.validate(raw,v);sources.entry(aid,rev)
            return Response(raw,media_type='image/jpeg',headers={'Accept-Ranges':'none'})
        return await run_in_threadpool(perform,read)

    def stream(request,asset_id,original):
        q=parameters(request,('revision',));aid=number(asset_id,2**31-1);rev=number(q.get('revision'),2**31-1)
        e=sources.entry(aid,rev);a=sources.publication.asset(aid,rev)
        prepared=None if original else a['video']
        if prepared and prepared['state']=='ready':
            size=prepared['bytes'];mime='video/mp4';factory=lambda:VideoReader(config,aid,prepared)
        elif sources.originals_allowed and e and e['kind']==('photo' if original else 'video'):
            size=e['identity'][2];mime=e['mime'];factory=lambda:OriginalReader(e,sources.roots)
        else:raise Refused(404,'media_unavailable')
        if 'if-range' in request.headers or len(request.headers.getlist('range'))>1:raise Refused(400,'invalid_request')
        try:start,end,status=byte_range(request.headers.get('range') if request.method=='GET' else None,size)
        except Refused:return JSONResponse({'error':'range_not_satisfiable'},416,headers={'Content-Range':f'bytes */{size}'})
        reader=factory()
        try:
            first=reader.chunk(start//CHUNK_BYTES)
            headers={'Content-Length':str(end-start+1),'Accept-Ranges':'bytes'}
            if status==206:headers['Content-Range']=f'bytes {start}-{end}/{size}'
            if request.method=='HEAD':reader.close();return Response(status_code=status,media_type=mime,headers=headers)
            def chunks():
                for i in range(start//CHUNK_BYTES,end//CHUNK_BYTES+1):
                    sources.entry(aid,rev)
                    data=first if i==start//CHUNK_BYTES else reader.chunk(i)
                    yield data[max(start-i*CHUNK_BYTES,0):min(end-i*CHUNK_BYTES+1,len(data))]
            def cleanup():
                try:reader.close()
                finally:slots.release()
            return LeasedStream(chunks(),status_code=status,media_type=mime,headers=headers,cleanup=cleanup)
        except BaseException:reader.close();raise

    @app.get('/home/v3/assets/{asset_id}/original')
    @app.head('/home/v3/assets/{asset_id}/original')
    async def original(asset_id:str,request:Request):return await run_in_threadpool(perform,lambda:stream(request,asset_id,True))
    @app.get('/home/v3/assets/{asset_id}/video')
    @app.head('/home/v3/assets/{asset_id}/video')
    async def video(asset_id:str,request:Request):return await run_in_threadpool(perform,lambda:stream(request,asset_id,False))
    reviewed=frozenset((m,r.path,r.endpoint) for r in app.routes for m in r.methods)
    app.add_middleware(HomeBoundary,config=config,routes=app.routes,reviewed=reviewed)
    return app
