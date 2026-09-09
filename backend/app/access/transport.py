"""Shared account router for web and native clients in the closed application.

No settings/database factory, app construction, startup, providers or model imports.
Integration must explicitly supply app.state.access_runtime.
This router alone provides no protection to routes outside it.
"""
from dataclasses import dataclass
import hashlib
import hmac
import json
import sqlite3
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

from .admission import Admission, AdmissionDenied
from .credentials import session_digest
from .service import AccessDenied, AccessService, Conflict

COOKIE = '__Host-ph_session'
MAX_BODY = 2048
PRIVACY_HEADERS = {'Cache-Control': 'no-store', 'Pragma': 'no-cache',
                   'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff'}


@dataclass(frozen=True)
class AccessRuntime:
    """Explicit integration contract. Factory yields/closes a fresh connection.

    The connection is to PhotoHouse's existing SQLite DB, foreign_keys=ON, no
    pending transaction, no schema fallback. Open it inside the worker thread.
    web_origin is reviewed configuration, never derived from request headers.
    """
    connection_factory: object
    web_origin: str
    clock: object = time.time

    def __post_init__(self):
        parsed = urlsplit(self.web_origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or not callable(self.connection_factory)):
            raise ValueError('Explicit HTTPS web origin and connection factory required')

    def call(self, action, *args, source=None, **kwargs):
        # Opening/closing the connection and all SQL/KDF work happen on one thread.
        with self.connection_factory() as connection:
            service = AccessService(connection, clock=self.clock)
            if action in {'login', 'register'}:
                with Admission(service).attempt(source, args[0]):
                    return getattr(service, action)(*args, **kwargs)
            if action not in {'profile', 'logout', 'accept_invitation', 'invite', 'cancel_invitation'}:
                raise AccessDenied('Access denied')
            return getattr(service, action)(*args, **kwargs)


class TransportError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def _single(request, name):
    values = request.headers.getlist(name)
    if len(values) > 1:
        raise TransportError(400, 'Invalid request')
    return values[0] if values else None


def _runtime(request, *, allow_query=False):
    runtime = getattr(request.app.state, 'access_runtime', None)
    if not isinstance(runtime, AccessRuntime):
        raise TransportError(503, 'Access unavailable')
    if (request.url.scheme != 'https'
            or _single(request, 'host') != urlsplit(runtime.web_origin).netloc):
        raise TransportError(400, 'Invalid request')
    origin = _single(request, 'origin')
    if origin is not None and origin != runtime.web_origin:
        raise TransportError(403, 'Access denied')
    if _single(request, 'sec-fetch-site') not in (None, 'same-origin', 'none'):
        raise TransportError(403, 'Access denied')
    # No query strings on account endpoints: no tokens, passwords or phone labels
    # in URLs, and no ignored credential/redirect parameters.
    if request.scope.get('query_string') and not allow_query:
        raise TransportError(400, 'Invalid request')
    return runtime


def _cookie(request):
    # Reject duplicate/malformed security cookies instead of first/last-wins parsing.
    values = []
    for header in request.headers.getlist('cookie'):
        for item in header.split(';'):
            name, separator, value = item.strip().partition('=')
            if name == COOKIE:
                if not separator:
                    raise TransportError(401, 'Access denied')
                values.append(value)
    if len(values) > 1:
        raise TransportError(401, 'Access denied')
    return values[0] if values else None


def csrf_token(token):
    return hmac.new(token.encode('ascii'), b'PhotoHouse web CSRF v1', hashlib.sha256).hexdigest()


def credentials_from_request(request, *, allow_query=False):
    """Parse transport credentials, NOT an authorization grant. Always call policy."""
    runtime = _runtime(request, allow_query=allow_query)
    authorization, cookie = _single(request, 'authorization'), _cookie(request)
    if authorization is not None and cookie is not None:
        raise TransportError(401, 'Access denied')
    if authorization is not None:
        if _single(request, 'origin') is not None or not authorization.startswith('Bearer '):
            raise TransportError(401, 'Access denied')
        token, mode = authorization[7:], 'native'
    elif cookie is not None:
        token, mode = cookie, 'web'
    else:
        raise TransportError(401, 'Access denied')
    try:
        session_digest(token)
    except ValueError:
        raise TransportError(401, 'Access denied') from None
    if mode == 'web' and request.method not in {'GET', 'HEAD'}:
        supplied = _single(request, 'x-csrf-token') or ''
        if (_single(request, 'origin') != runtime.web_origin or not supplied.isascii()
                or not hmac.compare_digest(supplied, csrf_token(token))):
            raise TransportError(403, 'Access denied')
    return token, mode


async def _body(request, fields):
    if _single(request, 'content-encoding') is not None:
        raise TransportError(400, 'Invalid request')
    if (_single(request, 'content-type') or '').split(';')[0].strip().lower() != 'application/json':
        raise TransportError(400, 'Invalid request')
    length = _single(request, 'content-length')
    if length is not None and (not length.isascii() or not length.isdecimal() or int(length) > MAX_BODY):
        raise TransportError(413, 'Request too large')
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BODY:
            raise TransportError(413, 'Request too large')
        raw.extend(chunk)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate field')
            result[key] = value
        return result
    try:
        body = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(body, dict) or set(body) != set(fields):
            raise ValueError('Invalid fields')
        if any(not isinstance(value, str) for value in body.values()):
            raise ValueError('Invalid value')
        # Reject surrogate code points before KDF/SQL encoding, without echoing input.
        for value in body.values():
            value.encode('utf-8')
        return body
    except (ValueError, UnicodeError, RecursionError):
        raise TransportError(400, 'Invalid request') from None


class AccessRoute(APIRoute):
    allow_query = False

    def get_route_handler(self):
        handler = super().get_route_handler()
        async def guarded(request):
            try:
                _runtime(request, allow_query=self.allow_query)
                response = await handler(request)
            except TransportError as exc:
                response = JSONResponse({'detail': exc.message}, status_code=exc.status)
            except AdmissionDenied:
                response = JSONResponse({'detail': 'Try again later'}, status_code=429,
                                        headers={'Retry-After': str(Admission.WINDOW_SECONDS)})
            except (AccessDenied, ValueError):
                response = JSONResponse({'detail': 'Access denied'}, status_code=401)
            except Conflict:
                response = JSONResponse({'detail': 'Refresh account state'}, status_code=409)
            except sqlite3.Error:
                response = JSONResponse({'detail': 'Access unavailable'}, status_code=503)
            except Exception:
                # Do not delegate connection/provider errors containing private
                # parameters to main.py's legacy str(exception) response handler.
                response = JSONResponse({'detail': 'Access unavailable'}, status_code=503)
            for key, value in PRIVACY_HEADERS.items():
                response.headers[key] = value
            return response
        return guarded


router = APIRouter(route_class=AccessRoute)


async def _sign_in(request, registration=False):
    runtime = _runtime(request)
    if _single(request, 'authorization') is not None or _cookie(request) is not None:
        raise TransportError(401, 'Access denied')
    fields = {'phone', 'password', 'transport'} | ({'code'} if registration else set())
    body = await _body(request, fields)
    mode = body['transport']
    origin = _single(request, 'origin')
    if mode not in {'web', 'native'} or (mode == 'web' and origin != runtime.web_origin) or (mode == 'native' and origin is not None):
        raise TransportError(403, 'Access denied')
    if request.client is None:
        raise TransportError(503, 'Access unavailable')
    args = [body['phone'], body['password']] + ([body['code']] if registration else [])
    token = await run_in_threadpool(runtime.call, 'register' if registration else 'login',
                                   *args, source=request.client.host)
    result = {'expires_in': AccessService.SESSION_SECONDS}
    if mode == 'native':
        result.update(access_token=token, token_type='Bearer')
    else:
        result['csrf_token'] = csrf_token(token)
    response = JSONResponse(result, status_code=201 if registration else 200)
    if mode == 'web':
        response.set_cookie(COOKIE, token, max_age=AccessService.SESSION_SECONDS,
                            path='/', secure=True, httponly=True, samesite='strict')
    return response


@router.post('/auth/login')
async def login(request: Request):
    return await _sign_in(request)


@router.post('/auth/register')
async def register(request: Request):
    return await _sign_in(request, registration=True)


@router.get('/auth/session')
async def session(request: Request):
    token, mode = credentials_from_request(request)
    result = await run_in_threadpool(_runtime(request).call, 'profile', token)
    if mode == 'web':
        result['csrf_token'] = csrf_token(token)
    return JSONResponse(result)


@router.post('/auth/logout')
async def logout(request: Request):
    token, mode = credentials_from_request(request)
    # Idempotent revocation, including expired sessions. CSRF still required for web.
    await run_in_threadpool(_runtime(request).call, 'logout', token)
    response = JSONResponse({'ok': True})
    if mode == 'web':
        response.delete_cookie(COOKIE, path='/', secure=True, httponly=True, samesite='strict')
    return response


@router.post('/auth/invitations/accept')
async def accept_invitation(request: Request):
    token, _ = credentials_from_request(request)
    body = await _body(request, {'code'})
    await run_in_threadpool(_runtime(request).call, 'accept_invitation', token, body['code'])
    return JSONResponse({'ok': True})


@router.post('/libraries/{library_id}/invitations')
async def invite(library_id: str, request: Request):
    token, _ = credentials_from_request(request)
    body = await _body(request, {'phone'})
    code = await run_in_threadpool(_runtime(request).call, 'invite', token, library_id, body['phone'])
    return JSONResponse({'code': code, 'expires_in': 86400}, status_code=201)


@router.post('/libraries/{library_id}/invitations/cancel')
async def cancel_invitation(library_id: str, request: Request):
    token, _ = credentials_from_request(request)
    body = await _body(request, {'code'})
    await run_in_threadpool(_runtime(request).call, 'cancel_invitation', token, library_id, body['code'])
    return JSONResponse({'ok': True})
