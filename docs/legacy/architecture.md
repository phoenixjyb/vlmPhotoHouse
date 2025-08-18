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

## Addendum: Voice Proxy & Dev Topology (2025-08)
- Voice is provided by an external service (LLMyTranslate) running on `127.0.0.1:8001` by default.
- The API exposes thin proxy endpoints under `/voice/*` (health, transcribe, tts, conversation). These forward to LLMyTranslate using an env-configured base URL and path mapping and intentionally bypass system proxies.
- Benefits of the proxy: single-origin UI, consistent auth/timeout policy, and ability to swap providers later.
- Ports: API on `8002`; Voice on `8001` (overridable via launcher `-VoicePort`).
- Dev ergonomics: a Windows Terminal multi-pane launcher starts API, LVFace, Caption, and Voice panes; a Quick Start guide documents one-command startup.
