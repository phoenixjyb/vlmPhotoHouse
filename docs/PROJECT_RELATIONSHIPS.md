# Project Relationships and Architecture

## Overview
VLM Photo House is the orchestration and product surface; companion projects provide model/runtime capabilities.  
This doc reflects the code-level integration currently present in `backend/app`.

## Repositories and Responsibilities

### 1) `vlm-photo-engine/vlmPhotoHouse` (primary)
- API, worker queue, SQLite metadata, Web UI, CLI.
- Owns user-facing flows for ingest, search, people, tags, and task operations.
- Key APIs include:
  - Search: `/search`, `/search/smart`, `/search/captions`, `/search/tags`, `/search/vector`
  - People/faces: `/persons/*`, `/faces/*`, `/search/person/*`
  - Tags: `/tags`, `/tags/{tag_id}/assets`, `/assets/{id}/tags`
  - Tasks/admin: `/tasks/*`, `/admin/tasks/*`

### 2) `vlmCaptionModels`
- External caption service used by Photo House over HTTP.
- Typical runtime endpoint from Photo House config: `CAPTION_SERVICE_URL=http://127.0.0.1:8102`.

### 3) `LVFace`
- External face embedding project used via subprocess integration.
- Selected from Photo House provider config; execution remains controlled by Photo House.

### 4) `llmytranslate`
- External voice runtime (ASR/TTS/conversation + streaming/phone-call features).
- Consumed by Photo House through `/voice/*` proxy routes.
- Uses local Ollama runtime for conversational LLM (`http://127.0.0.1:11434` by default).

### 5) `vlmPhotoHouse/rampp` (in-repo service module)
- In-repo RAM++ tag service and adapter (`rampp/service.py`, `rampp/adapter_rampp.py`).
- Exposes HTTP tagging endpoint to backend image-tag provider (`IMAGE_TAG_SERVICE_URL`, default `http://127.0.0.1:8112`).

## Runtime Topology (Current Defaults)

- Photo House API/UI: `http://127.0.0.1:8002`
- LLMyTranslate: `http://127.0.0.1:8001`
- Caption service: `http://127.0.0.1:8102`
- RAM++ tag service: `http://127.0.0.1:8112`
- Ollama runtime (for LLMyTranslate LLM): `http://127.0.0.1:11434`

## Integration Boundaries

### Caption boundary (active)
- Backend caption provider calls external caption service over HTTP (`CAPTION_PROVIDER=http` + `CAPTION_SERVICE_URL`).
- Caption writes are persisted in Photo House DB and all downstream tag derivation remains in Photo House logic.

### Face boundary (active)
- Face embedding is delegated to LVFace subprocess/HTTP provider depending on config (`FACE_EMBED_PROVIDER`, `LVFACE_*`).
- Face detection/assignment orchestration and person identity mutations remain in Photo House APIs/workers.

### Image-tag boundary (active)
- Backend image-tag provider calls RAM++ tag service over HTTP (`IMAGE_TAG_PROVIDER=http` + `IMAGE_TAG_SERVICE_URL`).
- Tag merge/suppression policy (`cap|img|cap+img` and `asset_tag_blocks`) remains in Photo House.

### Voice boundary (active)
Photo House proxies to LLMyTranslate through `backend/app/routers/voice.py`:
- `POST /voice/transcribe` -> `/api/voice-chat/transcribe`
- `POST /voice/tts` -> `/api/tts/synthesize`
- `POST /voice/conversation` -> `/api/voice-chat/conversation`
- `GET /voice/health` -> `/api/voice-chat/health`
- `GET /voice/capabilities` -> `/api/voice-chat/capabilities`
- `POST /voice/command` executes the Photo House read-only command orchestrator (not proxied upstream)
  - Current read-only actions include: `search.assets`, `search.people`, `search.tags`, `tasks.status`, `system.status`, `search.person.assets`
  - Kid scenario implemented: voice phrase like `show me the photos of chuan` resolves person and opens person-assets flow in UI

Current runtime baseline (2026-02-27):
- STT: Whisper `base`
- LLM: Ollama (`gemma3:latest` default in conversation route)
- TTS: Coqui Tacotron2-family models with Edge fallback
- Host GPU snapshot: `nvidia-smi` index `0=P2000`, `1=RTX3090`; observed voice runtime is RTX3090-centric, while Ollama can attach to both GPUs

### Voice boundary (legacy extension)
`backend/app/routers/voice_photo.py` exposes extra `/voice/*` demo/photo endpoints (`describe-photo`, `search-photos`, `rtx3090-status`, `photo-demo`).  
These routes are legacy and need schema-alignment cleanup before being treated as production voice-photo actions.

### Data/action boundary
All mutating domain actions (people assignment, tags, tasks) remain in Photo House APIs; external services do not mutate Photo House DB directly.

## Development Orchestration

`scripts/start-dev-multiproc.ps1` coordinates the multi-service dev stack:
1. Photo House API/worker pane
2. LLMyTranslate service pane (ASR/conversation)
3. LVFace environment pane
4. LLMyTranslate TTS environment pane
5. Optional RAM++ service pane

Caption service (`vlmCaptionModels`, port 8102) is expected to run separately in HTTP-provider mode.

## Current Direction

- Keep LLMyTranslate as speech runtime.
- Keep extending the Photo House voice command orchestrator (intent -> existing API calls).
- Read actions are active (including person-photo browse); mutating actions now run via explicit confirmation flow (rename, merge, assign Stranger, add tag).
- Return bilingual concise voice/text summaries for outcomes.
- Use phased rollout defined in architecture doc (`SYSTEM_ARCHITECTURE_2026-02-27.md`, section 5.8).
- Keep service boundaries explicit: external model runtimes compute; Photo House owns state, policy, and mutations.

---
*Last Updated: 2026-02-28*
*Version: 2.7*
