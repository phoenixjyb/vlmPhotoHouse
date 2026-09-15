# Scoped automatic face assignment

Local source implementation, 2026-09-15. This is not a deployed worker, a new
model, an authorized queue producer or Windows qualification. Follow the separate
[qualification checklist](FACE_WORKER_QUALIFICATION.md) before enabling it.

## Changed behavior

The three `TaskExecutor` handlers for `person_cluster`, `person_recluster` and
`person_label_propagate` delegate to `app.scoped_face_worker.run_scoped_assignment`.
There is no global legacy fallback. Unscoped legacy payloads are permanently
refused; embedding completion no longer creates unscoped cluster/recluster jobs,
even when the old `FACE_AUTO_CLUSTER_ENABLED` variable is true.

The explicit `TaskExecutor(..., face_assignment_only=True)` mode requires injected
settings and a session factory. It initializes no embedding models/indexes, claims
only those three assignment task types, and does not enqueue idle backfills. It is
mutually exclusive with caption-only mode. It cannot claim caption, detection or
embedding work; a reviewed standalone launcher still needs to select this mode.

- Manual positives and manual-null decisions are never candidates. Clustering
  considers unassigned faces; reclustering additionally considers non-manual DNN
  assignments to exclusively owned people. Reclustering is now a bounded repair
  batch, not a global count reset or full-library rebuild.
- Jobs require an explicit library and a current active operator who is also its
  approved owner. Authority is rechecked inside the write transaction and before
  completion. This checks the selected account's current authority; it does not
  authenticate whoever has direct database/queue write access. A future producer
  must independently authenticate and authorize its caller.
- Only active mapped assets and explicitly owned people are eligible. An identity
  with any foreign or unmapped face reference is excluded entirely. Propagation
  refuses an explicitly selected target that is not exclusively owned here.
- Reference vectors come from scoped manual faces, never cached/global person
  vectors. Competition includes all eligible scoped manual-reference people;
  propagation may assign only its explicit targets. Minimum reference count,
  similarity and margin must pass. Automatic people created within a cluster
  batch can seed additional matches in that same batch. They do not become manual
  reference anchors for later batches until reviewed/labeled. This conservative
  behavior can create additional identities that require family review.
- New people and their explicit library ownership are created atomically. Affected
  source/destination counts are recomputed from **all actual face rows**, including
  rows outside this batch. Their cached person embedding pointers are cleared and
  versioned aggregates marked `stale`; no vector file is overwritten/deleted.

## Explicit payload and vector contract

Required fields: `library_id`, `operator_account_id`, `embedding_model`,
`embedding_version`, `embedding_dim`, `embedding_alignment` (string or null) and
`embedding_status` (`active` or qualified `legacy`). These must match versioned
`face_embedding_artifacts` records exactly. Shadow vectors and the historical
`unknown-legacy` dimension-only registration are not qualified matching inputs.
Do not promote/rename artifact metadata to get past a refusal without separately
establishing the provider/version/alignment provenance.

Optional fields: `max_faces` (default 100, maximum 500), `score_threshold`
(default 0.82), `margin` (default 0.015), `min_ref_faces` (default 2, maximum 50).
Propagation additionally requires 1–100 unique integer `person_ids`; other kinds
must not select target people. Unknown fields are refused. The claimed task's
stored kind and payload are rechecked under the transaction, not just trusted from
an earlier in-memory object. No automatic existing-job payload upgrade is provided.

Artifacts must be checksum-bound NPY numeric vectors (float32/64, one dimension,
1–4096 elements, finite and nonzero). Reads use a small stdlib decoder, never
pickle/model initialization. The selected direct root must exist; artifact paths
must resolve directly below it without symlinks/traversal. Files are bounded to
64 KiB, with a 4 KiB header maximum. The actual mixed handler passes its reviewed
`DERIVED_DIR`; relative paths are relative to that root, not an ambient working
directory. Host ACLs must prevent other processes changing that trusted tree.
Missing/changed/invalid selected files refuse the whole batch. Other model/status
artifacts are not silently substituted.

## Transaction, recovery and resource boundaries

An explicit SQLite transaction/write reservation surrounds the bounded matching
and mutation batch. The session must have no pending ORM edits. A savepoint protects
all face/person/ownership/count/audit mutations, so the queue can record a task
failure afterward without committing partial assignments. No inner progress commits
remain. The worker requires management revision `d8e5b2f7a904`, foreign keys and
all required migrated tables; it does not create schema.

Each changed assignment records old/new provenance, actor and task ID. A completed
batch adds a library-scoped `access_audit` action `face.batch.<task-id>` in the same
transaction, even for zero assignments. This is its durable recovery handle. A
repeat attempt for the same task refuses; inspect that audit before recovering
a job interrupted after batch commit but before queue completion. This does not
create an offline provisioning receipt or undo committed assignments.

Limits: 1,000 eligible people, 2,000 selected manual references, 500 candidates,
and a ten-second cooperative CPU/SQL budget per batch. These are resource guards,
not throughput or full-library completion claims. Blocking filesystem calls and
SQLite lock acquisition require separate host supervision/timeouts. Cancellation
is checked before the batch; new cancellation requests wait for its short write
reservation to finish. Tune limits only after measured native qualification.

The legacy audit helper now requires its migrated table on the caller's connection
instead of creating/caching it. Legacy dependency initialization refuses any
database containing `access_*` tables before fallback DDL; use explicit protected
runtime wiring. Old unprotected startup behavior is not otherwise replaced.

## Remaining delivery gates

The follow-on [private job control](FACE_JOB_CONTROL.md) adds authenticated offline
enqueueing and a single-task launcher; no protected HTTP route or recurring face
scheduler is added. The launcher uses `commit=False` so batch changes and task
completion share its outer transaction. The default core call retains its existing
commit behavior for legacy handlers. The protected WebUI and caption-only worker
remain separate; this module must not be mounted into the protected HTTP process.
Native launch/package/producer qualification remains required before live use. Existing face
detection and embedding production must separately qualify versioned artifact
registration, provider availability, storage ACLs and bounded runtime behavior.
Legacy queues and family media were not inspected or changed for this slice.

Caption inference, prompts, caption-only queue selection, captions and original
media are unchanged. Source and isolated-handler tests do not prove native model
loading, Windows performance, family acceptance, migration or password readiness.

## Local evidence

The local security run completed 732 tests in 151.135 seconds, OK with four
Windows-native skips. It used the separate worktree dependency environment rather
than treating missing legacy dependencies as handler coverage. There are 15 focused
scoped-assignment tests and an isolated child with seven actual-handler checks.
After the final assignment-only constructor/queue guard, the isolated child checks
and all 17 caption-worker tests passed again (including their actual runner cases).
Synthetic NPY files, migrated SQLite, injected settings and blocked external I/O
are used; this is not model-inference or native Windows evidence. No visual UI
code changed, so browser/device acceptance was not rerun for this slice.
