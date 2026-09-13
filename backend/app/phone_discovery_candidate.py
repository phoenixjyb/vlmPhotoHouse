"""Explicit candidate composition. No module-level app and no live runtime wiring."""
import re
from fastapi import FastAPI
from .access.boundary import ClosedBoundary
from .access.transport import router as account_router
from .access.media import router as media_router
from .access.library import router as library_router
from .access.members import router as member_router
from .routers.ui import router as ui_router
from .access.discovery_transport import router as discovery_router, DiscoveryRuntime


class CandidateBoundary(ClosedBoundary):
    REVIEWED = ClosedBoundary.REVIEWED | {(method,route.path,route.endpoint)
        for route in discovery_router.routes for method in route.methods}

    @classmethod
    def allowed(cls, method, path):
        return ClosedBoundary.allowed(method,path) or bool(
            (method=='GET' and re.fullmatch(r'/libraries/[^/]+/discovery/v1/facets',path)) or
            (method=='POST' and re.fullmatch(r'/libraries/[^/]+/discovery/v1/search',path)))


def create_candidate(*, discovery_runtime, media_runtime=None):
    if not isinstance(discovery_runtime, DiscoveryRuntime): raise ValueError('Explicit candidate runtime required')
    app=FastAPI(openapi_url=None,docs_url=None,redoc_url=None,redirect_slashes=False)
    app.state.access_runtime=discovery_runtime.access
    app.state.discovery_runtime=discovery_runtime
    app.state.media_runtime=media_runtime
    app.include_router(account_router)
    app.include_router(media_router)
    app.include_router(library_router)
    app.include_router(member_router)
    app.include_router(ui_router)
    app.include_router(discovery_router)
    app.add_middleware(CandidateBoundary,routes=app.routes)
    return app
