# VLM Photo Engine — Current Project Status

Last Updated: 2026-02-27

## Scope

Operational handoff for any new agent joining this repository. Reflects the current
production-like local setup on Windows with data rooted on Drive E.

For full architecture: `docs/architecture/SYSTEM_ARCHITECTURE_2026-02-27.md`
For onboarding: `CLAUDE.md` (repo root)
For latest session details: `docs/HANDOFF_CLAUDE_2026-02-26.md`

---

## Current Ground Truth

- Repository: `vlmPhotoHouse` (branch `master`)
- API: `http://127.0.0.1:8002`
- UI: `http://127.0.0.1:8002/ui`
- Data root: `E:\VLM_DATA`
- Originals root: `E:\01_INCOMING`
- Database: `sqlite:///E:/VLM_DATA/databases/metadata.sqlite`
- Face embed provider: `LVFaceSubprocessProvider` (GPU/CUDA, LVFace-B_Glint360K.onnx)
- Face detect provider: `InsightFaceDetectionProvider` (SCRFD)
- Caption provider: `HTTPCaptionProvider` → `http://127.0.0.1:8102`
- Caption model: `Qwen/Qwen3-VL-8B-Instruct` (4-bit nf4, RTX 3090)
- Image tag provider: `HTTPImageTagProvider` → `http://127.0.0.1:8112`
- Image tag model: RAM++ (`ram_plus_swin_large_14m.pth`, Quadro P2000)

---

## Live Data Snapshot (2026-02-27)

| Metric | Count |
|--------|-------|
| Total assets | 12,336 |
| Images | 9,979 |
| Videos | 2,357 |
| Face detections | 15,979 |
| Faces assigned | ~11,099 |
| Faces unassigned | ~4,880 |
| Named persons | 38 (14 with manual refs) |
| Caption queue pending | ~4,880 (draining) |
| Image tag links | ~30,567 |

---

## People Taxonomy

Named persons:
- **Core (10+ manual refs)**: `jane`, `jane_newborn`, `yanbo`, `chuan`, `meiying`, `zhiqiang`, `yixia`
- **Known (2–9 manual refs)**: `guansuo`, `caoyujia`, `caoyuxin`, `gaozhu`, `yinzhi`, `mumu`, `dave`
- **Single-ref only**: `yang`, `james`, `zengyinqing`, `shixianhai`, `zeze`
  (cannot auto-assign safely from 1 reference face)

Important: `jane` and `jane_newborn` are intentionally separate person IDs.

---

## Entry Point

Primary launcher (from repo root):
```powershell
.\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal -KillExisting
```

Opens Windows Terminal 2×2 grid: API (8002), Caption server (8102), RAM++ (8112), free pane.

---

## Quick Operational Commands

### Health check
```bash
curl -s --noproxy '*' http://127.0.0.1:8002/health
```
> Always use `--noproxy '*'` — Clash proxy on port 7890 intercepts localhost.

### DB quick check (from vlmPhotoHouse root)
```python
import sqlite3
con = sqlite3.connect(r"E:/VLM_DATA/databases/metadata.sqlite")
cur = con.cursor()
print("pending", cur.execute("select count(*) from tasks where state='pending'").fetchone()[0])
print("running", cur.execute("select count(*) from tasks where state='running'").fetchone()[0])
print("unassigned", cur.execute("select count(*) from face_detections where person_id is null").fetchone()[0])
con.close()
```

### Reset stuck running tasks (after unclean shutdown)
```python
import sqlite3
con = sqlite3.connect(r"E:/VLM_DATA/databases/metadata.sqlite")
cur = con.cursor()
cur.execute("UPDATE tasks SET state='pending', started_at=NULL WHERE state='running'")
con.commit(); con.close()
```

### Face auto-assign (from backend/, using ../.venv/Scripts/python.exe)
```powershell
# Dry-run — conservative, core persons
python -m app.cli faces-auto-assign --score-threshold 0.35 --margin 0.08 `
    --min-ref-faces 10 --reference-manual-only --limit 0

# Apply — all persons with ≥2 manual refs
python -m app.cli faces-auto-assign --score-threshold 0.30 --margin 0.05 `
    --min-ref-faces 2 --reference-manual-only --apply --limit 0

# Re-evaluate existing DNN assignments with updated refs
python -m app.cli faces-auto-assign --score-threshold 0.30 --margin 0.05 `
    --min-ref-faces 2 --reference-manual-only --include-dnn-assigned --apply --limit 0
```

---

## Current Priorities

1. **Caption queue**: ~4,880 pending tasks draining. Keep caption service running.
2. **Remaining unassigned faces**: ~4,880. Most are hard cases (low quality crops,
   unusual angles, partial faces, unknown persons). Recommended approach:
   - Manually label more examples of caoyujia, mumu, yinzhi via UI
   - Run targeted auto-assign after each manual batch
   - For truly hard faces: targeted redetect pass
3. **phash / video task dispatch**: these task types are enqueued but not dispatched
   by `TaskExecutor.run_once` — known gap, no fix yet.

---

## Repository Structure (Post 2026-02-25 Cleanup)

Runtime surface:
- `backend/` — FastAPI app, worker, CLI, providers
- `rampp/` — RAM++ image-tag service adapter
- `scripts/` — launcher and utility scripts
- `docs/` — architecture and operational docs
- `CLAUDE.md` — agent onboarding guide

Legacy/experimental content archived to:
`C:\Users\yanbo\wSpace\vlm-photo-engine\archive_unused\20260225-prod-cleanup\`

---

## Notes for New Agents

- Use `vlmPhotoHouse/.venv/Scripts/python.exe` for all app code — NOT `backend/.venv`
  (that venv has no torch and is for unit tests only).
- After unclean shutdown, reset `running` tasks to `pending` before restarting.
- Prefer API + CLI over direct DB mutation (except for repair work).
- Do not commit `.coverage`, `coverage.xml`, `rampp/pretrained/`, personal workspace files.
- See `docs/architecture/SYSTEM_ARCHITECTURE_2026-02-27.md` for full technical reference.
