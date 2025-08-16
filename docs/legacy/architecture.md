# Architecture Overview

## High-Level Components
- Ingestion Scanner: walks directories, extracts metadata, schedules work
- Hashing & Metadata Extractor: computes hashes + EXIF, writes DB rows
- Task Queue: lightweight (initial: SQLite polling) for async jobs
- Derivation Workers: thumbnails, embeddings, captions, face detection
- Vector Index Service: abstraction over FAISS/Qdrant (pluggable)
- Search API (FastAPI): query parsing, hybrid ranking, album materialization
- Album Generator: periodic jobs for events/themes/person updates
- State Stores:
  - Metadata DB (initial: SQLite)
  - Vector Index (FAISS local files) / alt: Qdrant container
  - Derived Artifact Storage (filesystem hierarchy)
  - Config & Task Tables (in Metadata DB)

## Data Flow
1. Scan roots → discover new/changed files
2. Hash & metadata extraction → Asset row
3. Dedup check → skip or continue
4. Enqueue derivations (thumb, embed, caption, faces)
5. Workers process queue → write artifacts + embeddings
6. Index writer updates vector index
7. Search API queries indices + metadata for results
8. Album generator builds/refreshes dynamic album definitions

## Deployment (Initial)
- Single process (dev) or Docker Compose:
  - api (FastAPI + lightweight embedded services)
  - (future) worker container(s)
  - (optional) qdrant

## Scaling Path
- Split API vs workers
- Dedicated vector index service
- GPU-enabled worker pool
- Replace SQLite with Postgres when concurrency increases

## Filesystem Layout (Proposed)
```
/ originals/... (mirrors source relative paths or hashed buckets)
/ derived/
  thumbnails/{size}/{asset_id[0:2]}/{asset_id}.jpg
  embeddings/{model}/{asset_id}.npy
  faces/{asset_id}/{face_idx}.json
  captions/{asset_id}.json
```

## Configuration
Environment variables + optional `config.yaml` override.
