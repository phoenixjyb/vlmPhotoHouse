# Face-worker qualification and rollback checklist

Status: preparation only. The face workers are not implemented or qualified by
this document, and this document does not show that any live worker is disabled.
It is a review checklist for a separately authorized Windows maintenance window.
No password, media, database, deployment, publication, restart, queue action or
host operation is included here.

The accompanying [scoped worker source](SCOPED_FACE_WORKER.md) now supplies the
bounded assignment implementation and isolated local tests. Unchecked boxes below
remain qualification requirements, not a claim that those host/device steps ran.

This gate follows the ownership and migration rules in
[LIBRARY_MANAGEMENT.md](LIBRARY_MANAGEMENT.md), the writer/backup sequence in
[OWNER_SETUP_GATE.md](OWNER_SETUP_GATE.md), and the explicit-import fencing in
[MANAGEMENT_IMPORT.md](MANAGEMENT_IMPORT.md). A Mac test, an HTTP health result,
or a passing unit test is not Windows/runtime/family acceptance.

## Release invariants

Do not proceed unless the reviewed implementation and evidence demonstrate all
of the following:

- Every manual face decision is preserved, including a deliberate manual-null
  (explicit unassignment). A null person is a decision, not an invitation to
  recluster, relabel or infer an owner. Positive manual labels are immutable to
  automatic workers unless a separately authorized correction workflow changes
  them.
- Candidate faces, reference faces, jobs and target people are selected only
  within the explicitly requested library scope. A person/target must have
  explicit ownership for that library; no name, folder, similarity or asset
  movement may infer ownership.
- No shared or global centroid, candidate pool, count, cache or propagation
  result can cross library boundaries. Any cache key includes the reviewed
  library and relevant model/revision identity.
- Counts and summaries are recomputed from the actual affected rows after the
  transaction, not copied from a partial/global in-memory cluster. The report
  records exact integer before/after counts and the query definition used.
- The worker refuses to start, and makes no data change, when the migrated audit
  schema/revision is absent, the schema version is ambiguous, ownership scope is
  unavailable, or the audit write cannot be proven durable in the same write
  boundary as the face change.
- Every automatic mutation has an auditable actor, library, job/request ID,
  source/revision, affected face/person IDs, old and new assignments, and a
  durable receipt or equivalent recovery handle. Failure rolls back the full
  transaction, including the audit event.

## Evidence and authority preflight

- [ ] Record the exact source revision, package digest, configuration digest,
  worker entry point and intended Windows host. Verify each path and setting on
  that host; do not reuse a dated handoff, old endpoint, provider label or Mac
  path.
- [ ] Obtain separate authority for native qualification and, if applicable,
  later cutover. This checklist itself grants no permission to stop writers,
  change a schedule, run a queue, touch media/DB data, deploy, publish or move a
  robot.
- [ ] Privately identify the database, derived-data root, model installation,
  logs, service account and scheduler/task definitions. Confirm ACLs under the
  actual service principal, not an elevated interactive shell. Keep all private
  paths, IDs, credentials and media out of this report.
- [ ] Confirm the database is at the reviewed management head (`d8e5b2f7a904`)
  and that the audit tables/schema required by the worker are migrated. If the
  revision or audit schema cannot be established read-only, record **REFUSED**;
  do not let legacy initialization perform runtime DDL.
- [ ] Capture a read-only baseline: exact task states (face detection, embedding,
  clustering, reclustering, propagation and caption), writer identities,
  library/ownership row counts, manual-positive count, manual-null count,
  unassigned count, and current caption queue fingerprint. Counts must identify
  the SQL/filter definition and timestamp.

Use only commands assembled from paths and configuration values independently
verified on the target host. The following are non-executable command slots,
not commands to run:

```text
<VERIFIED_REPO_PYTHON> <VERIFIED_READ_ONLY_AUDIT_ENTRYPOINT> \
  --database <VERIFIED_PRIVATE_DATABASE> --library <REVIEWED_LIBRARY_ID> \
  --config <VERIFIED_CONFIG>
<VERIFIED_REPO_PYTHON> -m pytest <VERIFIED_WORKER_TEST_SELECTOR>
```

Do not substitute a guessed executable, database, library, provider, port or
Windows path. Attach stdout/JSON receipts privately and summarize only digests,
counts and pass/refused outcomes here.

## CPU synthetic qualification

- [ ] Build a minimal migrated SQLite fixture with at least two libraries and
  assets/faces that exercise: two similar people in different libraries, a
  manually positive label, a manual-null label, an ordinary unassigned face,
  an explicitly owned target, an unowned target, inactive/moved assets and an
  empty affected set.
- [ ] Run the actual worker handlers against the fixture with deterministic
  embeddings and a fake inference dependency. Prove the handler refuses an
  unmigrated/ambiguous audit schema before any assignment/ownership mutation.
- [ ] Prove library A cannot read, match, count, centroid, propagate to or alter
  library B. Prove an owned target is required and automatic person creation is
  either prohibited or explicitly owned in the same reviewed transaction.
- [ ] Prove manual-positive and manual-null rows are unchanged byte-for-byte
  (assignment, decision/provenance and audit history). Test rerun/idempotency,
  interruption/rollback and an audit-write failure.
- [ ] Compare exact affected counts to fresh fixture queries after commit;
  include zero rows and duplicate candidates. Reject any report based only on
  candidate-list length or a pre-change global count.

CPU evidence is source/fixture evidence only. It does not qualify Windows
models, service-account ACLs, full-size timing, scheduled tasks or family use.

## Dependency-isolated actual-handler qualification

- [ ] In a disposable environment, load the production handler modules and
  worker transaction/audit code with inference, scheduler and network
  dependencies isolated or stubbed. Confirm the code path is the actual handler,
  not a copied helper or test-only reimplementation.
- [ ] Exercise each shipped operation separately: clustering, reclustering and
  label propagation. Record entry point, dependency versions, schema revision,
  configuration and fixture digest. A missing optional dependency is a refusal,
  not a pass.
- [ ] Verify transaction fencing, durable audit receipt, retry behavior and
  fail-closed behavior for missing ownership, missing audit schema, stale
  revision, cross-library candidate, malformed embedding and partial write.
- [ ] Verify no handler performs startup/legacy audit DDL, global pool reuse,
  implicit person ownership or count reset. Inspect SQL/log evidence for scope
  predicates and parameter binding.

This stage proves handler behavior under isolated dependencies; it does not
prove model loading or Windows execution.

## Windows model and runtime qualification

- [ ] With separately authorized native access, verify the exact model files,
  provider/runtime versions, GPU/CPU mode, working directory, environment and
  service account on the intended host. A local clone/LFS pointer or `/health`
  device field is insufficient.
- [ ] First run a read-only preflight and a bounded synthetic/native canary
  against a reviewed disposable copy or explicitly approved test library.
  Confirm process ancestry, logs, actual handler revision, library scope and
  audit receipts. Do not use family media for a canary.
- [ ] Measure peak memory, GPU memory, duration, concurrency and failure modes
  on representative full-size inputs. Record exact sample/count and whether
  cache was cold or warm. Do not generalize historical `c7f4a9e2b610` evidence.
- [ ] Verify the service principal can read only intended model/derived paths,
  write only intended logs/DB reservations, and cannot gain access through an
  elevated-shell-only path. Confirm no originals or caption text are rewritten.
- [ ] Keep the live face scheduler/workers behind an explicit, reviewed enable
  gate until all preceding evidence is accepted. Caption operation remains a
  separate compatibility and continuity gate.

## Database writer fencing, backup and rollback

- [ ] Before any live qualification or cutover, independently verify and record
  that API servers, schedulers, intake, caption workers, face workers and admin
  sessions are drained/fenced. A task-table state or a tool flag alone does not
  prove external processes stopped.
- [ ] Capture queue state and make a fresh matching private backup with host
  ACLs. Validate restoration on a different new private output. Never use an
  older rehearsal snapshot, overwrite a newer database, or restore over newer
  work.
- [ ] Define the abort threshold before execution: any invariant violation,
  missing audit receipt, unexpected writer, count mismatch, cross-library row,
  caption mutation or resource breach means stop and preserve evidence.
- [ ] For an uncommitted failure, verify transaction rollback and unchanged
  database/queue fingerprints. For a committed failure, use the durable receipt
  and reviewed recovery procedure; do not blindly rerun. A backup restore is an
  independently authorized recovery action, not an automatic rollback.
- [ ] Reopen writers only after read-back confirms schema, ownership, assignment,
  audit and exact counts. Record the before/after digests and actual writer
  identities privately.

## Caption continuity

- [ ] Treat caption work as independent. Preserve pending/running caption tasks,
  existing caption text/history, intake state and caption-worker configuration.
- [ ] Before and after the isolated face test, compare the caption queue
  fingerprint and exact pending/running/failed counts. Any change outside the
  reviewed face transaction is a failure requiring investigation.
- [ ] Verify no face-worker retry, migration, dependency initialization or
  rollback deletes, rewrites, supersedes or requeues captions. Caption-only
  compatibility must be qualified separately; face evidence cannot certify it.

## Family and device acceptance

Only after source, handler, Windows, and database gates pass:

- [ ] Revalidate protected owner/member access in the intended library. Confirm
  people and albums remain library-scoped, legacy unowned records remain
  preserved, and no face worker publishes to TV, SMB or another library.
- [ ] Test the real phone/WebUI management flow and the relevant family-device
  read-only flows separately. Check representative manually labeled faces,
  manual-null faces, newly matched faces, empty people and moved/inactive assets.
- [ ] Record user-visible labels/results and audit receipt IDs without storing
  names, face vectors, media or passwords in this repository. Family acceptance
  is not implied by HTTP 200, API tests, SMB access, thumbnail access or a
  running process.

## Sign-off record

The private qualification packet should contain the verified host/config/source
identities, fixture and sample digests, all required evidence sections, exact counts,
resource measurements, backup/restore receipts, rollback rehearsal result,
caption fingerprint comparison, and owner/member/device acceptance. If any
required item is missing, mark the worker **not qualified** and leave the live
face worker behind the explicit enable gate. Do not claim deployment, disabled
state, cutover, or family acceptance from this document alone.
