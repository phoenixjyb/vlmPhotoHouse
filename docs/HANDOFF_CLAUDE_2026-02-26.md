# Claude Handoff - 2026-02-26

Last updated: 2026-02-26 (session 2)
Owner context: yanbo / vlmPhotoHouse

## 1) Quick Status

- Repo: `vlmPhotoHouse`
- Data root: `E:\VLM_DATA`
- Originals root: `E:\01_INCOMING`
- DB: `E:\VLM_DATA\databases\metadata.sqlite`
- API: `http://127.0.0.1:8002`
- Caption server target: `http://127.0.0.1:8102`

Live DB snapshot (end of session 2):
- assets: `12336` (images `9979`, videos `2357`)
- captions rows: draining — was 21521, queue was 7397 pending → ~6069 pending remaining
- face detections: `15979`
- face assigned: `9591`
- face unassigned: `6388`
- queue pending: ~6069 (all `caption`)
- queue running: `3` (all `caption`)

## 2) What Was Completed This Session

### 2a) LVFace Provider Restored
- Root cause: API process started without LVFace env vars → fell back to StubFaceEmbeddingProvider.
- Fix: restarted API process with correct env vars:
  - `FACE_EMBED_PROVIDER=lvface`
  - `LVFACE_EXTERNAL_DIR=C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace`
  - `LVFACE_PYTHON_EXE=C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace\.venv\Scripts\python.exe`
  - `LVFACE_MODEL_NAME=LVFace-B_Glint360K.onnx`
- API health now confirms: `embed_provider: LVFaceSubprocessProvider`.

### 2b) LVFace GPU Fix (cudnn64_9.dll)
- Root cause: `cudnn64_9.dll` was not on the PATH for the LVFace subprocess.
  The LVFace venv's ORT 1.24.2 requires cuDNN 9.x.
- Discovery: cuDNN 9 DLLs are bundled in the **backend** venv's torch/lib:
  `vlmPhotoHouse/.venv/Lib/site-packages/torch/lib/cudnn64_9.dll` (and siblings).
- Fix: modified `backend/app/lvface_subprocess.py` → `_subprocess_env()` to inject
  the backend torch/lib directory into the subprocess PATH before subprocess is launched.
  Verified: ORT now uses `CUDAExecutionProvider` when PATH includes torch/lib.

### 2c) dim Property Fix
- Cosmetic: added `dim` property to `LVFaceSubprocessProvider` (returns `self.target_dim`)
  so `/health` reports `embed_dim: 128` instead of `null`.

### 2d) Stale Running Tasks Reset
- Before restarting the API, 33 stuck `running` caption tasks were reset to `pending`
  directly in DB to prevent them getting orphaned.

## 3) Current Blockers / Notes

1. Caption queue still draining:
   - ~6069 pending caption tasks remaining.
   - Queue draining at ~670 tasks per few minutes while API worker runs.
   - Caption service: Qwen3-VL-8B-Instruct, nf4, RTX 3090, GPU healthy.

2. API started manually this session (not via startup script):
   - The API was restarted without `-UseWindowsTerminal` from a bash context.
   - env vars were set manually — they are correct but not persisted.
   - If the API process crashes or is restarted, run the startup script:
     ```powershell
     .\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal -KillExisting
     ```

3. LVFace GPU path now fixed in code but not yet validated end-to-end with real face:
   - The PATH injection logic runs when `embed_face()` is called.
   - Next face re-embed or auto-assign pass will use CUDA provider.

4. Unassigned faces (6388) still need strategy:
   - Ground-truth-only auto-assign (`--reference-manual-only`) matched 0/6388.
   - Best-score distribution: median=0.182, max=0.544 (threshold=0.55).
   - Consider: expanding manual labels, lowering threshold experimentally, or targeted redetect.

## 4) Files Modified This Session

- `backend/app/lvface_subprocess.py`:
  - Added `dim` property to `LVFaceSubprocessProvider`
  - Added torch/lib PATH injection in `_subprocess_env()` for CUDA provider

No commit was created this session.

## 5) Files Claude Should Read First

Primary handoff/status:
- `docs/HANDOFF_CLAUDE_2026-02-26.md` (this file)
- `docs/PROJECT_STATUS_CURRENT.md`

Key runtime files:
- `scripts/start-dev-multiproc.ps1`
- `backend/app/config.py`
- `backend/app/lvface_subprocess.py`
- `backend/app/face_embedding_service.py`

## 6) Immediate Next Steps (Recommended Order)

1. Monitor caption queue drain — check if queue reaches 0.
2. Run faces-auto-assign dry-run with lower threshold to assess residual face coverage.
3. Commit the two fixes to `backend/app/lvface_subprocess.py`.
4. When next LVFace embed is triggered, verify CUDA provider is active (check logs).

## 7) Command Reference

Health check (bypass Clash proxy):
```bash
curl -s --noproxy '*' http://127.0.0.1:8002/health
curl -s --noproxy '*' http://127.0.0.1:8002/health/caption
```

Reset stuck running tasks (after unclean shutdown):
```python
import sqlite3
con = sqlite3.connect(r"E:/VLM_DATA/databases/metadata.sqlite")
cur = con.cursor()
cur.execute("UPDATE tasks SET state='pending', started_at=NULL WHERE state='running'")
con.commit(); con.close()
```

Validate LVFace (from backend dir):
```powershell
$env:FACE_EMBED_PROVIDER='lvface'
$env:LVFACE_EXTERNAL_DIR='C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace'
$env:LVFACE_PYTHON_EXE='C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace\.venv\Scripts\python.exe'
$env:LVFACE_MODEL_NAME='LVFace-B_Glint360K.onnx'
.\.venv\Scripts\python.exe -m app.cli validate-lvface
```

Dry-run auto-assign (conservative, manual-only refs):
```powershell
.\.venv\Scripts\python.exe -m app.cli faces-auto-assign --score-threshold 0.30 --margin 0.05 --min-ref-faces 2 --reference-manual-only --limit 0
```

## 8) Current Working Tree Changes (Uncommitted)

- `backend/app/lvface_subprocess.py` — `dim` property + torch/lib PATH injection
- `backend/app/cli.py` — from previous session (mixed embed dim fix)
- `scripts/start-dev-multiproc.ps1` — from previous session
