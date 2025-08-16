# Non-Functional Requirements

| Aspect | Target | Notes |
|--------|--------|-------|
| Scale | 0.5–2M assets | Photos + short videos |
| Ingestion Throughput | ~1000 photos/min (baseline) | Parallel IO + batching |
| Search Latency | <500 ms (p95 warmed) | Vector + metadata hybrid |
| Caption Latency | <3 s on-demand | Async generation, cache results |
| Reliability | Resumable tasks | Idempotent hashing & embedding steps |
| Privacy | Local-only processing | No external API calls by default |
| Storage Efficiency | <30% overhead on originals | Thumbnails + embeddings separate path |
| Extensibility | Plug-in model adapters | Registry of model providers |
| Observability | Structured logs + counters | Minimal initial, extensible |

## Performance Strategy
- Batching: group embedding inference
- Caching: persist embeddings, thumbnails once
- Progressive refinement: fast model first, upgrade heavy captions later
- Parallelism: thread pool for IO, process/GPU parallel for models

## Reliability Strategy
- Task queue with retry & backoff
- Checkpoint ingestion state (last scan cursor per root)
- Hash-based idempotency keys

## Security & Privacy
- Sandboxed model execution (user machine only)
- Optional encryption at rest for metadata DB
- Access control (future multi-user): simple token / OS ACLs

## Maintainability
- Clear module boundaries: ingestion, derivation, index, api
- Pydantic schemas as shared contract

## Portability
- Linux first; Windows/macOS supported for dev
- Containerized deployment option (Docker Compose)

## Open Tight Constraints
- GPU memory unknown (tune batch sizes)
- Event segmentation thresholds TBD
