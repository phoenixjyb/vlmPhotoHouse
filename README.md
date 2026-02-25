# VLM Photo House

Local-first photo/video intelligence system with:
- ingestion from `E:\01_INCOMING`
- metadata + GPS extraction
- face detection + face embeddings + person assignment
- multimodal captions (Qwen3-VL via local HTTP caption service)
- bilingual web UI
- SQLite-backed search and task orchestration

## Production Repos

This project runs as a multi-repo stack under `C:\Users\yanbo\wSpace\vlm-photo-engine`:

1. `vlmPhotoHouse` (this repo): API, worker, DB orchestration, UI, CLI.
2. `vlmCaptionModels`: caption server (`/caption`, `/translate`) with local Qwen3-VL model.
3. `LVFace`: external face embedding project used by subprocess provider.

## Runtime Defaults (Current)

- API/UI: `http://127.0.0.1:8002` (`/ui`)
- Caption service: `http://127.0.0.1:8102`
- DB: `E:\VLM_DATA\databases\metadata.sqlite`
- Originals: `E:\01_INCOMING`
- Derived data root: `E:\VLM_DATA\derived`
- Caption provider: `http` (Qwen3-VL in caption server)
- Face detection provider: `scrfd` (InsightFace path)
- Face embedding provider: `lvface` (external subprocess)

## Repo Layout (Production Surface)

Keep and operate from these folders:
- `backend/` application code
- `scripts/` launchers (`start-dev-multiproc.ps1` is primary entrypoint)
- `docs/` current architecture and operations docs
- `deploy/` deployment files
- `config/` config templates
- `tools/` maintenance/admin scripts
- `tests/` automated tests

Legacy/experimental content is archived outside repo at:
- `C:\Users\yanbo\wSpace\vlm-photo-engine\archive_unused\20260225-prod-cleanup\`

## Start the Stack (Windows)

From repo root:

```powershell
.\scripts\start-dev-multiproc.ps1 -Preset RTX3090 -UseWindowsTerminal
```

This starts:
- API + inline worker (`vlmPhotoHouse`)
- caption server process (`vlmCaptionModels`, provider `qwen3-vl`)
- optional voice pane (if available)

## Core Operations

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m app.cli ingest-scan E:\01_INCOMING
.\.venv\Scripts\python.exe -m app.cli ingest-status E:\01_INCOMING
.\.venv\Scripts\python.exe -m app.cli captions-backfill --force --limit 0
.\.venv\Scripts\python.exe -m app.cli captions-backfill-zh --apply --overwrite-stub --batch-size 64
.\.venv\Scripts\python.exe -m app.cli gps-backfill --root E:\01_INCOMING
.\.venv\Scripts\python.exe -m app.cli faces-auto-assign --apply --reference-manual-only --include-dnn-assigned --limit 0
```

Health checks:

```powershell
Invoke-RestMethod http://127.0.0.1:8002/health
Invoke-RestMethod http://127.0.0.1:8002/health/caption
Invoke-RestMethod http://127.0.0.1:8002/system/usage
```

## Data Placement Policy

For production usage, keep data off `C:`:
- originals on `E:\01_INCOMING`
- DB, thumbnails, embeddings, temp/cache on `E:\VLM_DATA`

Do not store generated media artifacts in repo folders.

## Documentation

- Current architecture: `docs/architecture/SYSTEM_ARCHITECTURE_CURRENT_2026-02-24.md`
- Current status handoff: `docs/PROJECT_STATUS_CURRENT.md`
- Dev launcher details: `docs/launcher-quickstart.md`

