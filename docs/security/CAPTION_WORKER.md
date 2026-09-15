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
  task. Inference uses the existing external loopback service. Stub fallback is
  disabled. Caption-derived tagging defaults off but can be explicitly enabled
  through reviewed settings to preserve the live pipeline's search tags. It uses
  the existing local tag extractor, not another model or task queue.
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
`c7f4a9e2b610` or `d8e5b2f7a904`; the actual file must match the selected revision exactly. No schema
creation or migration is attempted. The execution connection uses SQLite `mode=rw`
so a missing file cannot silently become a new catalog.

Only after separate authorization and shutdown verification, add
`--execute --legacy-worker-stopped`; `--once` limits the run to one claim attempt,
including an idle attempt. It does not select a particular asset or retry failed
jobs. A processed claim can finish, retry or fail under existing policy; the
reported count is **not** a count of successful captions.

JSON is an object of string values. Allowed keys are listed in the launcher's
`NUMBERS`, `TEXT` and `BOOLEANS` constants: caption prompt/profile/infant-care exceptions,
word/variant/policy retry limits, HTTP retry/delay/timeout/image-edge settings, and
queue retry/backoff and caption-derived tagging settings. Booleans must be the
strings `true` or `false`. Unknown keys, duplicate keys, non-finite numbers and
out-of-range numbers are refused. No passwords or API tokens belong in this file.
Omitted values retain the source handler defaults except word count (zero) and
caption-derived tagging (off).
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
test dependencies installed, it also runs seven isolated processes against a real
synthetic migrated SQLite database: caption commit + stop, user-edit preservation,
retry, idle, unavailable provider, missing shutdown confirmation, and explicitly
enabled caption-derived tagging. Future tasks
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

## Immutable worker candidate

`scripts/build_caption_worker_package.py --commit FULL_LOCAL_COMMIT --out ABS_NEW_ZIP`
builds a fixed 15-file worker-only source package. It accepts only regular Git
blobs from an immutable commit, not the dirty working directory. It includes the
caption prompt and local tag extractor, but excludes `.env`, private configuration,
media, databases, migrations, Python environments, model weights and HTTP entry
points. The manifest hashes every source file. Existing output is never overwritten.
The protected WebUI package remains separate.

The candidate incorporates the previously installed pre-upload resize change:
EXIF orientation followed by aspect-preserving LANCZOS at the explicitly reviewed
maximum edge (1536 for the verified installation), no upscaling, one prepared image
reused across visual corrections, and permanent classification of exact legacy
pixel-limit rejections. Original media is not modified. Original-image decoding
is still full resolution; this does not impose a decoder memory bound or change
the legacy loader's Pillow safety configuration.

`tests/worker/test_caption_input_preparation.py` retains the 23 synthetic resize,
provider-isolation, retry-classification, temporary-file and source-preservation
checks from the recovered implementation. Run with separate worker dependencies,
`PYTHONPATH=backend`, `PHOTOHOUSE_NO_DOTENV=1`, an explicit test `DERIVED_PATH`,
and `pytest -o addopts= tests/worker/test_caption_input_preparation.py`.
For package qualification, the fixture runner accepts an optional **test-only**
migration source root; migrations and fixtures do not enter the worker artifact.

Keep effective environment capture private on Windows. Compare the live process
environment, unchanged-since-startup `.env` inputs and source defaults; preserve
caption exceptions, policy/HTTP/queue retries and tag settings. Setting the word
cap to zero explicitly implements the user's no-hard-cap preference (the bilingual
path already bypassed truncation). Do not silently replace missing settings with
unreviewed values or treat a config file/manifest as proof of activation.

## Windows runtime acceptance — 2026-09-15

The separate worker artifact from commit
`26c65daab6b99a9d053009cdc0d2f544861d5f5d` passed real photo and short-video
inference under the Windows SYSTEM principal against an isolated migrated catalog.
The photo handler completed in 62.25 seconds and the video in 28.45 seconds.
An in-flight stop request drained after the first task, a concurrent duplicate
was refused, and a fresh worker completed the second task. Original-file hashes
and production assets/captions/tasks/tags/asset_tags fingerprints matched before
and after the isolated test. These are two-sample runtime checks, not full-library
quality, sustained throughput, boot/wake or physical-device acceptance.

Following a separately backed-up safe queue boundary, the existing API was
restarted with its supported `-DisableInlineWorker` option. An on-demand SYSTEM
task now owns the separate caption worker; the API startup wrapper requests it
only after healthy API/database readiness with the inline worker disabled.
The supervisor checks artifact/config hashes and refuses non-caption pending or
running work at startup. It does not add an owner for other task families.

At 15:33 China time the handover controller completed successfully after two live
batch successes (12,410 to 12,412); the separate worker remained running. The API
and Qwen3 service were healthy, the Mac WebUI returned HTTP 200, all 8,364 temporary
pending schedule holds were restored, and the 157 failed / 15 dead jobs were not
requeued. The live schema remained `d2b7e4f6a901`. No model service restart,
protected WebUI activation, owner provisioning or database migration occurred.

Operational interpretation: API `worker_enabled=false` is now expected and is
**not** evidence that captioning is paused. Verify the separate worker task,
process and database progress. API shutdown alone no longer drains captioning.
Before sleep, migration or rollback, request the separate worker's retained stop
file and verify its exit and the queue boundary, then drain other writers.
Future resume must deliberately clear that exact request after authorization;
it must not silently clear it during API startup. Host-specific task identities,
stop path, configuration, receipts and prior API scheduler XML are retained in
the private deployment handoff. No new timed/wake triggers or live-monitoring
automation were installed. Boot/wake remains a separate untested gate.
