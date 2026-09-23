"""Default-deny HTTP surface. Does not import the historical API or its workers."""
import re

from fastapi.responses import JSONResponse
from starlette.routing import Match

from .transport import PRIVACY_HEADERS, router as account_router
from .media import router as media_router
from .library import router as library_router
from .members import router as member_router
from .stories import router as story_router
from .people import router as people_router
from .tags import router as tag_router
from .albums import router as album_router
from .discovery_transport import router as discovery_router
from .upload_transport import router as upload_router
from .upload_review import router as upload_review_router
from .duplicates import router as duplicate_router
from .captions import router as caption_router
from .library_organization import router as organization_router
from ..routers.ui import router as ui_router


class ClosedBoundary:
    # Deliberately explicit: newly registered routes do not become reachable by
    # accident. The runtime inventory test checks both missing and extra entries.
    ACCOUNT = {
        ('POST', '/auth/login'), ('POST', '/auth/register'),
        ('GET', '/auth/session'), ('POST', '/auth/logout'),
        ('POST', '/auth/invitations/accept'),
    }
    UI = {'/ui', '/ui/app.js', '/ui/styles.css', '/ui/photohouse-icon.png', '/ui/search', '/ui/admin'}

    REVIEWED = {(method, route.path, route.endpoint)
                for router in (account_router, media_router, library_router, member_router, story_router, people_router, tag_router, album_router, ui_router, discovery_router, upload_router, upload_review_router, duplicate_router, caption_router, organization_router)
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
        if method == 'POST' and path == '/upload-sessions': return True
        if method in {'GET','PUT','DELETE'} and re.fullmatch(r'/upload-sessions/[0-9a-f]{32}',path): return True
        if method == 'POST' and re.fullmatch(r'/upload-sessions/[0-9a-f]{32}/complete',path): return True
        if method == 'GET' and path in ('/library-catalogue', '/admin/library-transfers'): return True
        if method == 'POST' and path in ('/admin/library-transfers/review', '/admin/library-transfers/confirm'): return True
        if method == 'GET' and (path == '/admin/uploads' or re.fullmatch(r'/admin/uploads/[0-9]+/preview', path)): return True
        if method == 'POST' and re.fullmatch(r'/admin/uploads/[0-9]+/(review|approve)', path): return True
        if method in {'GET', 'POST'} and path == '/uploads':
            # No library in the path: the upload is a pre-library action, so there is nothing
            # library-scoped for this pattern to bind. The capability is checked in the service.
            return True
        if method == 'GET' and path == '/library-albums': return True
        if method == 'POST' and path == '/admin/albums': return True
        if method == 'PUT' and re.fullmatch(r'/admin/albums/[0-9]+',path): return True
        if method == 'POST' and re.fullmatch(r'/admin/albums/[0-9]+/(archive|restore)',path): return True
        if method == 'POST' and re.fullmatch(r'/admin/faces/[0-9]+/(new-person|unassign)',path): return True
        if method == 'GET' and re.fullmatch(r'/admin/assets/[0-9]+/faces', path):
            return True
        if method == 'GET' and path == '/admin/faces':
            return True
        if method == 'POST' and re.fullmatch(r'/admin/faces/[0-9]+/assignment', path):
            return True
        if method == 'GET' and (path in ('/people', '/admin/people')
                                or re.fullmatch(r'/people/[0-9]+/assets', path)
                                or re.fullmatch(r'/admin/people/[0-9]+/faces', path)):
            return True
        if method == 'PUT' and re.fullmatch(r'/admin/people/[0-9]+', path):
            return True
        if method == 'POST' and re.fullmatch(r'/assets/[0-9]+/captions', path):
            return True
        if method == 'GET' and path == '/admin/albums/archived': return True
        if method == 'GET' and path == '/duplicates':
            return True
        if method == 'GET' and (path == '/tags' or re.fullmatch(r'/tags/[0-9]+/assets', path)):
            return True
        if method in {'GET', 'POST'} and re.fullmatch(r'/assets/[0-9]+/stories', path):
            return True
        if method in {'PUT', 'DELETE'} and re.fullmatch(r'/stories/[0-9a-f-]{36}', path):
            return True
        if method == 'GET' and re.fullmatch(r'/stories/[0-9a-f-]{36}/history', path):
            return True
        if method == 'POST' and path == '/library/search':
            return True
        if (method, path) in cls.ACCOUNT or (method == 'GET' and path in cls.UI):
            return True
        if method == 'POST' and re.fullmatch(r'/libraries/[^/]+/invitations(?:/cancel)?', path):
            return True
        if method == 'GET' and re.fullmatch(r'/libraries/[^/]+/members', path):
            return True
        if method == 'POST' and re.fullmatch(r'/libraries/[^/]+/members/[^/]+/revoke', path):
            return True
        if method == 'GET' and (path == '/assets' or re.fullmatch(r'/assets/(?:detail/[0-9]+|[0-9]+/captions)', path)):
            return True
        if method == 'GET' and re.fullmatch(r'/libraries/[^/]+/discovery/v1/facets', path):
            return True
        if method == 'POST' and re.fullmatch(r'/libraries/[^/]+/discovery/v1/search', path):
            return True
        return method in {'GET', 'HEAD'} and bool(re.fullmatch(
            r'/(?:assets/[0-9]+/(?:media|thumbnail|display|playback)|faces/[0-9]+/crop)', path))

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'websocket':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        if scope['type'] == 'http':
            async def private_send(message):
                if message['type'] == 'http.response.start':
                    message = dict(message)
                    privacy = {key.lower().encode(): value.encode() for key, value in PRIVACY_HEADERS.items()}
                    message['headers'] = [(k, v) for k, v in message.get('headers', []) if k.lower() not in privacy]
                    message['headers'].extend(privacy.items())
                elif message['type'] == 'http.response.body' and scope['method'] == 'HEAD':
                    message = dict(message, body=b'')
                await send(message)
            if not self.allowed(scope['method'], scope['path']) or not self.reviewed_match(scope):
                response = JSONResponse({'detail': 'Access denied'}, status_code=403,
                                        headers=PRIVACY_HEADERS)
                await response(scope, receive, private_send)
                return
            await self.app(scope, receive, private_send)
            return
        await self.app(scope, receive, send)
