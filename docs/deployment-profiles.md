# Deployment Profiles & Software-to-Hardware Mapping

Version: v0.1  
Date: 2025-08-11

## 1. Overview
This document maps logical software components to physical hardware across scaling tiers, describing placement, transition triggers, and failure domains.

## 2. Profiles
| Profile | Scale Range | Description | Key Tech Choices |
|---------|-------------|-------------|------------------|
| P1 Single-Node Minimal | ≤200k assets | Everything on workstation (SQLite, FAISS, GPU) | 8–12GB GPU, 24–32GB RAM |
| P2 Single-Node Enhanced | 200k–1M | Workstation with larger GPU + NVMe; NAS only originals | 16–24GB GPU, 48–64GB RAM |
| P3 Split Services | ~1M high usage | Workstation (API + GPU workers) + Postgres + optional Qdrant container | 24GB GPU + Postgres |
| P4 Distributed (Future) | >1M multi-user | Separate inference host(s), dedicated DB/vector node | 2× GPUs, Postgres, Qdrant |

## 3. Component Placement Matrix
| Component | P1 | P2 | P3 | P4 | Notes |
|-----------|----|----|----|----|-------|
| API / Search | Workstation | Workstation | Workstation | App Node | Keep near vector index for locality |
| Ingestion Scanner | Workstation | Workstation | Workstation | Ingest Node | Reads originals over LAN |
| Task Queue (SQLite) | Workstation | Workstation | Postgres | Postgres | Migrate when concurrency rises |
| Metadata DB | SQLite (file) | SQLite | Postgres (container) | Postgres Cluster | WAL backups after migration |
| Vector Index | FAISS local | FAISS local | Qdrant (optional) | Qdrant dedicated | Switch for scaling / HNSW features |
| Model Weights | Local NVMe | Local NVMe | Local NVMe | Inference Node(s) | Sync script if multiple nodes |
| Embedding Worker | Workstation GPU | Workstation GPU | Workstation GPU | Inference Node(s) | Offload when saturated |
| Caption Worker | Workstation GPU | Workstation GPU | Workstation GPU | Inference Node(s) | Highest VRAM demand |
| Face Worker | Workstation GPU | Workstation GPU | Workstation GPU | Inference Node(s) | Shares GPU scheduling |
| Thumbnail Worker | Workstation CPU | Workstation CPU | Workstation CPU | Ingest Node | Light CPU bound |
| Album Generator | Workstation | Workstation | Workstation | App Node | Low demand |
| Backup / Snapshot | Workstation+NAS | Workstation+NAS | App+NAS | Central Backup Node | Derived regenerated if lost |
| Monitoring Agent | Workstation | Workstation+NAS SMART | Workstation+DB | All nodes | Prometheus later |

## 4. Data Flow by Profile (Conceptual)
- Originals always sourced from NAS (except P1 if originals local disk).
- Derived artifacts stored on fast local NVMe (P1–P3) with periodic rsync snapshot to NAS.
- Metadata & indices co-locate with API until Postgres/Qdrant migration in P3.

## 5. Transition Triggers
| Trigger | Condition | Action |
|---------|-----------|--------|
| DB Contention | Write latency p95 >50 ms | Move to Postgres (P2→P3) |
| GPU Saturation | Queue backlog >24h | Add inference node / 2nd GPU (P2→P3/P4) |
| Index Memory Pressure | FAISS >50% RAM target | Migrate to Qdrant (P2→P3) |
| Availability Requirement | Need maintenance without downtime | Split API & workers (P2→P3) |
| Multi-User Access | >3 active users | Dedicated DB & separate worker node (P3→P4) |

## 6. Remote GPU Option (P3/P4)
- gRPC / HTTP microservice endpoints: /embed, /caption, /faces
- Batch scheduler prioritizes embeddings > faces > captions
- Heartbeat + auto drain before shutdown
- Model warm pool: preload CLIP; lazy load BLIP2

## 7. Security Boundary
| Layer | Principle |
|-------|-----------|
| NAS | Export read-only to non-root where possible |
| DB | Bind to LAN, firewall external |
| Vector Service | Local network only |
| API | No external Internet egress unless explicitly enabled |
| Model Sync | Checksum verify weights |

## 8. Failure Domains & Mitigations
| Failure | Impact | Mitigation |
|---------|--------|------------|
| Workstation NVMe loss | Derived/index lost | Rebuild from originals; snapshots |
| NAS pool degraded | Originals at risk | RAIDZ2 / RAID6 + SMART alerts |
| GPU driver crash | Stalled tasks | Supervisor restarts worker process |
| Postgres corruption | Metadata loss | Daily dumps + WAL archive (P3+) |
| Qdrant index corruption | Search degraded | Rebuild from embeddings store |
| Power outage | In-flight tasks lost | UPS + idempotent task design |

## 9. Backup Strategy by Profile
| Profile | Metadata | Embeddings | Thumbnails | Vector Index | Originals |
|---------|----------|------------|------------|--------------|----------|
| P1/P2 | SQLite file copy daily | Repro (optional tar) | Repro | Rebuild | Primary (NAS or local) |
| P3 | Nightly pg_dump + weekly full | Optional | Optional | Rebuild/Qdrant export | NAS |
| P4 | Automated snapshots + PITR | Tiered | Tiered | Export & replicate | NAS + offsite |

## 10. Monitoring & Observability Roadmap
| Stage | Metrics | Tool |
|-------|---------|------|
| P1 | ingestion_rate, queue_depth (log only) | Stdout logs |
| P2 | +gpu_util, search_latency p95 | Simple script / JSON endpoint |
| P3 | +db_qps, index_add_latency | Prometheus + exporters |
| P4 | +multi-node health, replication lag | Central Prometheus + Alertmanager |

## 11. Configuration Strategy
| Aspect | Approach |
|--------|----------|
| Base Config | .env + defaults module |
| Secrets | Local environment only (no secret manager needed P1–P2) |
| Profile Flag | DEPLOY_PROFILE=P1/P2/P3/P4 influences component startup |

## 12. Deployment Modes
| Mode | Invocation | Use Case |
|------|-----------|----------|
| api-only | start API + inline worker loop | Simple dev / P1 |
| worker-only | start workers from same codebase | P3 multi-process |
| migrations | one-shot schema upgrade | Pre-release change |

## 13. Example ENV Profiles
P1 (Single):
```
DEPLOY_PROFILE=P1
DATABASE_URL=sqlite:///./metadata.sqlite
VECTOR_BACKEND=faiss
ORIGINALS_PATH=/mnt/photos
DERIVED_PATH=./derived
```

P3 (Split + Postgres + Qdrant):
```
DEPLOY_PROFILE=P3
DATABASE_URL=postgresql+psycopg://user:pass@db:5432/photo
VECTOR_BACKEND=qdrant
QDRANT_URL=http://qdrant:6333
ORIGINALS_PATH=/nas/photos
DERIVED_PATH=/nvme/derived
```

## 14. Upgrade Path Summary
P1 → P2: Hardware upgrade (GPU/RAM/NVMe), same topology.
P2 → P3: Introduce Postgres (migrate), optional Qdrant, split workers.
P3 → P4: Add inference node(s), load balancer (future), replication.

## 15. Open Questions
- Do we need a lightweight agent on NAS for integrity scans?
- Will remote GPU introduce unacceptable latency without local JPEG decode pipeline?
- Vector encryption at rest needed beyond filesystem layer?

## 16. Next Steps
- Implement DEPLOY_PROFILE handling in codebase.
- Add simple component registry enabling conditional startup.
- Add migration script (SQLite → Postgres) planning doc.

---
END
