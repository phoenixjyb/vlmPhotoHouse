# vlmPhotoHouse - Claude Instructions

Read these first:

1. `docs/agent-memory/PROJECT_TRUTH.md`
2. `docs/agent-memory/STATUS_AND_PRODUCT_READINESS_2026-04-07.md`
3. `docs/agent-memory/CLAUDE.md`

Critical current truths:

- use `vlmPhotoHouse\.venv\Scripts\python.exe` for app/runtime work
- do not use `backend\.venv` for the live stack
- verify localhost with `curl.exe --noproxy * http://127.0.0.1:8002/health`
- the active caption path is currently external subprocess captioning, not the old HTTP caption-server-first path
- `scripts\start-dev-multiproc.ps1` sets backend env correctly, but its caption pane does not actually start `caption_server.py`
- data stays on Drive E: `E:\01_INCOMING` and `E:\VLM_DATA`

Useful live endpoints:

- API: `http://127.0.0.1:8002`
- UI: `http://127.0.0.1:8002/ui`

Do not trust older handoff docs until they are checked against code, launcher behavior, DB state, and `/health`.
