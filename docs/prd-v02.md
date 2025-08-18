# Product Requirements Document (v0.2)

Date: 2025-08-18

## Summary
Add a lightweight web UI with voice or text driven commands/search, a gallery for photos and videos, and an admin area to configure providers and monitor health. Voice features (ASR, TTS, optional voice conversation) are provided by an external service (llmytranslate) and proxied by the backend.

## Goals
- Voice or text to retrieve, search, and issue commands.
- Gallery UI showing images and videos with filters and lightbox.
- Admin UI for configuration and health/metrics.
- Keep the backend simple: use existing APIs and new voice proxy endpoints.

## Non‑Goals
- Full desktop photo manager features (albums sync/export) in this phase.
- Complex RBAC or multi‑tenant auth.

## Personas
- Owner: manages ingestion, runs heavy models, adjusts settings, and bulk generates captions.
- Viewer: searches and browses; may use voice to find content quickly.

## Key features
1. Command Bar with Voice
	- PTT mic (Space key), language toggle (EN/中文), transcript preview.
	- Text entry with shortcuts. Submit to search or to a command parser.
	- Endpoints: `POST /voice/transcribe`, `POST /voice/tts` (for response), `POST /voice/conversation` (optional end‑to‑end).

2. Search + Gallery
	- Grid of mixed media (images/videos), infinite scroll, filters (time, faces, tags, type, path prefixes).
	- Lightbox with metadata, faces, caption editor.
	- Uses existing search/list endpoints; add pagination where missing.

3. Admin
	- Health/metrics surface: `/health`, `/metrics`, voice `/voice/health`, `/voice/capabilities`.
	- Configuration: toggle VIDEO_ENABLED, caption provider profile (Fast/Balanced/Quality/Auto), voice external base URL and paths.
	- Tools: vector index rebuild, (re)embed, recluster, ingest watch controls.

## Caption model profiles
- Fast → provider `vitgpt2` (lightweight, quick preview captions via `inference.py`)
- Balanced → `blip2`
- Quality → `qwen2.5-vl` or `llava-next` (configurable)
- Auto → choose based on priority; optionally upgrade from Fast to higher profiles asynchronously.

## Voice integration (llmytranslate)
- Backend proxies to an external service via env:
  - VOICE_EXTERNAL_BASE_URL, VOICE_*_PATH defaults mapped to llmytranslate.
- Exposed endpoints in backend:
  - `POST /voice/transcribe`, `POST /voice/tts` (streams audio), `POST /voice/conversation`, `GET /voice/health`, `GET /voice/capabilities`.
- UI surfaces a minimal voice panel and a test page.

## UX principles
- Profiles over raw model names; “Advanced” reveals exact provider/model.
- Clear timings (STT/LLM/TTS), error toasts, and graceful fallbacks.
- CN/EN throughout: input, captions, TTS voices.

## Acceptance criteria
- Voice transcription returns text for EN and ZH; TTS returns playable audio.
- Gallery lists images and videos with filters and opens a lightbox.
- Admin shows health/metrics and allows toggling video and caption profile.
- Caption batch job works with chosen profile; vitgpt2 path verified.

## Open questions
- WebSocket/SSE for live task progress now or later?
- How to store multi‑caption variants’ provenance in UI edits?

