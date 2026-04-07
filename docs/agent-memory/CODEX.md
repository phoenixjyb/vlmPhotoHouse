# Codex Notes

Read first:

1. `docs\agent-memory\PROJECT_TRUTH.md`
2. `docs\agent-memory\STATUS_AND_PRODUCT_READINESS_2026-04-07.md`

Working rules for this repo:

- use `vlmPhotoHouse\.venv\Scripts\python.exe` for app work
- do not use `backend\.venv` for real runtime work
- verify runtime claims against code plus `curl.exe --noproxy * http://127.0.0.1:8002/health`
- prefer API or CLI flows over direct DB writes unless doing repair work
- do not assume the HTTP caption server is the active production path

High-signal files:

- `backend\app\tasks.py`
- `backend\app\cli.py`
- `backend\app\main.py`
- `backend\app\config.py`
- `backend\app\caption_service.py`
- `scripts\start-dev-multiproc.ps1`

Typical traps:

- stale docs still describe `CAPTION_PROVIDER=http`
- launcher docs overstate what the caption pane does
- `/health` device fields are not a reliable proxy for external subprocess GPU use
