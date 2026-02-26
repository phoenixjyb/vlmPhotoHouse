# vlmPhotoHouse — Claude Instructions

## Project Overview
Local-first photo/video management system with AI pipelines:
face detection, face recognition, image captioning, semantic search.

## Key Paths
- API: `http://127.0.0.1:8002` (FastAPI + inline worker)
- Caption service: `http://127.0.0.1:8102` (Qwen3-VL-8B, RTX 3090)
- DB: `E:\VLM_DATA\databases\metadata.sqlite`
- Data root: `E:\VLM_DATA`, Originals: `E:\01_INCOMING`

## Python Environments
There are TWO venvs — use the correct one:
- **Backend API** → `vlmPhotoHouse/.venv/Scripts/python.exe` (repo root, has torch)
- **LVFace** → `LVFace/.venv/Scripts/python.exe` (separate repo, ORT-GPU)
- Do NOT use `backend/.venv` for running the app — that's a dev/test venv without torch.

## Running the Stack
```powershell
# From vlmPhotoHouse repo root:
.\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal -KillExisting
```

## curl on This Machine
Always add `--noproxy '*'` — `http_proxy=http://127.0.0.1:7890` (Clash) is set globally
and intercepts localhost traffic, returning 502.
```bash
curl -s --noproxy '*' http://127.0.0.1:8002/health
```

## LVFace Setup
- Dir: `C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace`
- Venv: `LVFace/.venv` (not `.venv-lvface-311` — that dir doesn't exist)
- Model: `LVFace/models/LVFace-B_Glint360K.onnx` (not `lvface.onnx`)
- Inference mode: `src_onnx` (uses `LVFace/src/inference_onnx.py`)
- CUDA fix: `lvface_subprocess.py:_subprocess_env()` injects backend torch/lib into PATH
  so ORT CUDA provider finds `cudnn64_9.dll` (bundled with backend torch install).

## Required Env Vars (for API process)
```
FACE_EMBED_PROVIDER=lvface
LVFACE_EXTERNAL_DIR=C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace
LVFACE_PYTHON_EXE=C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace\.venv\Scripts\python.exe
LVFACE_MODEL_NAME=LVFace-B_Glint360K.onnx
FACE_EMBED_DIM=128
CAPTION_PROVIDER=http
CAPTION_SERVICE_URL=http://127.0.0.1:8102
DATABASE_URL=sqlite:///E:/VLM_DATA/databases/metadata.sqlite
VLM_DATA_ROOT=E:\VLM_DATA
ORIGINALS_PATH=E:\01_INCOMING
```

## CLI (from `backend/` dir, using `../.venv/Scripts/python.exe`)
```powershell
# Validate LVFace
python -m app.cli validate-lvface

# Ingest status
python -m app.cli ingest-status E:\01_INCOMING

# Auto-assign faces (dry-run by default, add --apply to commit)
python -m app.cli faces-auto-assign --score-threshold 0.30 --margin 0.05 --min-ref-faces 2 --reference-manual-only --limit 0

# Reset stuck running tasks (after unclean shutdown)
# Use direct DB UPDATE — no CLI command for this
```

## DB Quick Check
```python
import sqlite3
con = sqlite3.connect(r"E:/VLM_DATA/databases/metadata.sqlite")
cur = con.cursor()
print("pending", cur.execute("select count(*) from tasks where state='pending'").fetchone()[0])
print("running", cur.execute("select count(*) from tasks where state='running'").fetchone()[0])
print("unassigned", cur.execute("select count(*) from face_detections where person_id is null").fetchone()[0])
con.close()
```

## People (named persons)
`jane`, `jane_newborn`, `yanbo`, `chuan`, `meiying`, `zhiqiang`, `yixia`, `guansuo`, `yang`, `james`
- `jane` and `jane_newborn` are intentionally separate IDs.

## Architecture Docs
- `docs/PROJECT_STATUS_CURRENT.md` — current ground truth
- `docs/HANDOFF_CLAUDE_*.md` — per-session handoff notes
- `docs/architecture/SYSTEM_ARCHITECTURE_CURRENT_2026-02-24.md` — full architecture

## Operational Notes
- Prefer API + CLI over direct DB mutation (except for repair work).
- After unclean shutdown, reset `running` tasks to `pending` before restarting worker.
- Keep all data artifacts on Drive E — do not migrate to Drive C.
- Do not commit: `.coverage`, `coverage.xml`, personal workspace files, `rampp/pretrained/`.
