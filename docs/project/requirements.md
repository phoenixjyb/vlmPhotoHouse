# Functional Requirements

## Core Ingestion
- Recursive filesystem / NAS scan (configurable roots)
- File filtering (extensions, size limits)
- Hashing: cryptographic (SHA256) + perceptual (pHash or dHash placeholder)
- EXIF & metadata extraction (timestamp, camera, lens, GPS, orientation)
- Idempotent re-scan (skip unchanged via mtime + size + hash cache)
- De-duplication (exact hash), near-duplicate clustering (future)
- Queue derived work (thumbnails, embeddings) asynchronously

## Derived Artifacts
- Multi-size thumbnails (e.g. 256, 1024) on-demand or batch
- Embeddings (CLIP image + optional text) persisted with model versioning
- Captions (BLIP2 or similar) lazy-generated, cached
- Face detections + embeddings with bounding boxes

## Indexing & Search
- Vector index for image embeddings
- Optional text embedding index (captions/tags) for cross-modal
- Metadata index (DB) for structured filters (date range, camera, person)
- Hybrid ranking (weighted sum) configuration
- Full-text search over captions & user annotations

## Albums & Organization
- Person albums (few-shot seeding, clustering, user validation loop)
- Time albums (calendar hierarchy: year → month → day)
- Event albums (time+location gap segmentation)
- Theme / semantic albums (unsupervised clustering of embeddings)
- Manual / rule-based smart albums (query templates)

## Annotation & Interaction
- Auto caption generation & summarization
- Voice input (speech-to-text) for annotations & search (future)
- User tag corrections propagate to model feedback dataset
- Exclude / hide assets (soft-delete flag)

## Administration & Ops
- Re-index commands (per asset, batch, full rebuild)
- Model upgrade migration path (versioned embeddings)
- Backup/export metadata and indices
- Health & metrics endpoints
- Config via env + override file + CLI flags

# Non-Functional Requirements (Summary)
See `nonfunctional.md` for detail.
