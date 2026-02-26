# Claude Handoff - 2026-02-26

Last updated: 2026-02-26 (US local)
Owner context: yanbo / vlmPhotoHouse

## 1) Quick Status

- Repo: `vlmPhotoHouse`
- Data root: `E:\VLM_DATA`
- Originals root: `E:\01_INCOMING`
- DB: `E:\VLM_DATA\databases\metadata.sqlite`
- API: `http://127.0.0.1:8002`
- Caption server target: `http://127.0.0.1:8102`

Live DB snapshot:
- assets: `12336` (images `9979`, videos `2357`)
- captions rows: `21521`
- stub-like captions: `0`
- face detections: `15979`
- face assigned: `9591`
- face unassigned: `6388`
- manual labels: `494`
- dnn labels: `9097`
- queue pending: `7397` (all `caption`)
- queue running: `11` (all `caption`)

## 2) What Was Just Completed

1. Full assigned-face re-embed pass finished:
- scope: all assigned faces under `E:\01_INCOMING`
- result: `9591/9591` updated, `0` failures

2. Ground-truth-only auto-assign finished:
- command mode: `--reference-manual-only`
- scope: unassigned faces under `E:\01_INCOMING`
- result: `scanned=6388 matched=0 changed=0`

3. `faces-auto-assign` robustness was fixed in code:
- file: `backend/app/cli.py`
- fix: mixed embedding dimensions no longer crash centroid build
- fix: scoring now only compares vectors against same-dimension centroids
- fix: reference summary print tuple unpack corrected

## 3) Why Unassigned Is Still High (6388)

The remaining unassigned faces are not passing similarity thresholds against manual centroids.

Observed best-score distribution on unassigned pool (`6388` faces):
- median best score: `0.182`
- p95 best score: `0.373`
- max best score: `0.544`

Conclusion:
- Even with loose threshold (`0.55`), no safe matches from manual-ground-truth centroids.
- This is not a queue failure; it is low-confidence identity matching.

## 4) Critical Runtime Drift / Blockers

1. API runtime currently reports stub face embedding provider:
- `/health` shows `face.embed_provider = StubFaceEmbeddingProvider` (dim `128`)
- This is wrong for production target (should be LVFace path).

2. LVFace GPU path is currently unavailable in LVFace venv:
- ONNXRuntime CUDA provider load fails (`cudnn64_9.dll` missing).
- Effective provider during re-embed pass: `CPUExecutionProvider`.

3. Caption queue is active and large:
- `pending caption=7397`, `running caption=11`.
- API still reports caption provider as HTTP path (`HTTPCaptionProvider`).

## 5) Files Claude Should Read First

Primary handoff/status:
- `docs/HANDOFF_CLAUDE_2026-02-26.md` (this file)
- `docs/PROJECT_STATUS_CURRENT.md`
- `docs/architecture/SYSTEM_ARCHITECTURE_CURRENT_2026-02-24.md`

Startup/orchestration:
- `scripts/start-dev-multiproc.ps1`
- `backend/app/config.py`
- `backend/app/main.py`

Face pipeline:
- `backend/app/cli.py`
- `backend/app/tasks.py`
- `backend/app/face_embedding_service.py`
- `backend/app/face_detection_service.py`
- `backend/app/lvface_subprocess.py`

Caption pipeline:
- `backend/app/caption_service.py`
- `backend/app/caption_subprocess.py`
- `backend/app/routers/ui.py` (task/status surfaces)

## 6) Immediate Next Steps (Recommended Order)

1. Restore correct face embed provider in live API process:
- ensure env is set to LVFace mode (not stub)
- validate via:
  - `http://127.0.0.1:8002/health`
  - `python -m app.cli validate-lvface`

2. Fix LVFace GPU dependency chain in LVFace venv:
- resolve ONNXRuntime CUDA requirements (cuDNN/CUDA runtime match)
- confirm provider is CUDA, not CPU.

3. Continue caption backlog monitoring:
- keep caption workers running
- verify `/health/caption` and queue drain trend.

4. Improve residual face assignment strategy:
- run targeted redetect/quality passes for hard cases
- keep manual labels as strict ground truth
- propagate only when confidence is high.

## 7) Command Reference

From repo root:

```powershell
Invoke-RestMethod http://127.0.0.1:8002/health
Invoke-RestMethod http://127.0.0.1:8002/health/caption
Invoke-RestMethod "http://127.0.0.1:8002/tasks?page=1&page_size=20"
```

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.cli validate-lvface
.\.venv\Scripts\python.exe -m app.cli faces-auto-assign --reference-manual-only --root E:\01_INCOMING --limit 0
```

DB quick check:

```powershell
.\.venv\Scripts\python.exe - <<'PY'
import sqlite3
con=sqlite3.connect(r"E:/VLM_DATA/databases/metadata.sqlite")
cur=con.cursor()
print("pending", cur.execute("select count(*) from tasks where state='pending'").fetchone()[0])
print("running", cur.execute("select count(*) from tasks where state='running'").fetchone()[0])
print("unassigned", cur.execute("select count(*) from face_detections where person_id is null").fetchone()[0])
con.close()
PY
```

## 8) Current Working Tree Notes

Local uncommitted code changes currently include:
- `backend/app/cli.py`
- `backend/app/lvface_subprocess.py`
- `scripts/start-dev-multiproc.ps1`

No commit was created in this handoff step.

