# VLM Photo House - System Architecture Snapshot (2026-02-24)

This document reflects the current architecture from live runtime checks plus current repository code.

## 1) Runtime Snapshot (Current)

- API base: `http://127.0.0.1:8002`
- UI: `http://127.0.0.1:8002/ui`
- Data root: `E:\VLM_DATA`
- Originals root: `E:\01_INCOMING`
- Database: `sqlite:///E:/VLM_DATA/databases/metadata.sqlite`
- Worker: enabled (`ENABLE_INLINE_WORKER=true`)
- Face embedding provider: `LVFaceSubprocessProvider` on `cuda`
- Face detection provider: `InsightFaceDetectionProvider`
- Caption provider: `HTTPCaptionProvider`

Live data snapshot:
- Assets: `12,336` (image/jpeg: `9,972`; video/mp4: `2,356`)
- Image embeddings: `9,979`
- Captions: `14,969`
- Face detections: `15,993`
- Persons: `23`
- Video segments: `22,450`
- Face assignment audit events: `2,585`

## 2) Topology and Projects

The stack is local-first and split across repositories/services:

- `vlmPhotoHouse` (this repo): API, UI, task queue, DB orchestration.
- External LVFace project: `C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace`
- External caption project: `C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels`
- External voice service (LLMyTranslate): `C:\Users\yanbo\wSpace\llmytranslate`

Primary launcher in current workflow:
- `scripts/start-dev-multiproc.ps1` (dev multipane launcher)
- `start-multi-proc.ps1` (root-level launcher with caption HTTP service defaults)

## 3) Storage and Data Layout

Raw data and generated artifacts are split:

- Raw originals: `E:\01_INCOMING`
- DB + derived artifacts: `E:\VLM_DATA`
- SQLite DB file: `E:\VLM_DATA\databases\metadata.sqlite`
- Derived folders:
  - `E:\VLM_DATA\derived\embeddings`
  - `E:\VLM_DATA\derived\thumbnails\256`, `...\1024`
  - `E:\VLM_DATA\derived\faces\256`
  - `E:\VLM_DATA\derived\face_embeddings`
  - `E:\VLM_DATA\derived\person_embeddings`
  - `E:\VLM_DATA\derived\video_frames`
  - `E:\VLM_DATA\derived\video_embeddings`

## 4) Backend Architecture

Core app modules:
- API entry and endpoints: `backend/app/main.py`
- Queue executor and handlers: `backend/app/tasks.py`
- Data model: `backend/app/db.py`
- DB/session wiring: `backend/app/dependencies.py`
- Config: `backend/app/config.py`
- REST routers:
  - People/faces/tasks/person-search: `backend/app/routers/people.py`
  - UI static routes: `backend/app/routers/ui.py`
  - Voice proxy routes: `backend/app/routers/voice.py`, `backend/app/routers/voice_photo.py`

Provider layer:
- Face embedding providers: `backend/app/face_embedding_service.py`
- Face detection providers: `backend/app/face_detection_service.py`
- Caption providers: `backend/app/caption_service.py`
- External LVFace subprocess adapter: `backend/app/lvface_subprocess.py`
- External caption subprocess adapter: `backend/app/caption_subprocess.py`

## 5) Pipeline Flows

### 5.1 Ingestion

- Trigger: `POST /ingest/scan` or CLI `ingest-scan`.
- Scanner: `backend/app/ingest.py` walks roots and creates `assets` rows.
- Metadata extraction:
  - Images: EXIF datetime, camera info, GPS.
  - Videos: ffprobe-based duration/fps/GPS probe.
- Task enqueue (images): `embed`, `phash`, `thumb`, `caption`, `face`.
- Task enqueue (videos, when enabled): `video_probe`, `video_keyframes`, `video_embed`, optional `video_scene_detect`.

### 5.2 Captioning

- Default active mode is HTTP caption provider (`/caption` on caption service).
- Captions stored in `captions` table with variant metadata:
  - `quality_tier`, `model_version`, `superseded`, `user_edited`.
- Asset-level status fields maintained in `assets`:
  - `caption_processed`, `caption_variant_count`, `caption_processed_at`, `caption_error_last`.

### 5.3 Face Pipeline

- Detection task (`face`):
  - Runs detector on EXIF-corrected image.
  - Persists detections to `face_detections`.
  - Generates face crops in derived store.
  - Enqueues `face_embed` tasks.
- Embedding task (`face_embed`):
  - Uses selected embedding provider (currently LVFace subprocess + CUDA).
  - Writes per-face vectors to `derived/face_embeddings`.
- Assignment:
  - Manual assignment via UI/API writes `label_source='manual'`.
  - DNN assignment via propagation/auto-assign writes `label_source='dnn'`.

### 5.4 Feedback Loop (Manual -> DNN)

- Manual face assignment endpoints enqueue `person_label_propagate`.
- Propagation uses manual-labeled faces as reference centroids.
- CLI full-batch mode supports re-evaluating unassigned + DNN labels:
  - `faces-auto-assign --include-dnn-assigned --reference-manual-only --apply`

### 5.5 Vector Search

- Image vectors in `embeddings` table + `.npy` files.
- In-memory/FAISS index loaded at startup from embedding files.
- Search APIs:
  - `/search/vector`
  - `/search/smart` (hybrid vector + caption + tags)
  - Person-scoped search under `/search/person/*`

## 6) Database Model (Current Main Tables)

- `assets`: file identity, EXIF/media metadata, GPS, status, caption summary fields.
- `embeddings`: per-asset vector metadata and storage path.
- `captions`: caption variants and edit provenance.
- `face_detections`: bounding box, embedding path, person assignment, label provenance.
- `persons`: person identities and cached `face_count`.
- `tasks`: async queue with state/retry/progress fields.
- `video_segments`: scene/time segments and segment embeddings.
- `tags`, `asset_tags`: lightweight tagging.
- `face_assignment_events`: assignment audit history (manual/dnn/system).

## 7) UI Architecture

UI is server-hosted static frontend:
- HTML: `backend/app/ui/index.html`
- JS: `backend/app/ui/app.js`
- CSS: `backend/app/ui/styles.css`
- Route: `/ui`

Main tabs:
- Library: search + asset inspector (media, captions, tags, per-asset faces).
- People: named/unnamed persons, person assets, unassigned face queue.
- Map: GPS visualization via Leaflet (`/assets/geo`).
- Tasks: queue monitor + cancel action.
- Admin: health/metrics, index rebuild, recluster, ingest trigger.

## 8) Model/Provider Matrix (As Wired)

Face embedding providers:
- `stub`, `facenet`, `insight`, `lvface`, `auto`

Face detection providers:
- `stub`, `mtcnn`, `insight/scrfd`, `auto`

Caption providers:
- `stub`, `http`, `blip2`, `llava`, `qwen2.5-vl`, `auto`
- External subprocess path supported when `CAPTION_EXTERNAL_DIR` is set.

Voice:
- Backend proxies to external LLMyTranslate endpoints under `/voice/*`.

## 9) Operational Commands (Current)

From repo root:

```powershell
.\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal
```

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.cli ingest-status E:\01_INCOMING
.\.venv\Scripts\python.exe -m app.cli gps-backfill --root E:\01_INCOMING
.\.venv\Scripts\python.exe -m app.cli faces-auto-assign --score-threshold 0.30 --margin 0.05 --min-ref-faces 2 --reference-manual-only --include-dnn-assigned --apply --limit 0
Invoke-RestMethod -Uri http://127.0.0.1:8002/health
```

## 10) Current Architecture Gaps / Drift

1. Documentation drift:
- `README.md` and several older architecture docs still describe 2025 defaults and stale provider defaults.

2. Worker dispatch mismatch in current code:
- `ingest.py` enqueues `phash` and video tasks.
- `tasks.py` defines handlers for `phash` and video tasks.
- `TaskExecutor.run_once` currently dispatches only:
  - `embed`, `thumb`, `caption`, `face`, `face_embed`, `person_cluster`, `person_label_propagate`, `dim_backfill`
- `phash` and video task types are not currently dispatched by `run_once`.

3. Task state naming inconsistency:
- Runtime contains both `done` and `finished` task states.
- Current executor writes `finished`, while some reporting logic still filters by `done`.

4. API runtime drift warning:
- Newly added `/faces/assignment-history` route exists in code but was not visible in current running OpenAPI snapshot during this audit.
- Backend restart/reload is required to align live process with current source.

## 11) Recommended Source of Truth Going Forward

- Operational truth: `docs/PROJECT_STATUS_CURRENT.md`
- Architecture truth (this snapshot): `docs/architecture/SYSTEM_ARCHITECTURE_CURRENT_2026-02-24.md`
- Code truth:
  - `backend/app/main.py`
  - `backend/app/tasks.py`
  - `backend/app/db.py`
  - `backend/app/routers/people.py`
