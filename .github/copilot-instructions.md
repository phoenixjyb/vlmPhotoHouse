# Copilot Instructions

Read these files before making assumptions about this repo:

1. `docs/agent-memory/PROJECT_TRUTH.md`
2. `docs/agent-memory/STATUS_AND_PRODUCT_READINESS_2026-04-07.md`
3. `docs/agent-memory/COPILOT.md`

Repo-specific rules:

- use `vlmPhotoHouse\.venv\Scripts\python.exe` for runtime and CLI work
- do not use `backend\.venv` for the live stack
- confirm runtime claims against `backend\app\config.py`, `backend\app\caption_service.py`, `backend\app\tasks.py`, and the live `/health` endpoint
- treat older docs that describe `CAPTION_PROVIDER=http` as potentially stale unless verified
