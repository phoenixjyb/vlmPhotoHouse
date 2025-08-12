# Changelog

All notable changes are tracked here. Dates in UTC.

## [Unreleased]
- Dead-letter queue for tasks (state='dead')
- Admin requeue endpoint
- Face embedding real model integration
- Person management API (rename/merge/split)
- ANN index prototype (HNSW/IVF)
- Postgres migration spike

## [2025-08-12]
### Added
- Prometheus metrics exporter endpoint `/metrics.prom` with counters (`tasks_processed_total`, `tasks_retried_total`, `embeddings_generated_total`), gauges (queue size, running, vector index size, persons), histogram (`task_duration_seconds`).
- Multi-worker task executor with configurable `WORKER_CONCURRENCY`, optimistic task claiming, cooperative shutdown.
- Exponential retry with jitter backoff using `scheduled_at`, transient vs permanent error classification, `max_task_retries` enforcement.
- Test coverage for metrics exporter, multi-worker concurrency, and retry/backoff scheduling logic.
- Environment guidance and pinned dependency snapshot `backend/requirements-lock.txt`.
- Added `prometheus-client` dependency.
- Helper `reinit_executor_for_tests()` to refresh settings/executor in tests.

### Changed
- Roadmap updated to reflect implemented observability and concurrency features.
- Task executor now records `started_at` / `finished_at` for duration metrics.

### Fixed / Internal
- Optimistic update logic for task claiming to avoid duplicate execution under concurrency.
- Various test stabilization adjustments (reduced flakiness by relaxing strict timing assertions).

### Removed
- N/A

---

## Historical (Pre-2025-08-12)
Initial foundational phases: ingestion pipeline (hashing, EXIF), thumbnail & embedding tasks, vector index (in-memory / FAISS), caption stub, face/person clustering stubs, basic search and duplicate detection endpoints.

