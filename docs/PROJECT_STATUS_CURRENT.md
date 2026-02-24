# VLM Photo Engine - Current Project Status

Last Updated: 2026-02-24

## Scope
This document is the operational handoff for any new agent joining this repository. It reflects the current production-like local setup on Windows with data rooted on Drive E.

Architecture companion:
- `docs/architecture/SYSTEM_ARCHITECTURE_CURRENT_2026-02-24.md`

## Current Ground Truth
- Repository: `vlmPhotoHouse` (branch `master`)
- API: `http://127.0.0.1:8002`
- UI: `http://127.0.0.1:8002/ui`
- Data root: `E:\VLM_DATA`
- Originals root: `E:\01_INCOMING`
- Database: `sqlite:///E:/VLM_DATA/databases/metadata.sqlite`
- Face embed provider: `LVFaceSubprocessProvider` (GPU/CUDA path)
- Face detect provider: `InsightFaceDetectionProvider`
- Caption provider: `HTTPCaptionProvider` (`http://127.0.0.1:8102`)
- Caption service default: `qwen3-vl` (`Qwen/Qwen3-VL-8B-Instruct`, 4-bit nf4)

## Entry Point
Use `scripts/start-dev-multiproc.ps1` as the main local entry point.

Recommended launch (from repo root):
```powershell
.\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal -KillExisting
```

## Current People Taxonomy
Named persons currently include:
- `jane`
- `jane_newborn`
- `yanbo` (renamed from `yb`)
- `chuan` (renamed from `cc`)
- `meiying`
- `zhiqiang`
- `yixia`
- `guansuo`
- `yang`
- `james`

Important split:
- `jane` and `jane_newborn` are intentionally separate IDs.
- Newborn propagation has been run with strict competition against other named persons.

## Snapshot (2026-02-24)
Counts are moving as manual tags continue, but recent verified baseline is:
- Faces total: ~16k
- Faces assigned: ~7.7k
- Faces unassigned: ~8.3k
- Queue: pending 0 / running 0 at rest

## What Was Fixed Recently
1. Face count drift:
- Root cause: `autoflush=False` sessions caused recompute queries to run before pending assignment writes were flushed.
- Fix: explicit `flush()` before count recomputation in:
  - `backend/app/routers/people.py`
  - `backend/app/cli.py`
  - `backend/app/tasks.py`

2. `dim_backfill` queue churn and dispatch gaps:
- Added `dim_backfill` task handling branch to executor.
- Added guard to avoid unbounded duplicate `dim_backfill` enqueue bursts.

3. Manual-label propagation behavior:
- Manual assignments enqueue `person_label_propagate` tasks.
- Propagation uses manual references and writes `label_source='dnn'`, preserving provenance.

## Operational Commands
From `backend` directory:

Check ingestion summary:
```powershell
.\.venv\Scripts\python.exe -m app.cli ingest-status E:\01_INCOMING
```

Run conservative full auto-assign:
```powershell
.\.venv\Scripts\python.exe -m app.cli faces-auto-assign --score-threshold 0.30 --margin 0.05 --min-ref-faces 2 --reference-manual-only --apply --limit 0
```

Run targeted auto-assign for selected names:
```powershell
.\.venv\Scripts\python.exe -m app.cli faces-auto-assign --score-threshold 0.30 --margin 0.05 --min-ref-faces 2 --reference-manual-only --name jane --name jane_newborn --name yanbo --name chuan --apply --limit 0
```

Run full-batch refresh using latest manual labels (re-evaluate unassigned + existing DNN labels):
```powershell
.\.venv\Scripts\python.exe -m app.cli faces-auto-assign --score-threshold 0.30 --margin 0.05 --min-ref-faces 2 --reference-manual-only --include-dnn-assigned --apply --limit 0
```

Health check:
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8002/health
```

Inspect face assignment audit history:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8002/faces/assignment-history?page=1&page_size=50"
```

## Next Priorities
1. Continue manual corrections on hard cases (baby vs kid phases, side profiles, low-light faces).
2. Run targeted propagation immediately after each manual batch.
3. Periodically run conservative full auto-assign and verify precision via UI spot checks.
4. Keep person naming clean (avoid unnamed clusters for known people).
5. Keep all data artifacts on Drive E; do not migrate working data back to Drive C.

## Notes for New Agents
- Prefer working through API and CLI, not direct DB mutation, unless repair work is required.
- If UI counts look stale, verify `persons.face_count` against `face_detections` counts.
- If queue backlog appears stuck, inspect stale `running` tasks and provider health before bulk requeue.
- Do not commit local artifacts like `.coverage`, `coverage.xml`, or personal workspace files.

