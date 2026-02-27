# Roadmap (Code-Aligned)

This roadmap reflects what is implemented in `backend/app` today and what is next.

## Status Legend
- ✅ Done
- 🔄 In progress
- ⚠️ Partial / known gap
- 📋 Planned

## Phase 0 — Foundation
- FastAPI service, SQLite schema/migrations, basic health/metrics surface ✅

## Phase 1 — Ingestion & Metadata
- Ingest scan API/CLI (`/ingest/scan`, CLI ingest commands) ✅
- Hash + EXIF/GPS extraction pipeline ✅
- Exact duplicate handling + near-duplicate endpoints (`/duplicates`, `/duplicates/near`) ✅

## Phase 2 — Thumbnails, Embeddings, Search
- Thumbnail generation and serving (`/assets/{id}/thumbnail`) ✅
- Image/text embedding pipeline with persisted index (`/search/vector`, `/vector-index/rebuild`) ✅
- Search surfaces: path/caption/tag/smart/person/vector ✅
- ANN/HNSW/IVF acceleration ⚠️

## Phase 3 — Captions & Tagging
- HTTP caption provider integration (Qwen3-VL service path) ✅
- Caption management APIs (`/assets/{id}/captions`, regenerate/update/delete) ✅
- Canonical caption-derived tagging with provenance (`cap`) ✅
- RAM++ image tagging integration with provenance merge (`img`, `cap+img`) ✅
- Tag catalog + tag->asset browsing APIs (`/tags`, `/tags/{tag_id}/assets`) ✅

## Phase 4 — Faces & People
- Face detection + embedding pipeline integration ✅
- Person assignment, merge/rename/delete, recluster operations ✅
- Person-based search endpoints (`/search/person/*`) ✅

## Phase 5 — Voice Integration
- Voice proxy endpoints in Photo House (`/voice/transcribe|tts|conversation|health|capabilities`) ✅
- Voice command orchestration to existing domain APIs (search/people/tags/tasks) 🔄
- Read-only voice actions with bilingual spoken summaries (including `search.person.assets`) ✅
- Main UI voice trigger for person-photo browse flow (`show me the photos of <name>`) ✅
- Mutating voice action confirmation + dry-run preview before execution 📋
- Legacy `voice_photo` routes schema alignment cleanup ⚠️

## Phase 6 — Video & Events
- Video search/segment endpoints exist (`/search/video*`, `/videos/*`) ⚠️
- Event/theme albuming and DSL 📋
- Known gap: some enqueued video/phash task types are not dispatched by worker `run_once` ⚠️

## Phase 7 — Hardening & Operations
- Dead-letter queue + requeue endpoints ✅
- Queue/task observability (`/metrics`, `/metrics.prom`, task APIs) ✅
- Auth/RBAC/audit logging 📋
- Backup/restore and Postgres migration option 📋

## Current Priorities
1. Add mutating voice commands with explicit confirmation + dry-run preview.
2. Cleanup/align legacy voice-photo routes.
3. Close video task dispatch gap.
4. Continue reliability/observability hardening.
5. Keep caption/tag pipelines stable while backlogs drain.

---
_Last updated: 2026-02-27_
