# Hardware Architecture

Version: Draft v0.1  
Date: 2025-08-11

## Objectives
Map software components to physical / logical hardware to ensure performance, scalability, and reliability targets (see PRD & nonfunctional.md).

## Deployment Tiers
| Tier | Use Case | Description |
|------|----------|-------------|
| T0 Minimal | Trial / <50k photos | Single CPU machine (no GPU), external USB or small NAS share. Slower captions & embeddings. |
| T1 Recommended | 50k–500k photos | Workstation + GPU (8–12GB VRAM), dedicated NAS (1 Gbps), SSD cache. |
| T2 Performance | 500k–2M photos | Workstation/Server w/ 24–32 CPU cores, 1–2 GPUs (24GB+ VRAM total), 10 Gbps LAN, NVMe scratch, RAID NAS. |
| T3 Advanced (Future) | >2M or multi-user | Separate nodes: ingest/index server, GPU inference server(s), Postgres + vector DB service. |

## Logical to Physical Mapping (T1/T2)
| Software Component | CPU | GPU | Disk I/O | Memory | Notes |
|--------------------|-----|-----|---------|--------|-------|
| Ingestion Scanner | Moderate (hash + EXIF) | None | High sequential / random read | 1–2 GB | Parallel threads (IO bound) |
| Hashing & Metadata | Low–Moderate | None | Shared with scanner | <1 GB | SHA256 streaming |
| Thumbnail Worker | Moderate (image decode) | Optional | Read original, write small files | <1 GB | Batch resize via Pillow/OpenCV |
| Embedding Worker (CLIP) | Low CPU driver | Yes (primary) | Read originals | Model + batch memory | VRAM 2–6 GB for batch (ViT-B) |
| Caption Worker (BLIP2) | Low CPU driver | Yes (heavy) | Read originals | Model weights + context | VRAM 8–12 GB advisable |
| Face Detection/Embed | Moderate | Yes (beneficial) | Read originals | 1–2 GB | Batch faces for throughput |
| Vector Index (FAISS) | Moderate (build) | Optional (GPU build future) | Read embeddings | Depends on vectors | 512d * N * 4 bytes (float32) |
| API / Search Service | Low–Moderate | Optional (query embedding) | Read indices | 1–2 GB | Can offload embedding to worker |
| Album Generator | Low | Optional | Read metadata | <1 GB | Scheduled job |
| Task Queue | Minimal | None | DB I/O | Negligible | SQLite or Postgres |

## Capacity Planning
### Storage Sizing Formula
Let:  
O = total originals size (input)  
T = thumbnail overhead fraction (~5–8%)  
E = embedding storage (vectors + metadata)  
C = captions & face JSON (<1%)

Embedding storage (float32) ≈ N * D * 4 bytes. For 512-d @ 1M assets:  
512 * 4 = 2048 bytes ≈ 2 KB/asset → ~2 GB.  
Additional modalities (faces avg 1.2 per image @ 512-d) → + ~2.4 GB.  
Total derived expected: (T * O) + (E) + (C) ≈ 10–15% O for Phase 4.

### Example (1M photos):
- Avg original size 2.5 MB → O ≈ 2.5 TB
- Thumbnails (two sizes) ~6% → 150 GB
- Embeddings (main + faces) ~4.5 GB
- Captions/JSON/misc <5 GB
- Indices & DB ~10 GB (FAISS + overhead)
- Total ≈ 2.67 TB (≈ +7%) excluding redundancy / snapshots.

## Performance Targets vs Hardware
| Target | T0 | T1 | T2 |
|--------|----|----|----|
| CLIP embed throughput (img/s) | 2–4 (CPU) | 25–40 (single mid GPU) | 60–120 (single high GPU) |
| Caption throughput (img/s) | 0.1–0.3 | 1–2 | 3–5 |
| Face embedding throughput (faces/s) | 3–6 | 40–70 | 90–150 |
| Ingestion hashing (files/min) | 800–1200 | 1500–2500 | 2500–4000 |
| Search latency p95 (K=200) | 400–800 ms | 200–400 ms | 120–250 ms |

## Network Architecture (T1/T2)
```
[User Workstation] --(1/10 Gbps LAN)-- [NAS]
     | (local process)
     |-- GPU (PCIe) for embeddings/captions
     |-- Local NVMe cache (/derived, /indices, DB)

Option: NAS exports originals only; derived artifacts kept local for speed with periodic sync.
```

## Storage Layout Strategy
- Originals on NAS: high-capacity RAID (ZFS / RAID6).  
- Derived & indices on local NVMe: low-latency random access.  
- Periodic rsync snapshot of derived & DB to NAS (or external drive).  

## I/O Characteristics
| Operation | Pattern | Optimization |
|-----------|--------|--------------|
| Ingestion Scan | Many small stat/open | Batch directory walks, ignore caches |
| Hashing | Sequential read full file | Increase read buffer (1–4 MB) |
| Thumbnail | Random read + small writes | Keep decode threads CPU pinned |
| Embedding | Random read + GPU batch | Pre-fetch queue, memory map |
| Search | Mostly in-memory index | Ensure index fits RAM / use IVF/HNSW |

## GPU Utilization Plan
- Single GPU scheduling: priority queue (embeddings > faces > captions) to balance latency & throughput.  
- Batch sizing heuristic: start high, reduce on OOM exception once.  
- Mixed precision (fp16) for BLIP2 & CLIP reduces VRAM footprint 30–40%.  

## Scaling Path (T2 → T3)
| Constraint | Symptom | Action |
|------------|---------|--------|
| GPU Saturation | Embedding queue backlog | Add 2nd GPU or offload captions to second host |
| CPU Saturation | High ingest latency | Separate ingest/index host |
| SQLite Lock Contention | Write stalls | Migrate to Postgres on dedicated container/VM |
| Memory for Vector Index | OOM/Swapping | Switch to HNSW (Qdrant) or IVF-PQ compression |

## Reliability & Redundancy
| Layer | Risk | Mitigation |
|-------|------|-----------|
| NAS | Disk failure | RAID + SMART monitoring |
| NVMe Cache | Drive wear | Derived artifacts reproducible; monitor TBW |
| Power | Outage | UPS for NAS + workstation |
| DB | Corruption | Daily snapshots + WAL archive (if Postgres) |
| Index | Corruption | Rebuild from embeddings directory |

## Backup Strategy
- Daily metadata.sqlite / indices snapshot tarball (rotating 7 days) stored on NAS.
- Weekly offsite (user-managed) copy if desired.
- Verification: periodic hash check of random originals vs stored SHA256.

## Security Surface
- LAN only; firewall blocks external inbound.
- Optional OS-level disk encryption (LUKS/FileVault) for derived store.
- GPU driver updates coordinated (avoid breaking CUDA stack).

## Environmental Considerations
| Component | Thermal Concern | Mitigation |
|-----------|-----------------|------------|
| GPU (caption loads) | Sustained high TDP | Adequate airflow, monitor temps |
| NAS drives | Continuous read bursts | Stagger scans, limit concurrency |
| NVMe | High random IO | Heat sink / active cooling |

## Monitoring (Hardware-Level)
- GPU: nvidia-smi sampling (utilization, memory, temperature)
- Disk: SMART stats & IO latency (iostat)
- Network: ifstat for throughput vs saturation
- CPU: per-core utilization (embedding vs ingestion separation)

## Future Enhancements
- Multi-GPU sharding by task type
- Remote inference microservice (gRPC) for heavy captioning
- On-the-fly vector compression (FP16 / INT8) to expand capacity
- Tiered storage for cold originals (spinning disks) vs hot set (SSD cache)

## Quick Reference Sizing (Rule of Thumb)
| Scale | Recommended Hardware |
|-------|----------------------|
| 200k assets | 12C CPU, 48GB RAM (32 GB minimal), 1x 10–12GB GPU, 3TB originals + 500GB NVMe derived |
| 100k assets | 8C CPU, 32GB RAM (24 GB minimal), 1x 8GB GPU, 2TB originals + 250GB NVMe derived |
| 500k assets | 16C CPU, 64GB RAM (48 GB minimal), 1x 12–16GB GPU, 6TB originals + 1TB NVMe derived |
| 1M assets | 24C CPU, 64GB RAM (48 GB minimal), 1x 24GB GPU (or 2x 12–16GB), 12TB originals + 2TB NVMe derived |
| 2M assets | 32C CPU, 96–128GB RAM (64 GB minimal), 2x 24GB GPUs, 24TB originals + 4TB NVMe derived |

## Minimal vs Recommended Resources
| Scale | RAM Min | RAM Rec | GPU Min | GPU Rec | Notes |
|-------|---------|---------|---------|--------|-------|
| 200k | 24 GB | 32–48 GB | 8 GB | 10–12 GB | Serialize captions & embeddings |
| 500k | 32 GB | 48–64 GB | 10–12 GB | 12–16 GB | Keep BLIP2 unloaded idle |
| 1M | 48 GB | 64 GB | 16 GB | 24 GB | 24 GB speeds caption batches |
| 2M | 64 GB | 96–128 GB | 24 GB | 2× 16–24 GB | Parallel workers, future models |

## 200k Asset Scenario Notes
- SQLite longevity: safe; migration unnecessary.
- Single mid-range GPU (e.g., RTX 4070) covers embeddings + captions sequentially.
- Derived storage fits comfortably on single 1TB NVMe (leave 50% free for wear & growth).
- Weekly rather than daily rescans adequate.
- Optional: downclock GPU / power limit to reduce thermals (lower sustained load).
- Face clustering runtime small → can run immediately post-ingestion.

## Alignment with Software Docs
This hardware architecture directly reflects pipeline stages (see ingestion-pipeline.md, embedding-and-indexing.md) and capacity assumptions (nonfunctional.md). Scaling path aligns with roadmap phases (roadmap.md) unlocking higher parallelism and model tiers.

---
END
