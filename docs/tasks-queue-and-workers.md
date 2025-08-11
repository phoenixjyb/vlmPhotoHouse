# Task Queue & Workers

## Goals
- Decouple heavy work (embeddings, captions) from ingestion
- Provide retry + backoff
- Enable scaling workers independently

## Minimal Implementation (Phase 1)
- tasks table in SQLite (id, type, payload_json, state[pending,running,done,failed], priority, retry_count, scheduled_at, updated_at)
- Polling loop inside API process every N seconds
- Row-level UPDATE with state transition guarded by `WHERE state='pending'`

## State Transitions
pending -> running -> done
pending -> running -> failed (retry_count++) -> pending (if retry_count < max)
failed (terminal)

## Backoff
- scheduled_at updated to now + backoff_delay(retry_count)

## Idempotency
- Use deterministic task payload hash as unique key for tasks that must not duplicate (e.g., embed same asset+model)

## Future Enhancements
- Separate worker service
- Priority queues (weight by task type)
- Dead letter queue table
- Metrics: tasks_running, tasks_failed, avg_latency

## Concurrency Control
- Limit concurrent embedding tasks to available GPU memory budget
