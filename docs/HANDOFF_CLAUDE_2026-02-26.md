# Claude Handoff - 2026-02-26

Last updated: 2026-02-27 (final)
Owner context: yanbo / vlmPhotoHouse

## 1) Quick Status

- Repo: `vlmPhotoHouse` (branch `master`, 5 commits ahead of origin)
- Data root: `E:\VLM_DATA`
- Originals root: `E:\01_INCOMING`
- DB: `E:\VLM_DATA\databases\metadata.sqlite`
- API: `http://127.0.0.1:8002`
- Caption server: `http://127.0.0.1:8102`

Live DB snapshot (final):
- assets: `12336` (images `9979`, videos `2357`)
- captions: draining — ~5608 pending caption tasks remain
- face detections: `15979`
- face assigned: `10371` (was 9591 at session start → +780)
- face unassigned: `5608` (was 6387 → -779)
- queue pending: `~5608` (all `caption`)
- queue running: `4` (all `caption`)

## 2) What Was Completed This Session

### 2a) LVFace Provider Restored
- Root cause: API started without LVFace env vars → StubFaceEmbeddingProvider.
- Fix: restarted API with correct env vars (see CLAUDE.md for full list).
- Confirmed: `LVFaceSubprocessProvider` active in `/health`.

### 2b) LVFace GPU Fix (cudnn64_9.dll)
- Root cause: `cudnn64_9.dll` not on subprocess PATH for LVFace ORT 1.24.2.
- Discovery: cuDNN 9 DLLs are bundled in backend venv's torch/lib.
- Fix: `_subprocess_env()` in `lvface_subprocess.py` now injects backend
  torch/lib into subprocess PATH before launching inference.
- Confirmed: `CUDAExecutionProvider` active in LVFace subprocess.

### 2c) Minor Fixes
- Added `dim` property to `LVFaceSubprocessProvider` (health now reports embed_dim).
- Wired `_subprocess_env()` into `subprocess.run()` (was missing).

### 2d) Face Auto-Assignment (779 new total)
Multi-phase pass against manual ground truth. Total: 6387 → 5608 unassigned.

**Phase 1** — threshold=0.35, margin=0.08, min_ref_faces=10, core 7 persons → **220 assigned**
- chuan=43, jane=18, jane_newborn=41, meiying=17, yanbo=49, yixia=38, zhiqiang=14

**Phase 2** — threshold=0.42, margin=0.10, guansuo (5 refs) → **23 assigned**

**Phase 3** — threshold=0.30, margin=0.05, min_ref_faces=10, core 7 persons → **392 assigned**
- jane=209, chuan=60, jane_newborn=52, yanbo=27, yixia=20, zhiqiang=13, meiying=11

**Phase 4** — threshold=0.38, margin=0.08, guansuo → **110 assigned**

**Final per-person totals (face_count after session):**
jane=2334, jane_newborn=4238, chuan=1142, yanbo=982, yixia=496, meiying=482, zhiqiang=344, guansuo=303

**Skipped** (too few refs, high FP risk): caoyujia (2 refs), mumu (4 refs), yinzhi (2 refs)

### 2e) Committed & Documented
- Commit `8d7f916`: all session fixes + CLAUDE.md created
- CLAUDE.md: created at repo root with full onboarding guide

## 3) Remaining Unassigned Faces Strategy

6144 faces remain unassigned. Distribution of why they're hard:
- Scores against manual centroids are low (median ~0.18, max ~0.54 at default threshold).
- The 0.35+ threshold pass took the "easy" matches.
- Remaining faces are likely: low quality crops, unusual angles, partial faces, people
  with few/no manual labels (caoyujia, mumu, yinzhi, unknown persons).

Recommended next steps:
1. **Manual corrections**: Review unassigned faces in UI; manually label any known persons.
   Especially: add more refs for caoyujia, mumu, yinzhi if you can identify them.
2. **Propagation**: After manual batch, run:
   ```powershell
   .\.venv\Scripts\python.exe -m app.cli faces-auto-assign --score-threshold 0.30 --margin 0.05 --min-ref-faces 2 --reference-manual-only --apply --limit 0
   ```
3. **Include DNN re-eval**: Once more refs exist, run with `--include-dnn-assigned` to
   re-evaluate borderline DNN assignments.
4. **Quality/redetect**: For truly hard faces, a targeted redetect pass may help.

## 4) Current Blockers / Notes

1. **Caption queue still draining**: ~5860 pending. Progressing well (~1500 processed this session).
   Keep caption service running.

2. **API started manually**: Not via startup script. Env vars are correct (LVFace active).
   If API restarts, use startup script:
   ```powershell
   .\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal -KillExisting
   ```

3. **No propagation tasks queued**: The CLI auto-assign writes `label_source='dnn'` directly.
   Propagation tasks are only auto-enqueued via the API manual labeling flow.
   To force a propagation pass: run faces-auto-assign again with `--include-dnn-assigned`.

## 5) Files Claude Should Read First

- `CLAUDE.md` (repo root) — quick project onboarding
- `docs/HANDOFF_CLAUDE_2026-02-26.md` (this file)
- `docs/PROJECT_STATUS_CURRENT.md`

## 6) Command Reference

Health check (bypass Clash proxy):
```bash
curl -s --noproxy '*' http://127.0.0.1:8002/health
```

Auto-assign dry-run (conservative, core persons):
```powershell
cd backend
..\.venv\Scripts\python.exe -m app.cli faces-auto-assign --score-threshold 0.35 --margin 0.08 --min-ref-faces 10 --reference-manual-only --limit 0
```

Auto-assign apply (add --apply when happy with dry-run):
```powershell
..\.venv\Scripts\python.exe -m app.cli faces-auto-assign --score-threshold 0.30 --margin 0.05 --min-ref-faces 2 --reference-manual-only --apply --limit 0
```

Reset stuck running tasks (after unclean shutdown):
```python
import sqlite3
con = sqlite3.connect(r"E:/VLM_DATA/databases/metadata.sqlite")
cur = con.cursor()
cur.execute("UPDATE tasks SET state='pending', started_at=NULL WHERE state='running'")
con.commit(); con.close()
```

## 7) Current Working Tree (after commit 8d7f916)

Clean — all session changes committed.
New uncommitted: only `docs/HANDOFF_CLAUDE_2026-02-26.md` (this update).
