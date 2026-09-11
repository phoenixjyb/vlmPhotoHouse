"""Explicit unauthenticated, selected-content LAN feed; separate from app.main.

No accounts, SQLite, original-media paths, workers or configuration discovery.
Operator publishes an atomic private manifest and prepared, hash-bound JPEGs.
"""
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import threading
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.routing import Match

VERSION = 1
MAX_MANIFEST = 2 * 1024 * 1024
MAX_ASSETS = 2000
LIMITS = {'grid': (512, 262144, 2 * 1024 * 1024),
          'display': (4096, 8847360, 12 * 1024 * 1024)}
PRIVATE = tuple(map(ipaddress.ip_network, ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')))
PRIVACY = {'Cache-Control': 'no-store', 'Pragma': 'no-cache',
           'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff',
           'Cross-Origin-Resource-Policy': 'same-origin'}


class Refused(Exception):
    def __init__(self, status=503, code='feed_unavailable'):
        self.status, self.code = status, code


def direct_path(path):
    if (not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts
            or path == Path(path.anchor) or str(path).startswith(('//', '\\\\'))):
        raise ValueError('Explicit direct local path required')
    return path


@dataclass(frozen=True, repr=False)
class Configuration:
    manifest: Path
    media_root: Path
    origin: str
    allowed_networks: tuple[str, ...]

    def __post_init__(self):
        direct_path(self.manifest); direct_path(self.media_root)
        if self.manifest == self.media_root or self.manifest.is_relative_to(self.media_root):
            raise ValueError('Manifest must be outside prepared media')
        parsed = urlsplit(self.origin)
        labels = (parsed.hostname or '').split('.')
        if (parsed.port == 0 or parsed.scheme != 'https' or len(labels) < 2 or parsed.path or parsed.query
                or parsed.fragment or parsed.username or parsed.password
                or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', s) for s in labels)
                or re.fullmatch(r'[0-9.]+', parsed.hostname or '')
                or self.origin != 'https://' + parsed.hostname + (f':{parsed.port}' if parsed.port not in (None,443) else '')):
            raise ValueError('Canonical DNS HTTPS origin required')
        if not isinstance(self.allowed_networks, tuple) or not 1 <= len(self.allowed_networks) <= 8:
            raise ValueError('Explicit narrow IPv4 LAN networks required')
        for value in self.allowed_networks:
            network = ipaddress.ip_network(value, strict=True)
            if (str(network) != value or network.version != 4 or network.prefixlen < 24
                    or not any(network.subnet_of(parent) for parent in PRIVATE)):
                raise ValueError('Only explicit RFC1918 /24 or narrower networks allowed')
        if len(set(self.allowed_networks)) != len(self.allowed_networks):
            raise ValueError('Duplicate network')


def bounded_read(path, maximum):
    """Reject aliases/changed identities; never return more than the budget."""
    direct_path(path)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or path.resolve(strict=True) != path
            or not 0 < before.st_size <= maximum):
        raise Refused()
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise Refused()
        value = stream.read(maximum + 1)
        after = path.stat()
        if (len(value) != before.st_size or len(value) > maximum or path.resolve(strict=True) != path
                or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) !=
                   (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)):
            raise Refused()
    return value


def jpeg_dimensions(data):
    """Validate normalized baseline JPEG framing/dimensions without decoding.

    APP0/JFIF only: reject EXIF, ICC, comments and other attached metadata. Full
    decode/color/orientation preparation is offline; clients still bound decoding.
    """
    if not data.startswith(b'\xff\xd8'): raise Refused()
    pos, dimensions, scanning = 2, None, False
    while pos < len(data):
        if scanning:
            pos = data.find(b'\xff', pos)
            if pos < 0: raise Refused()
        if data[pos] != 255: raise Refused()
        while pos < len(data) and data[pos] == 255: pos += 1
        if pos >= len(data): raise Refused()
        marker = data[pos]; pos += 1
        if scanning and (marker == 0 or 208 <= marker <= 215): continue
        if marker == 217:
            if pos != len(data) or not scanning or dimensions is None: raise Refused()
            return dimensions
        if scanning or marker not in (192,196,219,221,224,218): raise Refused()
        length = int.from_bytes(data[pos:pos+2], 'big')
        if length < 2 or pos + length > len(data): raise Refused()
        segment = data[pos+2:pos+length]
        if marker == 192:
            if (dimensions is not None or len(segment) < 6 or segment[0] != 8
                    or segment[5] not in (1,3) or len(segment) != 6+3*segment[5]): raise Refused()
            dimensions = (int.from_bytes(segment[3:5],'big'), int.from_bytes(segment[1:3],'big'))
        if marker == 224 and (not segment.startswith(b'JFIF\0') or len(segment)!=14 or segment[-2:]!=b'\0\0'): raise Refused()
        if marker == 218:
            if dimensions is None: raise Refused()
            scanning = True
        pos += length
    raise Refused()


def exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise Refused()


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def literal(value, maximum):
    return (type(value) is str and len(value.encode('utf-8')) <= maximum
            and not any(ord(c) < 32 and c not in '\n\t' for c in value))


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise Refused()
        value[key] = item
    return value


def load_manifest(config):
    value = json.loads(bounded_read(config.manifest, MAX_MANIFEST), object_pairs_hook=unique)
    exact(value, ('version','enabled','revision','feed_id','title','assets'))
    if (type(value['version']) is not int or value['version'] != VERSION
            or type(value['enabled']) is not bool or not integer(value['revision'],1,2**31-1)
            or type(value['feed_id']) is not str or not re.fullmatch(r'[a-z0-9-]{1,64}', value['feed_id'])
            or not literal(value['title'],256) or type(value['assets']) is not list
            or len(value['assets']) > MAX_ASSETS):
        raise Refused()
    seen = set()
    for asset in value['assets']:
        exact(asset, ('id','caption','previews'))
        if not integer(asset['id'],1,2**31-1) or asset['id'] in seen or not literal(asset['caption'],1024):
            raise Refused()
        seen.add(asset['id']); exact(asset['previews'], LIMITS)
        for variant, (edge, pixels, maximum) in LIMITS.items():
            preview = asset['previews'][variant]
            exact(preview, ('width','height','bytes','sha256'))
            if (not integer(preview['width'],1,edge) or not integer(preview['height'],1,edge)
                    or preview['width']*preview['height'] > pixels or not integer(preview['bytes'],1,maximum)
                    or type(preview['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', preview['sha256'])):
                raise Refused()
    if not value['enabled']:
        raise Refused(403, 'feed_disabled')
    return value


def parameters(request, fields):
    pairs = list(request.query_params.multi_items())
    if len(pairs) != len(dict(pairs)) or set(dict(pairs)) - set(fields):
        raise Refused(400,'invalid_request')
    return dict(pairs)


def number(text, high):
    if type(text) is not str or not re.fullmatch('[1-9][0-9]{0,9}',text) or int(text) > high:
        raise Refused(400,'invalid_request')
    return int(text)


def asset_result(asset, revision):
    return {'id':asset['id'],'caption':asset['caption'],'originals_allowed':False,
        'previews':{variant:dict(meta,url=f"/home/v1/assets/{asset['id']}/preview?variant={variant}&revision={revision}")
                    for variant,meta in asset['previews'].items()}}


class HomeBoundary:
    def __init__(self, app, *, config, routes, reviewed):
        self.app, self.config, self.routes, self.reviewed = app, config, routes, reviewed

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'websocket':
            await send({'type':'websocket.close','code':1008}); return
        if scope['type'] != 'http':
            await self.app(scope, receive, send); return
        async def private_send(message):
            if message['type'] == 'http.response.start':
                message = dict(message)
                headers = {k.lower().encode():v.encode() for k,v in PRIVACY.items()}
                message['headers'] = [(k,v) for k,v in message.get('headers',[]) if k.lower() not in headers]
                message['headers'].extend(headers.items())
            if message['type'] == 'http.response.body' and scope['method'] == 'HEAD':
                message = dict(message,body=b'')
            await send(message)
        try:
            peer = ipaddress.ip_address(scope['client'][0])
            if not any(peer in ipaddress.ip_network(net) for net in self.config.allowed_networks):
                raise ValueError()
            request = Request(scope)
            if (scope['scheme'] != 'https' or request.headers.getlist('host') != [urlsplit(self.config.origin).netloc]
                    or request.headers.get('origin') not in (None,self.config.origin)
                    or request.headers.get('sec-fetch-site') not in (None,'none','same-origin')
                    or 'authorization' in request.headers or 'cookie' in request.headers
                    or len(scope.get('query_string',b'')) > 1024):
                raise ValueError()
            matched = next((route for route in self.routes if route.matches(scope)[0] == Match.FULL), None)
            if matched is None or (scope['method'],matched.path,matched.endpoint) not in self.reviewed:
                raise ValueError()
        except (ValueError,TypeError,KeyError,AttributeError):
            await JSONResponse({'error':'access_denied'},status_code=403)(scope,receive,private_send);return
        await self.app(scope,receive,private_send)


def create_home_feed(config):
    """Explicit separate app only. Construction performs no storage or network I/O."""
    if not isinstance(config,Configuration): raise ValueError('Explicit home feed configuration required')
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, redirect_slashes=False)
    slots = threading.BoundedSemaphore(4)

    def perform(action):
        if not slots.acquire(blocking=False):
            return JSONResponse({'error':'busy'},status_code=429,headers={'Retry-After':'2'})
        try:
            return action()
        except Refused as error:
            return JSONResponse({'error':error.code},status_code=error.status)
        except (OSError,ValueError,TypeError,KeyError,RecursionError):
            return JSONResponse({'error':'feed_unavailable'},status_code=503)
        finally:
            slots.release()

    @app.get('/home/v1/feed')
    async def feed(request: Request):
        def read():
            query = parameters(request, ('page','page_size'))
            page,size = number(query.get('page','1'),2000), number(query.get('page_size','50'),100)
            manifest = load_manifest(config); assets = manifest['assets']; offset = (page-1)*size
            body = {'version':VERSION,'revision':manifest['revision'],
                'feed':{'id':manifest['feed_id'],'title':manifest['title']},
                'page':page,'page_size':size,'total':len(assets),'has_more':offset+size<len(assets),
                'items':[asset_result(a,manifest['revision']) for a in assets[offset:offset+size]]}
            response = JSONResponse(body)
            if len(response.body) > 524288: raise Refused()
            return response
        return await run_in_threadpool(perform,read)

    @app.get('/home/v1/assets/{asset_id}/preview')
    @app.head('/home/v1/assets/{asset_id}/preview')
    async def preview(asset_id: str, request: Request):
        def read():
            query = parameters(request, ('variant','revision'))
            variant = query.get('variant'); asset_number = number(asset_id,2**31-1)
            revision = number(query.get('revision'),2**31-1)
            if variant not in LIMITS or 'range' in request.headers or 'if-range' in request.headers:
                raise Refused(400,'invalid_request')
            manifest = load_manifest(config)
            if revision != manifest['revision']: raise Refused(409,'feed_changed')
            asset = next((a for a in manifest['assets'] if a['id']==asset_number),None)
            if asset is None: raise Refused(404,'preview_unavailable')
            meta = asset['previews'][variant]
            path = config.media_root / variant / f'{asset_number}.jpg'
            try: data = bounded_read(path,meta['bytes'])
            except FileNotFoundError: raise Refused(404,'preview_unavailable') from None
            if (len(data)!=meta['bytes'] or hashlib.sha256(data).hexdigest()!=meta['sha256']
                    or jpeg_dimensions(data) != (meta['width'],meta['height'])):
                raise Refused()
            return Response(data,media_type='image/jpeg',headers={'Accept-Ranges':'none'})
        return await run_in_threadpool(perform,read)

    reviewed = frozenset((method,route.path,route.endpoint) for route in app.routes for method in route.methods)
    app.add_middleware(HomeBoundary,config=config,routes=app.routes,reviewed=reviewed)
    return app
