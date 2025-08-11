# Temporary High-Level Roadmap

## 1. Core correctness & robustness
- Alembic migrations for new SQLAlchemy 2.0 models
	- Added script.py.mako template (was missing) and generated revision 402a07259e4a enforcing NOT NULL on assets.status.
- Backfill / guard for existing DBs
- Transactional task execution & structured error logging

## 2. Task system hardening
- Progress tracking fields
- Cancellation support
- Rate limiting / batching heavy tasks
- Dead-letter queue & requeue endpoint

## 3. Embeddings & search quality
- Real image/text embedding model integration (flagged)
- Persist model version & auto index rebuild on change
- Vector search filters & pagination
- Optional approximate backend (faiss/hnswlib abstraction)

## 4. Face pipeline evolution
- Real detector & embedding model
- Unassigned faces endpoint
- Cluster merge suggestions (centroid distance)

## 5. Duplicate & near-duplicate refinement
- Hamming distance histogram endpoint
- Merge/variant actions
- Perceptual diff thumbnails

## 6. API & schema polish
- Unified envelope {api_version, data, meta}
- Error model standardization
- Docs & tags

## 7. Observability & ops
- Structured JSON logs (correlation id)
- Metrics: queue depth, throughput, clustering duration
- Health/readiness endpoints
- Prometheus exporter or JSON metrics

## 8. Performance & scalability
- Batch clustering DB writes
- Memory map embeddings
- Parallel workers & locking

## 9. Testing & quality
- Expand coverage (duplicates, vector search, merges)
- Property-based clustering tests
- Larger ingest integration test

## 10. Developer ergonomics
- Makefile / pre-commit hooks (ruff, mypy, black)
- Dev data seeding

## 11. Security & resilience
- Ingest path validation
- Image size/MIME validation
- Retry backoff & limits

## 12. Future UX hooks
- Websocket/SSE task progress
- Lightweight UI for persons/search/duplicates

---
This file is a temporary staging area; promote to primary docs when items start completing.
