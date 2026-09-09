"""PhotoHouse HTTP entry point: no configuration, storage or worker side effects.

The application starts closed. Deployment must explicitly supply reviewed access
and media runtimes; no environment/database discovery or legacy fallback exists.
"""
from fastapi import FastAPI
from .access.transport import router as account_router
from .access.media import router as media_router
from .access.boundary import ClosedBoundary
from .routers.ui import router as ui_router


def create_app(*, access_runtime=None, media_runtime=None):
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, redirect_slashes=False)
    app.state.access_runtime = access_runtime
    app.state.media_runtime = media_runtime
    app.include_router(account_router)
    app.include_router(media_router)
    app.include_router(ui_router)
    app.add_middleware(ClosedBoundary, routes=app.routes)
    return app


app = create_app()
