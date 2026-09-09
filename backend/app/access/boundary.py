"""Default-deny HTTP surface. Does not import the historical API or its workers."""
import re

from fastapi.responses import JSONResponse
from starlette.routing import Match

from .transport import PRIVACY_HEADERS, router as account_router
from .media import router as media_router
from .library import router as library_router
from ..routers.ui import router as ui_router


class ClosedBoundary:
    # Deliberately explicit: newly registered routes do not become reachable by
    # accident. The runtime inventory test checks both missing and extra entries.
    ACCOUNT = {
        ('POST', '/auth/login'), ('POST', '/auth/register'),
        ('GET', '/auth/session'), ('POST', '/auth/logout'),
        ('POST', '/auth/invitations/accept'),
    }
    UI = {'/ui', '/ui/app.js', '/ui/styles.css', '/ui/search', '/ui/admin'}

    REVIEWED = {(method, route.path, route.endpoint)
                for router in (account_router, media_router, library_router, ui_router)
                for route in router.routes for method in route.methods}

    def __init__(self, app, routes):
        self.app = app
        self.routes = routes

    def reviewed_match(self, scope):
        # Bind the allowlist to the handler as well as URL/method. An accidental
        # route that shadows an account/media URL cannot bypass policy.
        for route in self.routes:
            match, _ = route.matches(scope)
            if match == Match.FULL:
                return (scope['method'], getattr(route, 'path', None),
                        getattr(route, 'endpoint', None)) in self.REVIEWED
        return False

    @classmethod
    def allowed(cls, method, path):
        if (method, path) in cls.ACCOUNT or (method == 'GET' and path in cls.UI):
            return True
        if method == 'POST' and re.fullmatch(r'/libraries/[^/]+/invitations(?:/cancel)?', path):
            return True
        if method == 'GET' and (path == '/assets' or re.fullmatch(r'/assets/(?:detail/[0-9]+|[0-9]+/captions)', path)):
            return True
        return method in {'GET', 'HEAD'} and bool(re.fullmatch(
            r'/(?:assets/[0-9]+/(?:media|thumbnail)|faces/[0-9]+/crop)', path))

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'websocket':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        if scope['type'] == 'http':
            if not self.allowed(scope['method'], scope['path']) or not self.reviewed_match(scope):
                response = JSONResponse({'detail': 'Access denied'}, status_code=403,
                                        headers=PRIVACY_HEADERS)
                await response(scope, receive, send)
                return
            async def private_send(message):
                if message['type'] == 'http.response.start':
                    message = dict(message)
                    privacy = {key.lower().encode(): value.encode() for key, value in PRIVACY_HEADERS.items()}
                    message['headers'] = [(k, v) for k, v in message.get('headers', []) if k.lower() not in privacy]
                    message['headers'].extend(privacy.items())
                await send(message)
            await self.app(scope, receive, private_send)
            return
        await self.app(scope, receive, send)
