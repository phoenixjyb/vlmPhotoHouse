# Standalone caption worker

`scripts/run_caption_worker.py` separates caption queue execution from the HTTP
entry point. It is a **separate process and release**, not a protected WebUI
dependency. Do not add its ML-adjacent dependencies to the protected CPU runtime
or import it into `app.main`. It does not serve HTTP or start a model server.

## Boundaries

- Preflight is the default: explicit existing database, reviewed revision, existing
  derived/temp directories, separate stop path, loopback caption URL, and private
  reviewed environment JSON. It opens SQLite read-only and does not contact the
  model or create directories, a lock, schemas, or tasks.
- Execution additionally requires `--execute --legacy-worker-stopped`. That flag
  records an **operator assertion**, not automatic detection or service control.
  Independently stop/drain the old queue owner first. A currently running caption
  task causes refusal, not automatic recovery. Other running task types are not
  treated as caption owners; all writers still need draining for migration.
- A kernel-held lock next to the selected database excludes other instances of
  this launcher using that exact canonical path. It does not fence the legacy API,
  aliases/hard links, or arbitrary database writers. Never remove its lock file;
  process exit releases the lock, and file existence is not a liveness indicator.
- The executor receives explicit dependencies and `caption_only=True`. It claims
  only due, pending captions with the existing guarded claim/retry/commit behavior.
  It does not initialize embedding models/indexes, claim other task types, or
  enqueue idle dimension backfills. Default mixed-executor behavior is preserved.
- Startup requires a healthy provider identifying as Qwen3 HTTP before claiming a
  task. Inference uses the existing external loopback service. Stub fallback and
  automatic caption-derived tagging are disabled for this migration worker.
  Original media reads, video frame extraction and normal caption database writes
  still occur when real jobs run; this is not a read-only production worker.
- The process ignores repository `.env` via `PHOTOHOUSE_NO_DOTENV=1` and removes
  inherited caption/retry settings. Only the explicit JSON allows overrides. It
  sets no word cap by default, disables local CUDA visibility and limits its own
  numeric-library threads to one; it does not tune the external GPU service.

## Command shape

Use the qualified **repo-root worker environment**, not `backend/.venv` or the
protected WebUI environment. All paths/configuration below are placeholders:

```text
python -I scripts/run_caption_worker.py
  --database ABS_EXISTING_DATABASE --expected-revision c7f4a9e2b610
  --derived ABS_EXISTING_DERIVED_DIR --temporary ABS_EXISTING_PRIVATE_TEMP_DIR
  --stop-file ABS_PRIVATE_STOP_REQUEST
  --caption-url http://127.0.0.1:REVIEWED_PORT
  --environment-json ABS_PRIVATE_REVIEWED_JSON
```

The only qualified revisions are the pre-access `d2b7e4f6a901` and migrated
`c7f4a9e2b610`; the actual file must match the selected revision exactly. No schema
creation or migration is attempted. The execution connection uses SQLite `mode=rw`
so a missing file cannot silently become a new catalog.

Only after separate authorization and shutdown verification, add
`--execute --legacy-worker-stopped`; `--once` limits the run to one claim attempt,
including an idle attempt. It does not select a particular asset or retry failed
jobs. A processed claim can finish, retry or fail under existing policy; the
reported count is **not** a count of successful captions.

JSON is an object of string values. Allowed keys are listed in the launcher's
`NUMBERS` and `TEXT` constants: caption prompt/profile/infant-care exceptions,
word/variant/policy retry limits, HTTP retry/delay/timeout/image-edge settings, and
queue retry/backoff settings. Unknown keys, duplicate keys, non-finite numbers and
out-of-range numbers are refused. No passwords or API tokens belong in this file.
Omitted values retain the source handler defaults except word count (zero).
Before rollout, compare the complete private JSON with the current live worker's
effective settings so exception lists, resize settings and retry budgets survive.

## Graceful stop and recovery

Create the explicitly configured stop-request file, or deliver a supported
SIGINT/SIGTERM (Windows console SIGBREAK is also handled). The worker finishes its
current synchronous handler and database transition, makes no next loop claim,
releases its lock, and exits with a small drained result. Idle stop-file detection
is within the one-second poll interval. The stop file is retained and prevents a
later start until an operator deliberately clears that request.

There is no forced drain timeout: caption HTTP/policy retries and video extraction
can take time. A supervisor must allow the reviewed worst-case handler duration.
Windows scheduled-task force-stop, process termination, machine sleep or power
loss are **not** graceful stop requests. An interrupted running task requires a
separate inspection/recovery decision; this launcher never resets/requeues it.
Unhandled startup/database errors return nonzero with no clean-drain claim.
Do not sleep or migrate solely because a stop request was issued: verify process
exit and the queue boundary, then account for every other writer.

## Qualification and remaining gates

`tests/security/test_caption_worker.py` checks read-only preflight, path/revision/
configuration refusal, lock exclusion/release, and drain behavior. With legacy
test dependencies installed, it also runs six isolated processes against a real
synthetic migrated SQLite database: caption commit + stop, user-edit preservation,
retry, idle, unavailable provider, and missing shutdown confirmation. Future tasks
and unrelated high-priority work stay pending. Embedding/index initialization,
idle backfill, network/process I/O and API imports are guarded. Minimal protected
test environments skip only that legacy-dependency integration test.

On 2026-09-15, all 17 focused tests passed on Mac and native Windows CPython 3.12
(17.4 seconds on Windows), including the six fresh-process handler scenarios and
default mixed-executor claim regression. The first native package lacked the
checked-in prompt file; after including it, the native runs passed. Source hashes
and test receipts are retained privately. No live database or model was used.

The source qualification is not live deployment or GPU acceptance. Before rollout:

1. Build and hash a separate worker candidate, including its caption prompt file,
   actual reviewed dependencies, and all installed caption input-resize changes.
   Do not overwrite the dirty recovered overlay with clean older source. The
   protected WebUI package allowlist intentionally excludes this worker.
2. Verify the installed resize policy and private effective settings in that
   candidate; perform native one-job inference and stop/drain acceptance under an
   approved window. Fixture providers do not prove image/video inference.
3. Qualify service-principal media/temp access and the supervisor's graceful stop,
   single-instance start, boot/resume behavior and resource limits. No scheduled
   task or automatic restart is installed by this change.
4. Drain every database writer for fresh backup/migration. Complete private owner
   provisioning, reviewed asset mapping, TLS/legacy-ingress isolation and a
   post-activation write-preserving rollback plan before protected WebUI cutover.
