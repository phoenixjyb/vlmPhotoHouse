from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter()

UI_DIR = Path(__file__).resolve().parents[1] / "ui"
INDEX_FILE = UI_DIR / "index.html"
APP_FILE = UI_DIR / "app.js"
STYLE_FILE = UI_DIR / "styles.css"
NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _ensure_ui_file(path: Path) -> Path:
    if not path.exists():
        raise HTTPException(status_code=500, detail=f"UI asset missing: {path.name}")
    return path

def _ui_file_response(path: Path, media_type: str) -> FileResponse:
    return FileResponse(str(_ensure_ui_file(path)), media_type=media_type, headers=NO_CACHE_HEADERS)


@router.get("/ui")
async def ui_home():
    return _ui_file_response(INDEX_FILE, "text/html")


@router.get("/ui/app.js")
async def ui_js():
    return _ui_file_response(APP_FILE, "application/javascript")


@router.get("/ui/styles.css")
async def ui_css():
    return _ui_file_response(STYLE_FILE, "text/css")


@router.get("/ui/search")
async def ui_search(q: str | None = Query(None)):
    query = {"tab": "library"}
    if q:
        query["q"] = q
    return RedirectResponse(url=f"/ui?{urlencode(query)}")


@router.get("/ui/admin")
async def ui_admin():
    return RedirectResponse(url="/ui?tab=admin")
