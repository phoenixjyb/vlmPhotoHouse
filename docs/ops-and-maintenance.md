# Operations & Maintenance

## Routine Jobs
- Nightly scan for new files
- Rebuild vector index weekly (optional)
- Orphan cleanup monthly
- Backup metadata & indices snapshot

## Commands (Planned CLI)
- ingest (scan roots)
- reindex (asset | all)
- rebuild-vector-index
- list-tasks --state pending|failed
- repair (consistency checks)

## Monitoring
- Metrics: ingestion_rate, queue_depth, embedding_latency, search_latency
- Health endpoints: /health (basic), /metrics (Prometheus future)

## Recovery
- If vector index corrupt → rebuild from embeddings directory
- If DB lost → restore snapshot + re-scan to reconcile missing

## Upgrades
- Migrations: schema version table
- Embedding model upgrade procedure documented in `embedding-and-indexing.md`
