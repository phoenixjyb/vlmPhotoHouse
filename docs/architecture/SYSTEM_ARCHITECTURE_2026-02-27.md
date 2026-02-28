# VLM Photo House — System Architecture (2026-02-27)

Supersedes: `SYSTEM_ARCHITECTURE_CURRENT_2026-02-24.md` (archived)

This document is the authoritative architecture reference. It covers the complete
multi-project topology, every AI component, the data model, all pipeline flows,
hardware assignment, and the design rationale behind each major choice.

---

## 1. What This System Is

**vlmPhotoHouse** is a local-first photo and video management system with deep AI
integration. It replaces cloud photo services for a personal archive of ~12,000 photos
and videos by running all AI workloads on local GPU hardware.

Core capabilities:
- **Ingestion**: walk a file tree, extract EXIF/GPS metadata, fingerprint and deduplicate.
- **Visual embeddings**: per-image CLIP-class vectors for semantic similarity search.
- **Image captioning**: Qwen3-VL vision-language model generates natural-language descriptions.
- **Caption-derived tagging**: bilingual canonical tag vocabulary extracted from captions.
- **Image tagging (RAM++)**: RAM++ recognition model produces independent tag set.
- **Face detection**: InsightFace SCRFD detects faces per frame.
- **Face recognition**: LVFace produces 128-dim face embeddings for identity clustering.
- **Person assignment**: manual labeling + Stranger grouping + DNN propagation against named-person centroids.
- **Vector search**: FAISS-backed similarity search over image and face embedding spaces.
- **Hybrid smart search**: combines vector similarity, caption text, and tag filters.
- **Story albums**: generated collections by person/tag/location/caption themes.
- **Similarity reduction**: non-destructive duplicate suppression with explicit restore.
- **GPS map view**: Leaflet-based geographic browsing of geotagged media.
- **Voice integration**: proxies to LLMyTranslate for STT/TTS alongside photo browsing.

Design philosophy: **local-first, no cloud dependencies, data stays on local drives**.
All model weights, indexes, and derived artifacts live on Drive E. The stack runs entirely
on a single Windows 11 workstation.

---

## 2. Multi-Project Topology

The stack is deliberately split into separate repositories/services. Each component runs
in its own Python environment and communicates over localhost HTTP.

```
C:\Users\yanbo\wSpace\vlm-photo-engine\
├── vlmPhotoHouse\          ← Main repo (API, UI, worker, CLI)
├── LVFace\                 ← Face embedding service (ORT-GPU)
├── vlmCaptionModels\       ← Caption HTTP service (Qwen3-VL, BLIP2)
└── archive_unused\         ← Archived scripts and legacy experiments

C:\Users\yanbo\wSpace\
└── llmytranslate\          ← STT/TTS/translation service (voice integration)

C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\
└── rampp\                  ← RAM++ image-tag adapter (runs from vlmPhotoHouse tree)
```

### Why separate repos/processes?

| Reason | Detail |
|--------|--------|
| **Conflicting CUDA runtimes** | LVFace uses ONNX Runtime 1.24 + CUDA 12.x while the main backend uses PyTorch 2.x. Subprocess isolation prevents DLL conflicts. |
| **GPU memory partitioning** | Memory-heavy models (Qwen3-VL 8B, Ollama LLM, voice STT/TTS) stay on RTX 3090, while RAM++ can run on Quadro P2000. Isolation gives each service dedicated VRAM context. |
| **Independent restart** | Caption service can OOM-recover without taking down the whole API. |
| **Separate development velocity** | LVFace and vlmCaptionModels have their own venvs, requirements, and testing cycles. |
| **HTTP protocol** | All external services expose simple `POST /caption`, `POST /tags`, etc. endpoints. The backend calls them with `httpx`. This makes swapping models (BLIP2 → Qwen3) a config change, not a code change. |

### Service ports

| Port | Service | Description |
|------|---------|-------------|
| 8002 | vlmPhotoHouse API | FastAPI, inline worker, static UI host |
| 8102 | vlmCaptionModels | Qwen3-VL-8B nf4 caption server |
| 8112 | rampp/service.py | RAM++ image tagging |
| 8001 | LLMyTranslate | STT/TTS/conversation API (proxied via `/voice/*`) |
| 11434 | Ollama | Local LLM runtime consumed by LLMyTranslate |

---

## 3. Hardware Topology

Single workstation, Windows 11 Pro:

| GPU | Memory | Primary assignment |
|-----|--------|-------------------|
| Quadro P2000 (GPU 0, nvidia-smi) | 5 GB VRAM | RAM++ image tagging, overflow/display workloads |
| RTX 3090 (GPU 1, nvidia-smi) | 24 GB VRAM | Qwen3-VL captioning, voice STT/TTS, primary Ollama load, LVFace embedding |

The `start-dev-multiproc.ps1` launcher pins services to GPUs using `CUDA_VISIBLE_DEVICES`.
Framework-local CUDA indices can differ from `nvidia-smi` ordering.

**Why Quadro P2000 for RAM++?** RAM++ (SwinL backbone, ~700M params) fits in 5 GB and runs
comfortably on P2000, freeing the 3090 for Qwen3-VL which needs ~14–16 GB in nf4 quant.

**Why LVFace on 3090?** ORT CUDA for face embedding runs quickly but needs cuDNN 9 DLLs
which are bundled with the backend's PyTorch install on the 3090.

---

## 4. Python Environment Map

Three distinct Python environments are active in production:

| Env | Path | Contents |
|-----|------|----------|
| **Backend API** | `vlmPhotoHouse/.venv` | Python 3.11, FastAPI, SQLAlchemy, PyTorch 2.x, CLIP, httpx |
| **LVFace** | `LVFace/.venv` | Python 3.11, ONNX Runtime 1.24.2 + CUDA, numpy |
| **vlmCaptionModels** | *(own venv)* | Python 3.11, transformers, PyTorch, Qwen3-VL, bitsandbytes |
| **RAM++** | `vlmPhotoHouse/rampp/.venv-rampp` | Python 3.10, recognize-anything, torch |

> **Note**: `vlmPhotoHouse/backend/.venv` exists but is for tests only (no torch). Never
> use it to run the application. Always use `vlmPhotoHouse/.venv/Scripts/python.exe`.

### cudnn64_9.dll bridging

LVFace's ORT 1.24.2 CUDA provider requires `cudnn64_9.dll`. This DLL is not in the
LVFace venv but IS bundled with the backend venv's PyTorch installation at:

```
vlmPhotoHouse/.venv/Lib/site-packages/torch/lib/cudnn64_9.dll
```

The `LVFaceSubprocessProvider._subprocess_env()` method injects this path into the
subprocess `PATH` before launching the LVFace inference subprocess, so ORT can find
the DLL without any separate cuDNN installation.

---

## 5. AI Components

### 5.1 Face Detection — InsightFace SCRFD

- **Model family**: SCRFD (Sample and Computation Redistribution for Efficient Face Detection)
- **Provider**: `InsightFaceDetectionProvider` in `backend/app/face_detection_service.py`
- **Runs in-process** inside the API worker
- **Output**: bounding boxes, keypoints (5-point landmarks for alignment)
- **Why SCRFD?** Best accuracy/speed tradeoff for dense face detection at mixed image
  resolutions. Handles small faces, partial occlusion, and group shots well.

### 5.2 Face Embedding — LVFace (subprocess + ORT-CUDA)

- **Model**: `LVFace-B_Glint360K.onnx` (ArcFace-family, Glint360K training set)
- **Output**: 128-dimensional L2-normalized face embedding vectors
- **Inference mode**: `src_onnx` via `LVFace/src/inference_onnx.py`
- **Provider**: `LVFaceSubprocessProvider` in `backend/app/lvface_subprocess.py`
- **Execution**: spawns LVFace Python subprocess for each batch; subprocess uses ORT CUDA provider
- **Storage**: per-face `.npy` files in `E:\VLM_DATA\derived\face_embeddings\`

Why subprocess instead of in-process?
- ORT 1.24.2 and PyTorch 2.x have conflicting CUDA runtime expectations
- Subprocess isolation avoids DLL conflicts and allows independent GPU memory allocation

### 5.3 Image Captioning — Qwen3-VL-8B

- **Model**: `Qwen/Qwen3-VL-8B-Instruct`, loaded in 4-bit nf4 quantization
- **VRAM usage**: ~14–16 GB on RTX 3090
- **Service**: `vlmCaptionModels/caption_server.py` FastAPI server on port 8102
- **Backend provider**: `HTTPCaptionProvider` → `CAPTION_SERVICE_URL=http://127.0.0.1:8102`
- **Protocol**: `POST /caption` with multipart image upload; response is a JSON caption string
- **Video support**: task handler extracts a representative keyframe with ffmpeg before sending
  to the caption service
- **OOM handling**: caption server implements automatic retry at smaller image edge / fewer tokens
- **Concurrency**: single-threaded by default (`CAPTION_SERVER_MAX_CONCURRENCY=1`) to prevent
  VRAM fragmentation during long caption queue drains
- **Caption provenance**: stored in `captions` table with `model_version`, `quality_tier`,
  `superseded`, `user_edited` fields

Why Qwen3-VL vs BLIP2?
- Qwen3-VL produces significantly richer, more accurate captions
- nf4 quantization makes it viable in 16 GB VRAM (vs needing 24+ GB in fp16)
- Auto-tagging from captions is gated to Qwen-sourced captions only (model substring check)
  to avoid lower-quality BLIP2-derived tags entering the tag catalog

### 5.4 Caption-Derived Tagging — Bilingual Canonical Mapping

- **Module**: `backend/app/tagging.py`
- **Approach**: deterministic bilingual (EN+ZH) canonical vocabulary mapping
- **Tag selection**: quota-based (≤8 tags per asset), keyword fallback for low-confidence
- **Entry point**: runs automatically after caption generation; also available via
  `captions-tags-backfill` CLI command
- **Provenance field**: `asset_tags.source = 'cap'`
- **Gate**: `CAPTION_AUTO_TAG_SOURCE_MODEL_CONTAINS=qwen` (default) — only Qwen captions
  trigger auto-tagging

### 5.5 Image Tagging — RAM++ (Recognize Anything++)

- **Model**: `ram_plus_swin_large_14m.pth` (SwinL backbone, 14M tag vocabulary)
- **Service**: `vlmPhotoHouse/rampp/service.py` FastAPI on port 8112
- **Backend provider**: `HTTPImageTagProvider` in `backend/app/image_tag_service.py`
- **Protocol**: `POST /tags` with multipart image; response is a JSON list of tag objects
  with `name` and `score` fields
- **Runs on**: Quadro P2000 (GPU 1)
- **Provenance field**: `asset_tags.source = 'img'`
- **Merged source**: when caption and RAM++ both produce the same tag, provenance is `cap+img`
- **Tag suppression**: `asset_tag_blocks` table prevents suppressed auto-tags from re-appearing;
  manual tag-add unblocks
- **Adapter architecture**: `rampp/adapter_rampp.py` is called as a subprocess by `service.py`
  (double subprocess pattern — service calls adapter, adapter calls model — to isolate the
  recognize-anything package from the FastAPI runtime)

### 5.6 Image Embeddings — CLIP-class Vectors

- **Produces**: per-image dense vector stored in `embeddings` table + `.npy` file
- **Storage**: `E:\VLM_DATA\derived\embeddings\`
- **Index**: FAISS in-memory index loaded at API startup from `.npy` files
- **Search backends**: `/search/vector`, `/search/smart` (hybrid), `/search/person/*`
- **Task**: `embed` in the ingestion pipeline

### 5.7 Voice / LLMyTranslate

- **Project**: `C:\Users\yanbo\wSpace\llmytranslate`
- **Capabilities**: STT (speech-to-text), TTS (text-to-speech), conversational LLM,
  streaming and phone-call style WebSocket pipelines
- **Integration (active)**: vlmPhotoHouse backend proxies LLMyTranslate under `/voice/*`
  via `backend/app/routers/voice.py`:
  - `/voice/transcribe`
  - `/voice/tts`
  - `/voice/conversation`
  - `/voice/health`
  - `/voice/capabilities`
  - `/voice/demo`
  - `/voice/command` (Phase-2 read-only orchestrator in Photo House)
    - Current read-only actions: `search.assets`, `search.people`, `search.tags`, `tasks.status`, `system.status`, `search.person.assets`
    - Current kid scenario: voice phrase like `show me the photos of chuan` resolves person and opens the person-assets gallery flow in main UI
- **Current model stack (runtime baseline, 2026-02-27)**:
  - **STT**: OpenAI Whisper `base` (local ASR in LLMyTranslate)
  - **LLM**: Ollama, default conversation model `gemma3:latest`
  - **TTS**: Coqui TTS Tacotron2-family models; Edge TTS fallback when Coqui path fails
- **Current GPU execution snapshot (host-specific)**:
  - `nvidia-smi` index: `0=Quadro P2000`, `1=RTX 3090`
  - STT/TTS runtime observed on RTX 3090 during live checks
  - Ollama may appear on both GPUs on this host, with primary LLM VRAM footprint on RTX 3090
- **Legacy extension routes**: `backend/app/routers/voice_photo.py` exposes extra
  `/voice/*` demo/photo endpoints and requires schema-alignment cleanup before production use
- **Why proxied?** Keeps voice capabilities accessible from the same UI origin (port 8002)
  without cross-origin issues, while LLMyTranslate runs as an independent service

### 5.8 Voice Integration Status and Plan (voice-in + voice-out)

**Goal**: enable voice control for search, people/tag operations, and task orchestration
without bypassing API validation, safety checks, and audit paths.

**Current implementation snapshot (2026-02-27)**:
- Browser UI includes a top-bar `Voice Command` trigger in `/ui`.
- Execution flow: mic capture -> `/voice/transcribe` -> `/voice/command` -> UI navigation/action.
- Read-only person-photo command is active: `search.person.assets` (e.g., `show me the photos of <name>`).
- Mutating commands remain blocked as `mutate.request` until confirmation phase is implemented.

**Scope boundary**:
- **In scope (v1-v2)**: query/search/status flows and concise spoken summaries.
- **In scope (v3+)**: mutating operations with strict confirmation.
- **Out of scope (current)**: direct DB writes or bypassing existing domain APIs.

**Execution model**:
1. **Voice-in**: microphone audio -> `/voice/transcribe` -> normalized text command
2. **Intent/orchestration layer (new)**: map text to a structured action contract
3. **Action execution**: call existing Photo House APIs
4. **Voice-out**: return spoken + text summary through `/voice/tts`

**Planned action contract**:
```json
{
  "action": "search.smart | person.rename | tag.add | task.cancel | ...",
  "mode": "read | mutate",
  "args": {},
  "needs_confirmation": true,
  "confidence": 0.0
}
```

**Route mapping (orchestrator -> existing APIs)**:
- Search intents -> `/search`, `/search/smart`, `/search/captions`, `/search/tags`, `/search/vector`
- People read intents -> `/search/person/*`, `/persons`, `/faces`
- People mutate intents -> `/faces/*/assign`, `/faces/*/assign-stranger`, `/persons/{id}/name`, `/persons/merge`
- Tag intents -> `/tags`, `/tags/{tag_id}/assets`, `/assets/{id}/tags`
- Story/similarity intents -> `/albums/stories`, `/duplicates/reduction/*`, `/assets/suppressed`
- Task intents -> `/tasks`, `/tasks/{id}`, `/tasks/{id}/cancel`, `/admin/tasks/{id}/requeue`

**Safety and confirmation policy**:
- Mutating actions require explicit user confirmation before execution.
- Low-confidence parse falls back to clarification, not execution.
- All writes must flow through existing APIs so current validation/audit remains effective.
- Voice responses must include a short action/result summary with target IDs or counts.

**Phased rollout**:
- **P1**: stabilize `/voice/*` proxy contracts and de-risk legacy `voice_photo` routes
- **P2**: shipped read-only orchestrator (search + status + browse, including person-photo browse) with bilingual summaries
- **P3**: add mutating commands with confirmation + dry-run preview
- **P4**: refine multilingual UX, latency/quality metrics, and interruption behavior

**Acceptance criteria (initial)**:
- Read-only commands dispatch to correct route family and return usable spoken summaries.
- Mutating commands never execute without confirmation.
- Failed actions surface explicit reasons (no silent success-shaped fallback).

---

## 6. Backend Architecture

### 6.1 Entry Point

```
backend/app/main.py
```

FastAPI application. Registers all routers, initialises providers (face, caption, tag),
loads FAISS index, starts inline worker if `ENABLE_INLINE_WORKER=true`.

### 6.2 Configuration

All settings via environment variables in `backend/app/config.py` (Pydantic Settings).
No config files needed at runtime. Key settings:

```
FACE_EMBED_PROVIDER=lvface          # stub|lvface|facenet|insight|auto
LVFACE_EXTERNAL_DIR=...             # path to LVFace project root
LVFACE_PYTHON_EXE=...               # LVFace venv python
LVFACE_MODEL_NAME=LVFace-B_Glint360K.onnx
FACE_EMBED_DIM=128
CAPTION_PROVIDER=http               # stub|http|blip2|qwen3-vl|auto
CAPTION_SERVICE_URL=http://127.0.0.1:8102
IMAGE_TAG_PROVIDER=http             # stub|http|auto
IMAGE_TAG_SERVICE_URL=http://127.0.0.1:8112
DATABASE_URL=sqlite:///E:/VLM_DATA/databases/metadata.sqlite
VLM_DATA_ROOT=E:\VLM_DATA
ORIGINALS_PATH=E:\01_INCOMING
ENABLE_INLINE_WORKER=true
CAPTION_AUTO_TAG_SOURCE_MODEL_CONTAINS=qwen
```

### 6.3 Task Queue and Worker

- **Storage**: `tasks` table in SQLite
- **Worker**: inline — runs in a background asyncio task within the API process
- **State machine**: `pending → running → finished` (also `failed`, legacy `done`)
- **No auto-reset**: if the process dies with `running` tasks, they must be manually reset
  to `pending` before restarting. This is by design (prevents duplicate processing).

Task types dispatched by `TaskExecutor.run_once`:

| Task type | Handler | Description |
|-----------|---------|-------------|
| `embed` | `handle_embed` | Generate CLIP image embedding |
| `thumb` | `handle_thumb` | Generate 256 + 1024 px thumbnails |
| `caption` | `handle_caption` | Run VLM caption via HTTP provider |
| `face` | `handle_face` | Run face detection, generate crops |
| `face_embed` | `handle_face_embed` | Run LVFace embedding on each crop |
| `person_cluster` | `handle_cluster` | Re-cluster person embeddings |
| `person_label_propagate` | `handle_propagate` | Propagate manual labels via centroid matching |
| `dim_backfill` | `handle_dim_backfill` | Backfill embedding dim metadata |
| `image_tag` | `handle_image_tag` | Run RAM++ tagging via HTTP provider |

> **Known gap**: `phash` and video task types (`video_probe`, `video_keyframes`, `video_embed`,
> `video_scene_detect`) are enqueued by `ingest.py` and have handler functions in `tasks.py`
> but are **not dispatched** by `run_once`. They silently stay pending.

### 6.4 Routers

| Router | File | Routes |
|--------|------|--------|
| People / faces | `routers/people.py` | `/persons/*`, `/faces/*`, `/search/*` |
| Albums / similarity | `main.py` | `/albums/time`, `/albums/stories`, `/duplicates/*`, `/assets/suppressed` |
| Assets | `routers/assets.py` (in services/) | `/assets/*` |
| UI static | `routers/ui.py` | `/ui` (serves index.html + JS/CSS) |
| Voice proxy | `routers/voice.py` | `/voice/*` → LLMyTranslate |
| Voice photo (legacy) | `routers/voice_photo.py` | `/voice/describe-photo`, `/voice/search-photos`, `/voice/rtx3090-status`, `/voice/photo-demo` |

### 6.5 Provider Architecture

Provider pattern: each capability has a base class with stub and real implementations.
Providers are selected via config at startup.

```
face_detection_service.py   → FaceDetectionProvider
    StubFaceDetectionProvider
    InsightFaceDetectionProvider         ← active (SCRFD)

face_embedding_service.py   → FaceEmbeddingProvider
    StubFaceEmbeddingProvider
    LVFaceSubprocessProvider             ← active (subprocess + ORT CUDA)
    (lvface_subprocess.py)

caption_service.py          → CaptionProvider
    StubCaptionProvider
    HTTPCaptionProvider                  ← active (→ port 8102)
    (caption_subprocess.py — available)

image_tag_service.py        → ImageTagProvider
    StubImageTagProvider
    HTTPImageTagProvider                 ← active (→ port 8112)
```

This allows the system to run with stubs (no GPU needed) for development/testing.

---

## 7. Database Model

SQLite at `E:\VLM_DATA\databases\metadata.sqlite`. Managed by SQLAlchemy 2.x + Alembic.
8 migration versions from initial schema to current.

### Core tables

| Table | Key columns | Purpose |
|-------|-------------|---------|
| `assets` | `id`, `path`, `sha256`, `media_type`, `exif_datetime`, `gps_lat/lon`, `caption_*` flags | Master catalog of all media files |
| `embeddings` | `asset_id`, `model`, `vector_path`, `dim` | Per-asset embedding metadata |
| `captions` | `asset_id`, `text`, `model_version`, `quality_tier`, `superseded`, `user_edited` | Caption variants with provenance |
| `face_detections` | `id`, `asset_id`, `bbox_*`, `embedding_path`, `person_id`, `label_source` | Per-face detections and assignments |
| `persons` | `id`, `name`, `face_count` | Named person identities |
| `tasks` | `id`, `type`, `asset_id`, `state`, `retry_count`, `started_at`, `progress` | Async task queue |
| `tags` | `id`, `name`, `lang` | Global tag vocabulary |
| `asset_tags` | `asset_id`, `tag_id`, `source`, `score`, `model` | Asset↔tag links with provenance |
| `asset_tag_blocks` | `asset_id`, `tag_id` | Suppressed auto-tags |
| `video_segments` | `asset_id`, `start_time`, `end_time`, `embedding_path` | Video scene segments |
| `face_assignment_events` | `face_id`, `person_id`, `event_type`, `label_source` | Audit trail for face assignments |

### Provenance tracking

The system tracks *where* each data item came from:
- `face_detections.label_source`: `'manual'` (UI assignment) or `'dnn'` (propagation/auto-assign)
- `asset_tags.source`: `'cap'` (caption-derived), `'img'` (RAM++), `'cap+img'` (both)
- `captions.model_version`: records which model version produced the caption
- `captions.user_edited`: marks user-edited captions as protected from auto-overwrite

---

## 8. Pipeline Flows

### 8.1 Ingestion

```
POST /ingest/scan  (or CLI ingest-scan)
         │
         ▼
  ingest.py: walk E:\01_INCOMING
         │
    per file:
    ├── create/update assets row
    ├── extract EXIF datetime, GPS, camera
    ├── for images: enqueue → embed, phash, thumb, caption, face
    └── for videos: enqueue → video_probe, video_keyframes, video_embed
```

### 8.2 Embedding Pipeline (images)

```
task: embed
  └── load image (EXIF-rotation corrected)
  └── run CLIP-class model
  └── write .npy to E:\VLM_DATA\derived\embeddings\
  └── write embeddings row (vector_path, dim)
  └── update FAISS index in memory
```

### 8.3 Caption Pipeline

```
task: caption
  └── if video: extract representative frame with ffmpeg
  └── POST image to http://127.0.0.1:8102/caption
  └── receive caption text
  └── upsert captions row (model_version, quality_tier)
  └── update assets.caption_* fields
  └── run tagging.py canonical mapping → upsert asset_tags (source='cap')
```

### 8.4 Face Pipeline

```
task: face
  └── load image (EXIF-corrected)
  └── InsightFaceDetectionProvider → bounding boxes + landmarks
  └── for each face:
      ├── generate aligned face crop → E:\VLM_DATA\derived\faces\256\
      ├── insert face_detections row (bbox, embedding_path=None, person_id=None)
      └── enqueue face_embed task

task: face_embed
  └── load face crop
  └── LVFaceSubprocessProvider (subprocess → ORT CUDA)
      └── inference_onnx.py: 112×112 aligned crop → 128-dim L2 vector
  └── write .npy to E:\VLM_DATA\derived\face_embeddings\
  └── update face_detections.embedding_path
```

### 8.5 Person Assignment

```
Manual path (UI/API):
  POST /faces/{face_id}/assign           → label_source='manual'
  POST /faces/{face_id}/assign-stranger  → assigns/reuses named person 'Stranger'
  └── enqueue person_label_propagate task for affected identity

task: person_label_propagate
  └── load manual-labeled face embeddings for each known person
  └── compute centroid per person
  └── for each unassigned face:
      ├── score = cosine_similarity(face_embed, centroid)
      ├── if score ≥ threshold AND margin ≥ margin_threshold:
      │       assign face → person, label_source='dnn'
      └── log face_assignment_events row

Auto-assign path (CLI):
  python -m app.cli faces-auto-assign [options]
  └── same centroid/scoring logic
  └── dry-run by default; --apply to commit
  └── supports per-person thresholds, min-ref-faces, --include-dnn-assigned
```

### 8.6 Image Tagging (RAM++)

```
task: image_tag
  └── load image
  └── POST to http://127.0.0.1:8112/tags
  └── receive list of {name, score} dicts
  └── upsert tags + asset_tags (source='img')
  └── merge with existing 'cap' tags → source becomes 'cap+img' if overlap
```

### 8.7 Search

```
/search/vector      → FAISS kNN on image embeddings
/search/smart       → hybrid: FAISS + caption FTS + tag filter + person filter
/search/person/*    → person-scoped similarity search
```

### 8.8 Story Albums

```
GET /albums/stories
  └── generate grouped albums by:
      person  (face assignments)
      tag     (asset_tags topics)
      location(gps bucket)
      caption (caption keyword themes)
  └── return story metadata + sample asset items + context-open hints
```

### 8.9 Similarity Reduction

```
GET  /duplicates/reduction/preview
  └── build exact (sha256) + near (phash distance) groups
  └── choose best candidate per group, mark others as hide candidates

POST /duplicates/reduction/apply
  └── set hide candidates to assets.status='suppressed' (no deletion)

POST /duplicates/reduction/restore
  └── restore suppressed assets back to assets.status='active'
```

---

## 9. Frontend Architecture

Single-page web application. Server-hosted as static files from `backend/app/ui/`:

| File | Role |
|------|------|
| `index.html` | Shell with tab structure |
| `app.js` | All client-side logic (~5000 lines, vanilla JS) |
| `styles.css` | CSS |

Main tabs:
- **Library**: asset grid, search (text/vector/hybrid), asset inspector (media player,
  captions panel, tags panel with remove/block flow, face assignment panel per asset)
- **People**: named/unnamed person list, per-person asset gallery, unassigned face queue
  with manual assignment + Stranger quick-label action
- **Tags**: global tag catalog and tag-scoped asset browsing
- **Stories**: generated albums by person/tag/location/caption themes
- **Similarity**: duplicate reduction preview/apply/restore (non-destructive)
- **Map**: Leaflet GPS visualization of geotagged media (`/assets/geo`)
- **Tasks**: live queue monitor, cancel actions
- **Admin**: health/metrics dashboard (tags, face counts, embed counts), index rebuild,
  recluster, ingest trigger

The UI talks exclusively to the vlmPhotoHouse API at port 8002. No external dependencies.

---

## 10. Startup Topology

Primary launcher: `vlmPhotoHouse/scripts/start-dev-multiproc.ps1`

Opens a Windows Terminal 2×2 grid (+ optional RAM++ tab):

| Pane | Service | Command |
|------|---------|---------|
| Top-left | vlmPhotoHouse API + worker | `uvicorn app.main:app --port 8002` (from backend/) |
| Top-right | LLMyTranslate voice service (ASR) | `uvicorn src.main:app --host 127.0.0.1 --port 8001` |
| Bottom-left | LVFace environment shell | activate LVFace venv for face-model ops |
| Bottom-right | LLMyTranslate TTS environment shell | activate `.venv-tts` for Coqui/Edge TTS ops |
| Extra tab (optional) | RAM++ tag service | `uvicorn service:app --host 127.0.0.1 --port 8112` (from `rampp/`) |

Caption service (`vlmCaptionModels`, port 8102) is expected to be running separately for HTTP caption provider mode.

**Env vars** are set in the launcher script and inherited by all processes. The most
critical are the `FACE_EMBED_PROVIDER=lvface` and `LVFACE_*` vars — without them the API
falls back to `StubFaceEmbeddingProvider` silently.

---

## 11. Operational Commands

### Health check (always use --noproxy — Clash proxy intercepts localhost)

```bash
curl -s --noproxy '*' http://127.0.0.1:8002/health
```

### Reset stuck running tasks (after unclean shutdown)

```python
import sqlite3
con = sqlite3.connect(r"E:/VLM_DATA/databases/metadata.sqlite")
cur = con.cursor()
cur.execute("UPDATE tasks SET state='pending', started_at=NULL WHERE state='running'")
con.commit(); con.close()
```

### Face auto-assign (from backend/, using repo-root venv)

```powershell
# dry-run — core persons, conservative
..\venv\Scripts\python.exe -m app.cli faces-auto-assign `
    --score-threshold 0.35 --margin 0.08 --min-ref-faces 10 `
    --reference-manual-only --limit 0

# apply — all persons with ≥2 refs
..\venv\Scripts\python.exe -m app.cli faces-auto-assign `
    --score-threshold 0.30 --margin 0.05 --min-ref-faces 2 `
    --reference-manual-only --apply --limit 0

# re-evaluate DNN assignments with updated refs
..\venv\Scripts\python.exe -m app.cli faces-auto-assign `
    --score-threshold 0.30 --margin 0.05 --min-ref-faces 2 `
    --reference-manual-only --include-dnn-assigned --apply --limit 0
```

### Caption tags backfill

```powershell
..\venv\Scripts\python.exe -m app.cli captions-tags-backfill `
    --source-model-contains qwen --max-tags 8 --apply
```

### Image tags backfill (RAM++)

```powershell
..\venv\Scripts\python.exe -m app.cli image-tags-backfill --only-missing-img --apply
```

---

## 12. Current Status Snapshot (2026-02-27)

| Metric | Value |
|--------|-------|
| Total assets | 12,336 |
| Images | 9,979 |
| Videos | 2,357 |
| Face detections | 15,979 |
| Faces assigned (named person) | ~11,099 |
| Faces unassigned | ~4,880 |
| Captions (active variants) | ~24,464 |
| Caption queue pending | ~4,880 (draining) |
| Image tag links | ~30,567 |
| Named persons | 38 total; 14 with manual reference faces |
| Face embed provider | LVFaceSubprocessProvider (CUDA active) |
| Caption provider | HTTPCaptionProvider → Qwen3-VL-8B nf4 |
| Image tag provider | HTTPImageTagProvider → RAM++ |

### Named persons (with face counts after 2026-02-26 session)

| Person | Face count |
|--------|-----------|
| jane_newborn | 4,238 |
| jane | 2,838 |
| chuan | 1,230 |
| yanbo | 1,021 |
| yixia | 496 |
| meiying | 482 |
| zhiqiang | 344 |
| guansuo | 303 |
| caoyujia | 46 |
| caoyuxin | 29 |
| gaozhu | 23 |
| yinzhi | 9 |
| mumu | 8 |
| dave | 8 |

Persons with only 1 manual reference (yang, james, zengyinqing, shixianhai, zeze):
cannot be safely auto-assigned from a single reference face.

---

## 13. Design Rationale Summary

| Design choice | Why |
|---------------|-----|
| **Local-first, no cloud** | Privacy; personal family archive; no subscription; no data egress |
| **SQLite** | Sufficient for ~12K assets on a single machine; no server to manage; Alembic migrations keep schema controlled |
| **Inline worker** | Avoids separate Celery/Redis stack; simplicity over throughput (throughput is GPU-bound anyway) |
| **HTTP between services** | Loose coupling; independent restart; model swap is a config change; works across Python environments |
| **Subprocess for LVFace** | Avoids CUDA DLL conflicts between PyTorch 2.x and ORT 1.24.x |
| **Dual GPU** | RTX 3090 for memory-hungry models (Qwen3-VL 8B); P2000 for lighter workloads (RAM++) |
| **Provider pattern** | Stub implementations enable CPU-only dev without any GPU; easy to swap models |
| **Manual-first face assignment** | Face recognition errors compound; human review of high-confidence assignments is essential for a personal archive |
| **DNN propagation as feedback loop** | After manual seeding, the centroid-based auto-assign scales well; only manual ground truth is used as reference |
| **Bilingual canonical tags** | Family archive has mixed EN/ZH context; canonical mapping ensures consistent tag vocabulary |
| **Qwen gate for caption tags** | BLIP2 captions are lower quality; gating prevents noise in the tag catalog |

---

## 14. Known Gaps and Issues

1. **phash and video task types not dispatched**: `ingest.py` enqueues `phash`,
   `video_probe`, `video_keyframes`, `video_embed`. None of these are handled by
   `TaskExecutor.run_once`. They accumulate in `pending` state indefinitely.

2. **Task state naming inconsistency**: both `done` (legacy) and `finished` (current)
   exist in production DB. Some reporting queries filter by one or the other.

3. **FAISS index rebuilt from disk on restart**: no persistent index file; startup reads
   all `.npy` files. Slow if many embeddings but acceptable for current asset count.

4. **No automatic `running` → `pending` reset on startup**: by design (avoids duplicate
   work), but requires manual intervention after crashes.

5. **LVFace subprocess spawn per batch**: LVFace process is spawned and destroyed per
   embedding batch. No persistent subprocess daemon. Acceptable for background queue
   processing but adds ~1s overhead per batch.

6. **Single-threaded caption server**: `CAPTION_SERVER_MAX_CONCURRENCY=1`. Multiple
   simultaneous caption requests queue up. This is intentional (VRAM management) but
   limits throughput.

---

## 15. Source of Truth Hierarchy

| Layer | Source |
|-------|--------|
| Operational status | `docs/PROJECT_STATUS_CURRENT.md` |
| Architecture (this doc) | `docs/architecture/SYSTEM_ARCHITECTURE_2026-02-27.md` |
| Code truth (entry points) | `backend/app/main.py`, `backend/app/tasks.py`, `backend/app/db.py` |
| Configuration | `backend/app/config.py` |
| DB schema | `backend/app/db.py` + `backend/alembic/versions/` |
| Onboarding | `CLAUDE.md` (repo root) |
| Per-session notes | `docs/HANDOFF_CLAUDE_*.md` |
