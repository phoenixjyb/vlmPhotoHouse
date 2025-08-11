# Roadmap

## Phase 0: Foundations  **[DONE]**
- Repo scaffold, docs, minimal FastAPI (/health)  ✅ Implemented (FastAPI app, /health, basic logging)

## Phase 1: Core Ingestion & Metadata  **[PARTIAL]**
- Implement hashing + EXIF extraction  ✅ (hashing + EXIF in pipeline)
- SQLite schema & migrations  ✅ (Alembic set up; multiple revisions)
- CLI ingest command  ⏳ (ingest API exists; CLI minimal or pending expansion)
- Dedup logic  ✅ (sha256 + perceptual hash + near-duplicate clustering endpoint)

## Phase 2: Thumbnails & Embeddings (Search v1)  **[PARTIAL]**
- Thumbnail generator  ✅ (thumb task implemented)
- Embedding service (image/text)  ✅ Real model support (CLIP via open_clip / sentence-transformers) with stub fallback
- Embedding version + device tracking  ✅ (model, dim, device, optional version stored)
- Re-embed scheduling on model change  ✅ (startup detection & task enqueue)
- Vector search endpoint  ✅ (text or image-based)
- Persistent vector index (FAISS Flat IP)  ✅ (memory or faiss backend selectable)
- Approximate / optimized ANN (HNSW / IVF)  ❌ Not started

## Phase 3: Captions & Hybrid Search  **[EARLY PARTIAL]**
- BLIP2 caption generation  ⚠️ Stub heuristic captions in place
- Text embedding index  ⏳ Not yet separate (text uses same stub service)
- Hybrid ranking weights config  ❌ Not started

## Phase 4: Faces & Person Albums  **[PARTIAL]**
- Face detection  ⚠️ Stub (random boxes)
- Face embeddings  ⚠️ Stub (random vectors) — real model pending
- Clustering (incremental + full recluster w/ progress + cancel)  ✅ Implemented
- Labeling & merge/split workflow  ❌ Not started
- Person-based search / filtering  ⏳ Partial (entities exist, no dedicated endpoint)

## Phase 5: Events & Themes  **[NOT STARTED]**
- Event segmentation  ❌
- Theme clustering & labeling  ❌
- Smart album DSL  ❌

## Phase 6: Voice & Advanced UX  **[NOT STARTED]**
- Whisper integration for voice annotations  ❌
- Album summarization  ❌
- Query suggestions & relevance feedback  ❌

## Phase 7: Optimization & Hardening  **[NOT STARTED]**
- GPU scheduling & batching improvements  ❌
- Postgres migration option  ❌ (design consideration only)
- Backup & restore tooling  ❌

## Phase 8: Extended Media & Analytics  **[NOT STARTED]**
- Short video keyframe support  ❌
- Usage analytics dashboards  ❌

---

### Cross-Cutting (Updated)
- Observability & Metrics: ✅ /health, /metrics, /embedding/backend, average task duration computed. ❌ Prometheus exporter exposition format, per-task-type histograms, index autosave stats.
- Task Queue: ✅ Progress & cancellation for recluster, started_at/finished_at timing, configurable max retries. ❌ Multi-worker concurrency, categorized error codes, exponential backoff, dead-letter queue.
- Vector Index Strategy: ✅ FAISS flat persistent. ❌ ANN (HNSW/IVF), delta updates, autosave thread, per-face/person indexes.
- Model Realization: ✅ Image/Text embeddings real. ⚠️ Captions & face embeddings still stub. ❌ OCR, event/theme models.
- Data Store: ⚠️ SQLite baseline. ❌ Postgres option, backup/export tooling, integrity reconciliation.
- Security / Auth: ❌ No auth, no RBAC, no auditing.
- Governance & Compliance: ❌ PII purge / face/person deletion workflows.
- Developer Experience: ⚠️ Basic tests. ❌ Coverage for clustering/index, CLI task ops, performance benchmarks.
- Scalability: ❌ GPU batching, resource limits, sharded re-embed orchestration.
 - API & Schema Consistency: ⚠️ Mixed envelope styles. ❌ Unified {api_version,data,meta,error} wrapper, standardized error codes.
 - Reliability & Resilience: ❌ Dead-letter queue, requeue endpoint, rate limiting / batching heavy tasks.
 - Real-Time UX Hooks: ❌ Websocket/SSE for task progress, live clustering updates.
 - Validation & Safety: ⚠️ Basic path handling. ❌ Ingest path/mime/size validation hardening, face/person deletion safety checks.
 - Performance Engineering: ❌ Memory-mapped embeddings, batched clustering DB writes.

### Newly Identified Gaps (Big Picture)
1. Real face embedding model integration (InsightFace / Facenet) & quality filtering.
2. Postgres migration path + dual-run verification.
3. Prometheus /metrics.prom endpoint (task durations, failures, index stats).
4. Multi-worker executor (configurable concurrency + graceful shutdown).
5. Person management API (merge, split, rename) & audit history.
6. ANN index upgrade (HNSW or IVF/HNSW) with background build + swap.
7. Tag/label system (manual + auto concept extraction) enabling filtered vector search.
8. Bulk re-embed orchestrator (checkpointing, resumable, rate-limited).
9. Backup/export (DB + derived metadata manifest) & restore.
10. Auth layer (API tokens / future multi-user roles).
11. Dead-letter queue & manual requeue workflows.
12. Websocket/SSE progress streaming channel.
13. Unified response envelope & error taxonomy.
14. Input validation hardening (ingest path, MIME, size, EXIF trust boundaries).
15. Rate limiting / task throttling for heavy GPU ops.

### Near-Term Focus (Rolling Plan)
Current Track: Option A (Foundation Hardening) selected.

Sprint (Current):
1. Prometheus exporter endpoint (/metrics.prom) exposing:
	- Counters: tasks_total_processed, tasks_failed, tasks_retried, embeddings_generated
	- Gauges: tasks_pending, tasks_running, vector_index_size, persons_total
	- Histograms/Summaries: task_duration_seconds (by task_type)
2. Multi-worker support:
	- Spin up N worker threads (WORKER_CONCURRENCY) with DB row-level locking (SELECT ... FOR UPDATE / state transition guard) and cooperative shutdown.
3. Retry/backoff policy:
	- Exponential w/ jitter; classify errors (transient vs permanent) for earlier dead-lettering.
4. Dead-letter queue (state = 'dead') + admin requeue endpoint.

Next Sprint:
5. Face embedding real model integration (replace random vectors) + store model metadata.
6. Person management minimal API (rename, merge, split) + audit log stub.
7. ANN index prototype (HNSW or IVF build in background) behind feature flag.
8. Postgres migration spike: run dual-write or offline export/import tool (decide path, produce design doc snippet).

Following Sprint (Preview):
9. Websocket/SSE progress streaming for long tasks.
10. Unified API envelope + standardized error codes.
11. Input validation hardening (paths, mime, size limits) & rate limiting for heavy operations.

Selection Rationale:
- Improves observability before scaling (reduces blind spots for later performance work).
- Lays groundwork (multi-worker, metrics) required to validate Postgres or ANN performance improvements.

Option Switch Gate:
- After current sprint: evaluate readiness & data volume; if > X assets (configure threshold), prioritize Postgres track earlier.

Success Metrics (for current sprint):
- p95 task duration queryable via Prometheus.
- Can process tasks concurrently without duplicate execution (verified in test).
- Failed task moves to dead-letter after max retries with cause recorded.
- Requeue endpoint returns task to pending and clears retry_count.

Risk / Impact Matrix (Abbrev):
| Item | Impact | Effort | Risk | Notes |
|------|--------|--------|------|-------|
| Prometheus exporter | High | Low | Low | Straightforward instrumentation |
| Multi-worker | High | Med | Med | Need safe locking & idempotency |
| Backoff + DLQ | Med | Med | Low | Schema stable; logic isolated |
| Face embeddings real model | High | Med | Med | Model selection & perf constraints |
| ANN index | High | High | Med | Memory vs recall trade-offs |
| Postgres migration | High | High | High | Data export, migration, integrity checks |

Execution Order justifies quick wins (exporter) before concurrency complexity.

### Legend
✅ Complete   ⚠️ Stub / placeholder   ⏳ In progress / partial   ❌ Not started

---
_Last updated: automated assistant refresh integrating embedding backend, FAISS persistence, progress/cancel tasks._

> Note: Former temporary file `backend/docs/ROADMAP_TEMP.md` has been superseded; its unique items are merged above (dead-letter queue, unified envelope, SSE/websocket progress, validation hardening, rate limiting, memory mapping).
