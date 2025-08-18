# Product Requirements Document (PRD)

Product: VLM Photo Engine  
Owner: Gareth  
Date: 2025-08-18  
Version: Draft v0.2

## 1. Executive Summary
A local-first AI photo engine that unifies a decade (0.5–2M) of personal photos from disparate storage into a single, semantically searchable, privacy-preserving library. It auto-generates captions, tags, person/time/event/theme albums without duplicating originals, enabling fast retrieval and rich organization while running entirely on user-owned hardware.

## 2. Goals & Non-Goals
### 2.1 Goals (Phase 1–4 focus)
- Consolidate and normalize photo metadata & structure
- Provide fast semantic + structured search (<500 ms p95)
- Automate de-duplication & avoid storage bloat
- Generate meaningful captions & tags locally
- Enable person/time/event/theme albums with minimal manual labeling
- Maintain strict local privacy (no cloud dependency by default)
- Design modular pipeline enabling incremental model upgrades

### 2.2 Non-Goals (Initial Phases)
- Cloud sync or multi-user collaboration
- Full video analysis beyond keyframe extraction (future)
- Advanced UI/UX polish or mobile clients
- Real-time ingestion watchers (added later)
- Distributed clustering across multiple hosts

## 3. Target Users & Personas
| Persona | Description | Key Needs |
|---------|-------------|-----------|
| Memory Curator | Individual organizing a decade of family photos | Reliable person/event albums, easy search |
| Power Photographer | Enthusiast with large RAW/JPEG collection | Fast ingestion, metadata fidelity, dedup |
| Privacy Advocate | User avoiding cloud photo platforms | Local-only processing, transparency |
| Tinkerer / Dev | Interested in extending system | Clear modular architecture, documented APIs |

## 4. Use Cases
1. "Show all beach photos with Alice in 2019" (person + tag + date filter)
2. "Find the trip where we visited Kyoto" (semantic + location inference)
3. "List all photos of Dad not yet confirmed" (face review workflow)
4. "Auto-create an album for last weekend's hiking event" (event segmentation)
5. "Search for 'red vintage car at night'" (semantic embedding retrieval)
6. "Add a manual tag and have it impact future theme clustering" (annotation feedback)
7. "Regenerate embeddings after upgrading model" (maintenance)

## 5. Scope (Initial Release vs Later)
| Feature | Phase | In Scope Now | Notes |
|---------|-------|--------------|-------|
| Ingestion (scan + EXIF + hash) | 1 | Yes | CLI + API trigger |
| Dedup (exact hash) | 1 | Yes | Perceptual near-dup future |
| Thumbnail generation | 2 | Yes | Sizes configurable |
| Image embeddings (CLIP) | 2 | Yes | ViT-B/32 initial |
| Vector search | 2 | Yes | FAISS flat |
| Caption generation (BLIP2) | 3 | Yes | Async, cached |
| Hybrid text+image search | 3 | Yes | Weighted scoring |
| Face detection & clustering | 4 | Yes | User validation loop |
| Person albums | 4 | Yes | Confidence thresholds |
| Event segmentation | 5 | Later | Gap-based heuristic |
| Theme clustering | 5 | Later | HDBSCAN/k-means |
| Voice annotations | 6 | Later | Whisper small |
| Album summarization | 6 | Later | LLM summarizer |
| Video keyframes | 8 | Later | Out of MVP |

## 6. Functional Requirements (Condensed)
(Full detail: `requirements.md`)
- Ingestion: recursive scan, metadata extraction, idempotent updates
- Hashing: SHA256 + perceptual placeholder
- Dedup: skip duplicate ingestion; track canonical asset
- Derived artifacts: thumbnails, embeddings, captions, face crops
- Search: semantic embedding retrieval + filters + hybrid rerank
- Albums: person/time/event/theme/manual queries
- Face workflow: detection → cluster → user label → refine
- Annotation: user edits override model; voice-to-text via external service (LLMyTranslate) proxied by API
- Task system: async jobs, retry, backoff, idempotency
- Configuration: env + optional file; introspection endpoint

## 7. Non-Functional Requirements
(Full detail: `nonfunctional.md`)
| Dimension | Requirement |
|-----------|------------|
| Scale | Up to 2M assets |
| Latency | Search <500 ms p95 (warm) |
| Throughput | ~1000 photos/min ingestion baseline |
| Privacy | No external network calls by default |
| Reliability | Resumable, idempotent pipelines |
| Storage Overhead | <30% above originals |
| Extensibility | Pluggable models & indices |

## 8. System Architecture Summary
Reference: `architecture.md`.
Core services: Ingestion Scanner, Task Queue, Derivation Workers (embeddings, thumbnails, captions, faces), Vector Index, Search API (with voice proxy), Album Generator.
State layers: Metadata DB (SQLite initially), Vector Index (FAISS), Derived FS store, Config/Settings.
Data flow: discover → extract → dedup → schedule tasks → derive artifacts → update indices → query/album materialization. Voice user flows use API `/voice/*` proxy to LLMyTranslate for STT/TTS.

## 9. Data Model Summary
Reference: `data-model.md`.
Core entities: Asset, Embedding, DerivedArtifact, Caption, FaceDetection, Person, Tag, AssetTag, Album, Task, Setting.
Versioned embeddings & captions support model upgrades without destructive overwrite.

## 10. User Flows
### 10.1 Initial Library Setup
1. User configures roots
2. Run ingest CLI → assets created, tasks scheduled
3. Workers populate thumbnails & embeddings
4. User performs first searches; optional caption batch kicks off

### 10.2 Searching
1. User issues text query
2. Text embedding generated (cached if repeat)
3. Vector similarity fetch (top K)
4. Apply filters & hybrid rerank
5. Paginated results returned

### 10.3 Person Labeling
1. Faces detected & clustered
2. Unlabeled clusters surfaced in UI
3. User assigns label → cascade update person_id
4. Person album auto-updates

## 11. Release Phasing & Milestones
See `roadmap.md`. Acceptance criteria per phase:
- Phase 1: Ingest + hash + EXIF + dedup; DB integrity; basic CLI metrics.
- Phase 2: Embeddings + search returning relevant images for simple queries.
- Phase 3: Captions generated for ≥90% of sampled assets; hybrid score improves MRR vs image-only baseline.
- Phase 4: ≥80% precision in top-1 person cluster assignments before user correction. Voice: STT/TTS smoke test via `/voice/demo` succeeds.

## 12. Success Metrics
| Metric | Target (Post Phase 4) |
|--------|-----------------------|
| Search p95 latency | <500 ms |
| Caption coverage | >95% of assets selected for captioning |
| Person tagging precision | >90% after user feedback loop |
| Dedup false negative rate | <1% on test sample |
| Embedding rebuild time (100k assets) | <2 hours on target HW |
| User correction rate (tags) | Declines over time (trend) |

## 13. Dependencies & Assumptions
| Category | Assumption |
|----------|-----------|
| Hardware | Single PC; GPU (>=8GB VRAM) improves performance, CPU-only path supported |
| Storage | Local internal/external storage (NVMe/SATA/USB); NAS optional, not required |
| Libraries | Stable availability of PyTorch & CLIP/BLIP2 weights locally |
| OS | Linux primary; Windows 11 (WSL2 + Docker Desktop) and macOS supported. Windows quick-start launcher available. |

## 13.1 Target Hardware Profile (Single PC)
- Form factor: One machine running the full stack (API, workers, vector index, DB)
- CPU/RAM: ≥8 cores, 64 GB RAM recommended (32 GB minimum) for smooth derivation and search
- GPU: Optional NVIDIA GPU (≥8 GB VRAM) accelerates embeddings/captions/faces; CPU fallback available
- Storage:
	- Originals: internal SSD/HDD or external drive; configured as read-mostly root path
	- Derived & DB: NVMe SSD preferred (separate path) to keep latency low
	- Backup: snapshot/mirror/cold backup strategy (local mirror + cloud optional)
- Deployment modes:
	- Linux bare-metal or Docker Compose
	- Windows 11 via WSL2 + Docker Desktop (GPU enabled)
	- macOS via Docker (GPU acceleration limited; CPU fallback)
- Networking: Localhost access by default; LAN share optional for ingestion only

### 13.1.1 Reference Mapping (Windows single PC)
- Drives and roles
	- C: Windows OS and applications
	- D: App data (derived artifacts, caches, optional DB backups)
	- E: NAS/Library (original photos and shared datasets)
	- F: WSL VM storage (VHDX) – does not change host mount paths, available under `/mnt/f`
- GPUs
	- GPU 0: Quadro P2000 for desktop/normal use and light ML tasks
	- GPU 1: RTX 3090 for LLM/VLM inference and light LoRA/fine-tuning
- WSL2/Docker mappings (examples)
	- PHOTOS_PATH → `/mnt/e/photos`
	- DERIVED_PATH → `/mnt/d/vlm/derived`
	- GPU selection via `NVIDIA_VISIBLE_DEVICES` (verify index with `nvidia-smi`)

## 14. Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Model memory footprint | OOM / slow | Tiered models, batch size autotune |
| Large initial embedding build time | Slow readiness | Progressive (on-demand) embedding, lazy captioning |
| Face clustering drift | Incorrect albums | Periodic recluster eval, user feedback gating |
| SQLite contention | Latency under load | Transition path to Postgres, write batching |
| Index corruption | Search downtime | Rebuild procedure from persisted embeddings |
| Privacy misconfig | Data leak | Default deny external calls, config audit tool |

## 15. Open Questions
See `open-questions.md` (kept live). PRD adopts defaults until resolved.

## 16. Out of Scope (Explicit)
- Cloud sync / sharing features
- Real-time collaborative editing
- Advanced editing (filters, transformations)
- Full ML model training (fine-tuning) pipeline

## 17. Appendices
- Detailed pipelines: `ingestion-pipeline.md`, `embedding-and-indexing.md`
- Albums logic: `albums-and-theming.md`
- AI components: `ai-components.md`
- Search scoring: `search-and-ranking.md`
- Storage layout: `storage-strategy.md`
- Face pipeline: `face-recognition.md`
- Task queue: `tasks-queue-and-workers.md`

## 18. Approval & Next Steps
- Review stakeholders: (list)
- Upon sign-off: lock v0.1 PRD in repo, begin Phase 1 implementation tasks (`backlog.md`).

---
CHANGE LOG
- v0.1 Initial draft derived from consolidated spec docs.
