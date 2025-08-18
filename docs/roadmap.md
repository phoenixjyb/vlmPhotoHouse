# Project Roadmap — status as of 2025-08-18

Legend: [x] Done • [~] In progress/Partial • [ ] Planned

## 1) Core correctness & robustness
- [x] Alembic migrations baseline and fixes for SQLite (idempotent, circular-dependency-safe)
- [x] Backfill/guards for existing DBs via idempotent migrations
- [~] Transactional task execution & structured error logging (basic logging; JSON and correlation IDs planned)

## 2) Task system hardening
- [x] Progress tracking fields (started_at, finished_at, progress_current/total)
- [x] Cancellation support (schema + behavior; tests present)
- [ ] Rate limiting / batching heavy tasks
- [x] Dead-letter queue + requeue CLI

## 3) Embeddings & search quality
- [~] Real image/text embedding model integration behind flags (LVFace external subprocess wired; captions external wired with vit-gpt2/BLIP2/Qwen; improve docs & CPU/GPU toggles)
- [~] Persist device/model_version; rebuild indices on change (schema done; auto re-embed/reindex to be finalized)
- [ ] Vector search filters & pagination across endpoints
- [~] Optional approximate backend (FAISS) abstraction available, gated via settings

## 4) Face pipeline evolution
- [~] Recluster tooling and endpoints present; facenet/lvface available behind flags
- [ ] Real detector enablement (MTCNN/InsightFace), unassigned faces endpoint, cluster merge suggestions

## 5) Duplicate & near-duplicate refinement
- [ ] Hamming distance histogram; merge/variant actions; perceptual diff thumbnails

## 6) API & schema polish
- [ ] Unified envelope {api_version, data, meta}
- [ ] Error model standardization across endpoints
- [~] Docs & tags (OpenAPI present; needs curation)

## 7) Observability & ops
- [x] Health/readiness endpoints and basic metrics
- [ ] Structured JSON logs with correlation id
- [ ] Prometheus exporter (expose warmup/caption latency; face/caption provider names and device)

## 8) Performance & scalability
- [ ] Batch clustering DB writes
- [ ] Memory-map embeddings for faster load
- [ ] Parallel workers & locking

## 9) Testing & quality
- [~] Solid base tests; coverage moderate; expand around vector search, duplicates, merges
- [ ] Property-based tests for clustering
- [ ] Larger ingest integration test

## 10) Developer ergonomics
- [x] Windows Terminal multi‑pane launcher with presets (+ LVFace/Caption/Voice panes)
- [x] WSL tmux launcher and setup guide
- [x] Quick-start guide for Windows launcher and unified ports
- [ ] Makefile / pre-commit hooks (ruff, mypy, black)
- [ ] Dev data seeding targets

## 11) Security & resilience
- [~] Retry backoff controls via settings; more validation needed
- [ ] Ingest path and image size/MIME validation hardening

## 12) Future UX hooks
- [ ] Websocket/SSE task progress
- [ ] Lightweight UI for persons/search/duplicates

---

## Completed beyond the original draft
- [x] Video ingestion (ffprobe/ffmpeg), keyframes/embeddings, and in-memory video index
- [x] Optional scene segmentation; persisted `VideoSegment` + segment embeddings and search
- [x] Caption and tag system: caption search (case-insensitive), tag CRUD/search, and hybrid “smart” search
- [x] Multi-caption variants per asset (max 3) and caption word cap; regenerate/list endpoints
- [x] Admin caption PATCH/DELETE; preserve user-edited variants
- [x] Unified CLI with migrate/revision/stamp and index rebuild helpers; scripts resilient to CWD
- [x] External LVFace integration (subprocess) and external caption integration with robust stderr/stdout handling
- [x] Warmup CLI (preload providers; tiny inference; timings) integrated into launchers
- [x] Windows multi‑pane launcher + WSL tmux launcher with presets (LowVRAM/RTX3090)
- [x] Voice proxy integration via LLMyTranslate: `/voice/*` endpoints (health, TTS, conversation, transcribe), env‑driven base URL/paths, proxy bypasses system proxies (trust_env=False)
- [x] Minimal server-rendered UI pages: `/ui`, `/ui/search`, `/ui/admin`, `/voice/demo` (TTS test)
- [x] Port standardization: API on 8002; Voice on 8001 (overridable)

---

## Next 2-week priorities (proposed)
1) UI gallery and admin improvements: basic search/gallery grid, simple filters, surface health/config on `/ui/admin`.
2) Caption profiles: Fast (vitgpt2), Balanced (blip2), Quality (qwen2.5-vl/llava-next). Wire to external inference.py; batch job + inline editor.
3) API polish: search pagination/filters and basic response envelope.
4) Observability: structured JSON logs; Prometheus metrics for caption/voice latency and provider/device labels.
5) Tests: UI route smoke tests; caption pipeline (vitgpt2 happy path), voice proxy health; ingest+video e2e.

## Quick wins (1–2 days)
- Add DB indexes for caption/tag search columns (and any slow query surfaces)
- CLI to backfill multiple caption variants across existing assets (respect user edits)
- Pre-commit hooks (ruff, black, isort, mypy) + Makefile targets
- Expose a /health/deps endpoint that asserts external dirs and model availability
- Docs: endpoint examples for captions/tags/smart search and video/segment search; UI usage notes and voice proxy env

