# Functional Requirements (Code-Aligned Baseline)

This document is aligned to the current backend implementation in `backend/app`.

## 1) Ingestion & Metadata
- Must ingest media from configured roots via API/CLI (`/ingest/scan`, ingest CLI).
- Must extract and persist file identity and metadata (hash, EXIF/GPS/time where available).
- Must support idempotent re-scan behavior and exact duplicate handling.
- Must expose duplicate analysis endpoints (`/duplicates`, `/duplicates/near`) and keep/delete flows.

## 2) Derived Processing & Task Queue
- Must enqueue and execute asynchronous work via `tasks` table state machine.
- Must support at least these task flows in production:
  - `thumb`, `embed`, `caption`, `face`, `face_embed`, `person_cluster`, `person_label_propagate`, `image_tag`
- Must support retries, dead-letter handling, and manual requeue (`/admin/tasks/{id}/requeue`).
- Known gap: some video/phash task types may be enqueued but are not currently dispatched by worker `run_once`.

## 3) Search & Retrieval
- Must support:
  - Path search (`GET /search`)
  - Caption search (`POST /search/captions`)
  - Tag search (`POST /search/tags`)
  - Smart/hybrid search (`POST /search/smart`)
  - Vector search (`POST /search/vector`)
  - Person search (`/search/person/*`)
- Must return asset references that are resolvable via media/thumbnail endpoints.

## 4) Captions
- Must provide caption list/regenerate/update/delete APIs for each asset.
- Must support external caption provider integration via config (current production path is HTTP caption service).
- Must preserve model/source metadata needed for downstream tagging and audit.

## 5) Tagging
- Must support per-asset tag CRUD and global tag catalog browsing.
- Must preserve provenance fields on tag links (`cap|img|cap+img|manual|rule`).
- Must prevent removed auto-tags from immediate re-appearance via blocklist semantics.
- Must expose tag-to-asset navigation for both image and video assets.

## 6) Faces & People
- Must support face listing, crop retrieval, assignment/unassignment, and bulk assignment/deletion.
- Must support person CRUD-style operations needed by workflow (create, rename, merge, delete, recluster trigger/status).
- Must preserve assignment audit events for person/face changes.

## 7) Voice (Current + Planned)
- Current:
  - Must proxy STT/TTS/conversation/health/capabilities through `/voice/*` to LLMyTranslate.
  - Must provide `POST /voice/command` read-only orchestration with structured contract output.
  - Must support person-photo browse intent (`search.person.assets`) so commands like "show me the photos of chuan" can resolve person and return person-asset payload.
  - Must support optional local TTS fallback when upstream voice service returns no audio.
- Planned:
  - Must parse voice text into a structured action contract (`action`, `mode`, `args`, `needs_confirmation`, `confidence`).
  - Must keep read-only actions (search/status/browse) routed through existing APIs.
  - Must expand voice command orchestration coverage to additional domain actions (search/people/tags/tasks).
  - Low-confidence parsing must trigger clarification and never execute mutating actions.
  - Explicit confirmation required for mutating voice commands before execution.

## 8) Operations & Observability
- Must expose health and metrics surfaces (`/health`, `/metrics`, `/metrics.prom`, provider health endpoints).
- Must expose task inspection/cancellation APIs.
- Must keep runtime configurable by environment variables (provider selection, service URLs, data paths).

## Non-Functional Summary
- Local-first deployment on Windows is the baseline.
- Reliability is prioritized over silent fallback for mutating operations.
- Documentation and API behavior should stay source-aligned with active routes in `main.py` and `routers/*`.
