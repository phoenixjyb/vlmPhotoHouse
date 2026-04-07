# Claude Notes

Start here:

1. `docs\agent-memory\PROJECT_TRUTH.md`
2. `docs\agent-memory\STATUS_AND_PRODUCT_READINESS_2026-04-07.md`

Minimum truths to keep straight:

- the app runtime is `vlmPhotoHouse\.venv`, not `backend\.venv`
- the active caption path is currently external subprocess captioning, not the old HTTP caption-server-first path
- the launcher sets the backend env correctly, but the caption pane itself does not start `caption_server.py`
- current backlog is caption-only for the active `E:\01_INCOMING` corpus

When in doubt, verify against:

- `backend\app\config.py`
- `backend\app\caption_service.py`
- `backend\app\tasks.py`
- `scripts\start-dev-multiproc.ps1`
- live `/health`
