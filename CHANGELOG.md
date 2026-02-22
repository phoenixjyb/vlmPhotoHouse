# Changelog

All notable changes are tracked here. Dates in UTC.

## [2025-09-03] - Drive E Migration Complete

### 🏗️ Architecture
- **Complete Code/Data Separation**: Moved 35,369+ files from workspace to E:\VLM_DATA
- **Professional Data Organization**: Structured directories (databases/, embeddings/faces/, derived/, logs/, verification/, test_assets/)
- **Clean Workspace**: Repository now contains only code, configurations, and documentation

### 🧠 Face Embeddings Migration
- **11,528 Embedding Files**: Relocated from `embeddings/` to `E:\VLM_DATA\embeddings\faces\`
- **Preserved Accessibility**: All 512-dimensional face vectors remain accessible via Drive E helper
- **Service Integration**: Updated SCRFD service to save embeddings to Drive E location

### 💾 Database Consolidation
- **Database Migration**: Moved metadata.sqlite (26.71 MB), app.db (4.13 MB), drive_e_processing.db (0.04 MB) to E:\VLM_DATA\databases\
- **Configuration System**: Created `config/drive_e_paths.json` for centralized path management
- **Helper Infrastructure**: Added `tools/drive_e_helper.py` for easy data access

### 🔧 Infrastructure
- **Migration Scripts**: PowerShell and Python automation for safe data movement
- **Configuration Management**: JSON-based path resolution with validation
- **Documentation Suite**: Comprehensive migration reports and usage guides

### ✅ Validation
- **Migration Verification**: All 35,369+ files successfully moved with integrity checks
- **Service Updates**: All components operational with Drive E paths
- **Clean Architecture**: Workspace verification confirms only code remains

## [Unreleased]
- Dead-letter queue for tasks (state='dead')
- Admin requeue endpoint
- Face embedding real model integration
- Person management API (rename/merge/split)
- ANN index prototype (HNSW/IVF)
- Postgres migration spike
# Changelog

## [2025-08-12]
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

