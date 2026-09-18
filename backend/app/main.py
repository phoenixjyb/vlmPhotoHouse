"""PhotoHouse HTTP entry point: no configuration, storage or worker side effects.

The application starts closed. Deployment must explicitly supply reviewed access
and media runtimes; no environment/database discovery or legacy fallback exists.
"""
from fastapi import FastAPI
from .access.transport import router as account_router
from .access.media import router as media_router
from .access.library import router as library_router
from .access.members import router as member_router
from .access.stories import router as story_router
from .access.people import router as people_router
from .access.tags import router as tag_router
from .access.albums import router as album_router
from .access.boundary import ClosedBoundary
from .access.discovery_transport import router as discovery_router
from .access.upload_transport import router as upload_router
from .access.duplicates import router as duplicate_router
from .access.captions import router as caption_router
from .routers.ui import router as ui_router


def create_app(*, access_runtime=None, media_runtime=None, discovery_runtime=None,
               upload_runtime=None):
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, redirect_slashes=False)
    app.state.access_runtime = access_runtime
    app.state.media_runtime = media_runtime
    app.state.discovery_runtime = discovery_runtime
    app.state.upload_runtime = upload_runtime
    app.include_router(account_router)
    app.include_router(media_router)
    app.include_router(library_router)
    app.include_router(member_router)
    app.include_router(story_router)
    app.include_router(people_router)
    app.include_router(tag_router)
    app.include_router(album_router)
    app.include_router(ui_router)
    app.include_router(discovery_router)
    app.include_router(upload_router)
    app.include_router(duplicate_router)
    app.include_router(caption_router)
    app.add_middleware(ClosedBoundary, routes=app.routes)
    return app


app = create_app()
