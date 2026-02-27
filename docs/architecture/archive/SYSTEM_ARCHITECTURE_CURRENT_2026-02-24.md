# VLM Photo House - System Architecture Snapshot (2026-02-27)

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
- Caption service: `http://127.0.0.1:8102` (active provider `qwen3-vl`)
- Image tag provider: `HTTPImageTagProvider`
- Image tag service: `http://127.0.0.1:8112` (active model `ram-plus`, checkpoint-backed)

Live data snapshot:
- Assets: `12,336` (images: `9,979`; videos: `2,357`)
- Image embeddings: `9,979`
- Captions (active variants): `24,464`
- Face detections: `15,978`
- Persons: `38`
- Video segments: `22,450`
- Face assignment audit events: `4,309`
- Tag links: `30,567` (`cap=25,195`, `img=5,361`, `cap+img=7`, `(null)=4`)
- Image-tag queue: `pending=1,399`, `running=2`, `finished=8,567`, `failed=12` (draining)

## 2) Topology and Projects

The stack is local-first and split across repositories/services:

- `vlmPhotoHouse` (this repo): API, UI, task queue, DB orchestration.
- External LVFace project: `C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace`
- External caption project: `C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels`
- External voice service (LLMyTranslate): `C:\Users\yanbo\wSpace\llmytranslate`

Primary launcher in current workflow:
- `scripts/start-dev-multiproc.ps1` (dev multipane launcher)

Legacy experimental launchers and one-off scripts were archived on 2026-02-25 to:
- `C:\Users\yanbo\wSpace\vlm-photo-engine\archive_unused\20260225-prod-cleanup\`

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
- Current default model path is Qwen3 over HTTP:
  - Caption service provider: `qwen3-vl`
  - Model: `Qwen/Qwen3-VL-8B-Instruct` (4-bit `nf4`)
- Provider routing behavior in backend (`backend/app/caption_service.py`):
  - If `CAPTION_PROVIDER=http`: use `HTTPCaptionProvider` -> `CAPTION_SERVICE_URL`.
  - Else if `CAPTION_EXTERNAL_DIR` is set: use subprocess provider via `backend/app/caption_subprocess.py`.
  - Else: use built-in in-process provider classes.
- Qwen aliases supported in routing: `qwen2.5-vl`, `qwen3-vl`, `qwen3`, `qwen`.
- Caption task now supports videos by extracting a representative frame with `ffmpeg` before VLM caption generation (`backend/app/tasks.py`).
- Captions stored in `captions` table with variant metadata:
  - `quality_tier`, `model_version`, `superseded`, `user_edited`.
- Asset-level status fields maintained in `assets`:
  - `caption_processed`, `caption_variant_count`, `caption_processed_at`, `caption_error_last`.
- Caption-derived tagging now uses deterministic bilingual canonical mapping in `backend/app/tagging.py` with quota-based selection (`<=8`) and keyword fallback.
- Caption auto-tagging is Qwen-gated by default via `CAPTION_AUTO_TAG_SOURCE_MODEL_CONTAINS=qwen` to avoid BLIP-derived tags.
- Auto-tag entry points:
  - caption generation path in `backend/app/tasks.py`
  - batch backfill command `captions-tags-backfill` in `backend/app/cli.py` (default `source_model_contains=qwen`)
- Image-tagging path (RAM++ over HTTP) is active:
  - provider module: `backend/app/image_tag_service.py`
  - worker task: `image_tag` in `backend/app/tasks.py`
  - enqueue command: `image-tags-backfill` in `backend/app/cli.py`
  - RAM++ service/adapter: `rampp/service.py`, `rampp/adapter_rampp.py`
- Tag upsert merges provenance by source; same tag from both pipelines is tracked as `cap+img`.
- Per-asset auto-tag suppression is supported:
  - `DELETE /assets/{asset_id}/tags` can remove tags and block re-add for auto-tagging.
  - Blocked tag IDs are persisted in `asset_tag_blocks`; manual add unblocks.

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
- `tags`, `asset_tags`: tagging catalog and asset links.
- `asset_tag_blocks`: per-asset blocked auto tags (prevents removed auto tags from coming back).
- `asset_tags` now tracks provenance fields (`source`, `score`, `model`) for source-aware search/debug.
- `asset_tags.source` values used in production include `cap`, `img`, and merged `cap+img`.
- `face_assignment_events`: assignment audit history (manual/dnn/system).

## 7) UI Architecture

UI is server-hosted static frontend:
- HTML: `backend/app/ui/index.html`
- JS: `backend/app/ui/app.js`
- CSS: `backend/app/ui/styles.css`
- Route: `/ui`

Main tabs:
- Library: search + asset inspector (media, captions, tags with remove/block flow, per-asset faces).
- People: named/unnamed persons, person assets, unassigned face queue.
- Map: GPS visualization via Leaflet (`/assets/geo`).
- Tasks: queue monitor + cancel action.
- Admin: health/metrics (including `tags.total_links`, `tags.assets_with_tags`, `tags.by_source`), index rebuild, recluster, ingest trigger.

## 8) Model/Provider Matrix (As Wired)

Face embedding providers:
- `stub`, `facenet`, `insight`, `lvface`, `auto`

Face detection providers:
- `stub`, `mtcnn`, `insight/scrfd`, `auto`

Caption providers:
- `stub`, `http`, `blip2`, `llava`, `qwen2.5-vl`, `qwen3-vl`, `qwen3`, `auto`
- External subprocess path supported when `CAPTION_EXTERNAL_DIR` is set.
- Operational default for caption-derived auto-tagging is Qwen-only (model substring gate: `qwen`).

Image tag providers:
- `stub`, `http`, `auto` (`IMAGE_TAG_PROVIDER`)
- Active path uses RAM++ HTTP service at `http://127.0.0.1:8112` with model `ram-plus`.
- Runtime/checkpoint: `rampp/.venv-rampp` + `rampp/pretrained/ram_plus_swin_large_14m.pth`.

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
.\.venv\Scripts\python.exe -m app.cli captions-tags-backfill --source-model-contains qwen --max-tags 8 --apply
.\.venv\Scripts\python.exe -m app.cli image-tags-backfill --only-missing-img --apply
.\.venv\Scripts\python.exe -m app.cli validate-image-tag
Invoke-RestMethod -Uri http://127.0.0.1:8002/health
```

## 10) Current Architecture Gaps / Drift

1. Documentation drift:
- `README.md` and several older architecture docs still describe 2025 defaults and stale provider defaults.

2. Worker dispatch mismatch in current code:
- `ingest.py` enqueues `phash` and video tasks.
- `tasks.py` defines handlers for `phash` and video tasks.
- `TaskExecutor.run_once` currently dispatches only:
  - `embed`, `thumb`, `caption`, `face`, `face_embed`, `person_cluster`, `person_label_propagate`, `dim_backfill`, `image_tag`
- `phash` and video task types are not currently dispatched by `run_once`.

3. Task state naming inconsistency:
- Runtime contains both `done` and `finished` task states.
- Current executor writes `finished`, while some reporting logic still filters by `done`.

4. API runtime drift warning:
- Newly added `/faces/assignment-history` route exists in code but was not visible in current running OpenAPI snapshot during this audit.
- Backend restart/reload is required to align live process with current source.

## 11) Recommended Source of Truth Going Forward

- Operational truth: `docs/PROJECT_STATUS_CURRENT.md`
- Architecture truth (this snapshot title date: 2026-02-27): `docs/architecture/SYSTEM_ARCHITECTURE_CURRENT_2026-02-24.md`
- Code truth:
  - `backend/app/main.py`
  - `backend/app/tasks.py`
  - `backend/app/db.py`
  - `backend/app/routers/people.py`
