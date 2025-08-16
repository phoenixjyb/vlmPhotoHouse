# Scaling Assumptions (1M Assets Target)

Version: v0.1  
Date: 2025-08-11

## Dataset Composition
- Max assets: 1,000,000 (images + some short videos)
- Mix: ~95% still images, 5% short videos (videos keyframed later)
- Formats: JPEG 70%, HEIC 15%, RAW 10%, PNG/Other 5%
- Avg photo size: 2.5 MB (range 0.8–12 MB)
- RAW avg size: 28 MB
- Resolution distribution: 60% (12–24 MP), 30% (24–45 MP), 10% (>45 MP)

## Derivative Artifact Ratios
- Thumbnails (256 & 1024): ~6% of originals size
- Image embeddings (512-d, CLIP): ~2 GB @1M
- Face embeddings (avg 1.2 faces/img across total set): ~2.4 GB
- Captions + JSON + misc: <0.3% of originals
- Vector index overhead (FAISS/HNSW): up to ~2× raw vectors (≤10 GB target)

## Ingestion & Growth
- Initial backlog ingested once; steady growth 2–5k photos/month
- Initial full hashing + metadata target: ≤48h continuous run
- Daily incremental rescan touches <2% of files

## Operational Throughput Targets (Recommended HW)
| Pipeline | Throughput | Notes |
|----------|-----------|-------|
| Hash + EXIF | 2500–3000 files/min | IO bound, multithreaded |
| Image embeddings (CLIP ViT-B/32) | 80–110 img/s | 24 GB GPU, FP16, batch≈128 |
| Captioning (BLIP2 small) | 3–5 img/s | Async, batch≈8 |
| Face detection | 50–70 img/s | Mixed CPU/GPU |
| Face embeddings (ArcFace) | 120 faces/s | Batched |

## Access & Query Patterns
- Single primary interactive user
- Concurrency: ≤5 heavy background tasks plus user queries
- Search latency goal: p95 <500 ms (K=200)
- Query repetition (cacheable): 20–30%

## Index Design Assumptions
- Start: Flat or HNSW (M=32, ef=128)
- Rebuild time for 1M: <2h
- Compression (PQ/FP16) deferred until memory pressure (>16 GB footprint)

## Face / Person Modeling
- Faces in 55% of images
- Avg faces per face-bearing image: 2.2
- Effective labeled persons: 30–80
- Re-cluster cadence: weekly or +50k new images

## GPU & Models
- Single high-end GPU (24 GB) resident models: CLIP, BLIP2, ArcFace
- Mixed precision acceptable (no FP32-only constraints)
- Sequential heavy model usage (avoid simultaneous large VRAM spikes)

## Reliability & Failure Tolerance
- Task retry rate <0.5%
- Power protected by UPS; graceful shutdown expected
- Derived artifacts reproducible; only originals + DB + index metadata backed up

## Storage & IO
- Originals on NAS: sustained read ≥800 MB/s aggregate (10 GbE)
- Derived + indices on local NVMe (random read <100 µs)
- Daily snapshot window: <10 min (metadata + indices)
- Space buffer: ≥30% free NAS capacity post-ingestion

## Security & Privacy
- No external network calls by default (models local)
- Encryption optional; not assumed for performance baselines

## Capacity Headroom
- GPU VRAM: 25% reserved headroom (no oversubscription planned)
- CPU cores: 20% free for OS & future services
- RAM: 48–64 GB sufficient for 1M sequential workloads (prior 128 GB was comfort upper bound). Larger (96–128 GB) only if parallel heavy models or multi-user.

## Process Scheduling
- Caption tasks throttled to keep GPU util <85% when user active
- Night idle window used for batch captions & reclustering

## Key Risks Embedded in Assumptions
| Risk | If Assumption Breaks | Adjustment |
|------|----------------------|-----------|
| Higher RAW % | Larger throughput & storage hit | Add NVMe, increase ingestion window |
| More videos | Extra keyframe processing time | Introduce video worker & GPU scheduling |
| Multiple users | API contention | Move DB to Postgres, add worker separation |
| Lower GPU VRAM | Reduced batch sizes | Increase embedding wall-clock time |

## Revision Triggers
- Dedup false negatives >1% → add perceptual hash tuning
- Embedding backlog >24h → add 2nd GPU or remote inference node
- DB write latency p95 >50 ms → migrate to Postgres
- Vector index >12 GB RAM → enable compression / Qdrant

## Divergence Reporting
If real environment differs (RAW %, growth, users, GPU spec), document delta and update sizing multipliers.

---
End of assumptions v0.1

---

# Scaling Profile (200k Assets Scenario)

## Overview
Derived subset of 1M plan (20% scale) enabling lighter hardware & simplified architecture.

## Storage Estimates
- Originals (~200k * 2.5 MB avg): ~0.5 TB (headroom target ≥1 TB)
- Thumbnails (≈6%): ~30 GB
- Image embeddings (512-d): ~0.4 GB
- Face embeddings (~110k faces): ~0.5 GB
- Captions + JSON + indices + DB: <5 GB
- Total derived overhead: ~70–80 GB (<15% originals)

## Hardware Simplification
| Component | 200k Recommendation | Notes |
|-----------|---------------------|-------|
| GPU | 8–12 GB (RTX 4060 Ti / 4070) | 8 GB workable (smaller batches) |
| RAM | 32–64 GB | Vector index + caches <4 GB |
| NVMe | 1 × 1 TB | Derived + models + temp; 2nd NVMe optional |
| NAS | 2–3 TB usable | Leaves multi‑year growth margin |
| CPU | 8–12 cores | Plenty for ingestion + light workers |

## Performance (Targets)
| Pipeline | Throughput | Full-Set Duration |
|----------|-----------|-------------------|
| CLIP embeddings | 40–60 img/s | <1.5 h (if batch) |
| Captioning (BLIP2 small) | 2–3 img/s | 18–28 h (staged/idle) |
| Hash + EXIF | 2000–2500 files/min | 1.5–2 h core ingest |
| Face detection | 30–45 img/s | ~1–1.5 h |

## Architectural Choices
- Single process (API + task loop) acceptable long term.
- SQLite sufficient; low write contention probability.
- Flat FAISS index; rebuild in minutes (<15 min).
- No need for Qdrant/Postgres unless approaching 500k.

## Operational Cadence Adjustments
- Weekly rescan vs daily.
- On-demand face recluster or monthly.
- Captions generated progressively (night batches) first week.

## Deferred Components
- Second GPU, vector compression, remote inference.
- Advanced scheduling / multi-tenant isolation.

## Risk Reductions
- Lower VRAM usage reduces OOM likelihood.
- Lower IO & storage footprint simplifies backup.

## When to Reassess (Upgrade Triggers)
- Asset count >350k → consider 64 GB RAM + larger NVMe.
- Caption backlog >72h → upgrade GPU or reduce batch caption scope.
- Search latency p95 >500 ms with >5 concurrent tasks → split worker process.

---

## Minimal vs Recommended Resource Matrix

| Scale | RAM Minimal | RAM Recommended | GPU Minimal | GPU Recommended | Notes |
|-------|-------------|----------------|-------------|-----------------|-------|
| 200k  | 24 GB | 32 GB | 8 GB (RTX 4060/3060) | 10–12 GB (4070) | All tasks serialized; captions slower on 8 GB |
| 500k  | 32 GB | 48 GB | 10–12 GB | 12–16 GB | Consider keeping BLIP2 unloaded when idle |
| 1M    | 48 GB | 64 GB | 16 GB | 24 GB (4090/6000 Ada) | 24 GB enables larger batches & faster captioning |
| 2M    | 64 GB | 96–128 GB | 24 GB | 2× 16–24 GB | Parallel workers or larger models |

### Memory Component Breakdown (Typical 1M Run)
| Component | Approx RAM | Notes |
|-----------|------------|-------|
| OS + Services | 2–4 GB | Base system |
| API + Python Overhead | 1–2 GB | FastAPI, libs |
| CLIP Model (fp16) | 0.6 GB | Resident |
| BLIP2 Small (fp16 active) | 8–10 GB | Loaded only during caption batch |
| Face Models | <0.5 GB | Combined |
| Vector Index (1M, 512d, float32 + overhead) | 3–4 GB | Flat/HNSW |
| Caches (thumbnails mmap, FS cache) | 4–8 GB | Elastic |
| Free / Headroom | 8–16 GB | For bursts, kernel cache |

### Memory Optimization Options
- Unload BLIP2 between batches (free 8–10 GB)
- Convert vectors to fp16 (≈50% reduction) if recall acceptable
- Use HNSW with M lower or PQ compression when index >5 GB
- Limit simultaneous embedding & caption tasks

---
End of assumptions v0.1 (updated with resource matrix)
