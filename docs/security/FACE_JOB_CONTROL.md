# Private, exact-task face assignment

This is a local operator workflow, not a new HTTP endpoint or a live deployment.
It assigns existing qualified face vectors; it does not detect faces, create
embeddings, load models, caption media, or make missing native qualification pass.
The protected library and anonymous TV access remain separate.

## Submission

Use `scripts/provision_access.py plan-face-job` with an explicit existing migrated
database, a private request JSON and a fresh private output plan. The request has
exactly `kind`, `payload`, and `quiescence_reference`. The kind and payload follow
[the scoped assignment contract](SCOPED_FACE_WORKER.md); the last field is an
opaque independent all-writer shutdown review reference, never a secret or path.

The plan binds current owner/operator authority and password hash, library scope,
ownership revisions, selected manual anchors/candidates, asset hashes, vector
checksums and all matching parameters. No vectors or media are opened at planning.
Only one bounded face task may be outstanding; pending caption tasks are untouched.
An empty selection, running task, other pending face job, or non-offline database
refuses. The plan lifetime is **15 minutes**, including submission and execution;
this is not an overnight scheduler.

Follow the existing `validate`, `review`, and `apply` workflow documented in
[Operator tool](OPERATOR_TOOL.md). Review requires a distinct matching database
backup and an independently reviewed authority/restore reference. Application
requires the exact plan/review digests and `--all-writers-stopped`. Use only an
approved maintenance window; this tool does not stop any writers for you.

`apply` prompts once for the **existing owner's password** using non-echoing
terminal input. No password argument, environment variable, chat entry, fallback
echo or owner bootstrap is accepted. Authority, metadata, backup and expiry are
checked again before a single transaction inserts the pending task, audit and
signed receipt. It does not execute the task. The safe summary includes `task_id`.

Direct database/filesystem access remains privileged. The password check does not
turn this offline tool into a public login API or replace host ACLs. Keep the full
plan and receipt private; ordinary command output omits names, vectors and paths.

## Exact execution

`scripts/run_face_worker.py` requires explicit `--database`, `--embedding-root`,
`--task-id`, `--plan-id`, `--reviewed-plan-digest`, and `--stop-file` arguments.
Without `--execute`, it performs read-only preflight; this does not establish full
cohort or vector qualification. Actual execution additionally requires
`--legacy-worker-stopped` and the authenticated enqueue receipt.

The launcher holds a per-database process lock, revalidates the exact receipt,
current owner, cohort and pending task under a SQLite write reservation, then
executes only that task. It never picks another task or retries a failed batch.
Face mutations, audit and task completion commit together; refusal rolls back.
Inspect the durable task and batch audit after interruption before deciding any
manual recovery. Never repeatedly resubmit an expired or refused task blindly.

The stop file is an operator-owned stop request, checked before execution; it is
not a service controller. Independent legacy writer shutdown and filesystem ACLs
remain operator gates. This local process lock cannot fence unrelated programs.

## Packaging and delivery gates

`scripts/build_face_worker_package.py --commit <full-commit> --out <new-absolute-zip>`
builds a deterministic source-only allowlist. It includes no credentials, database,
vectors, models, settings discovery, HTTP listener or dependency installation.
Use a separately qualified CPU environment containing SQLAlchemy. The protected
staging package includes the planning support for the private operator CLI only;
it does not mount the worker into the protected HTTP application.

Local regression coverage uses migrated synthetic databases and tiny synthetic
vectors. Seven submission tests cover password input/refusal, stale metadata,
backup/replay gates, rollback and caption preservation. Seven launcher tests cover
isolated execution, copied source-package execution, tampering/expiry, stop/lock
refusal, corrupt vectors, and a completion-trigger failure after face mutation
that must roll back the batch and claim together. Package tests verify exact
contents, deterministic hashes and rejected unsafe/missing Git inputs.
The final local security run completed 749 tests in 159.914 seconds, OK with four
Windows-native skips. All 17 caption-worker compatibility tests also passed.
These are source/synthetic checks, not Windows execution or family acceptance.

Before live use, complete [native face qualification](FACE_WORKER_QUALIFICATION.md):
Windows service-principal storage access, artifact provenance/quality, measured
runtime, approved maintenance/backup/restore, owner password readiness and a small
family-reviewed canary. No captioning pause, live enqueue, restart, deployment,
publication, password setup or remote inspection is authorized by this document.
