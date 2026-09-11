# Offline database preparation

`scripts/prepare_access_database.py` implements four explicit local commands.
Only disposable synthetic databases have been tested. The tool does not connect
to a service, load models, read media, consult environment database settings or
modify an existing database. It is included in the source-only staging package.

| Command | Input | Effect | Verification |
| --- | --- | --- | --- |
| `initialize --out ABS_NEW_FILE` | No existing database | Migrate empty memory database to `b6e3f9a5c721`, then create a new private file | Required tables/key, integrity, foreign keys and in-memory restore equality |
| `backup --database ABS_EXISTING --out ABS_NEW_FILE` | Explicit known-revision database | Copy one read transaction to memory, then a separate new private file | Source/copy logical equality, integrity, foreign keys and in-memory restore equality |
| `rehearse-migration --database ABS_EXISTING` | Explicit known-revision database | Upgrade an in-memory copy to the required revision and discard it | Actual Alembic chain, required tables/key, integrity and foreign keys |
| `migrate-candidate` with source, separate matching backup, reviewed digest and review references | Exact reviewed known-revision snapshot | Migrate in memory, quarantine access, create a new private candidate | Both input snapshots, quarantine barriers, integrity, foreign keys and output restore equality |

There is no command to overwrite/migrate an existing file in place, restore over a target, activate
an old backup, reopen access, grant membership or start/stop services. Initialization
creates no account, session, library, invitation, asset mapping or original-access
grant. Owner provisioning remains a separate [reviewed operator workflow](OPERATOR_TOOL.md).

Use an explicitly selected interpreter and private absolute paths. These examples
are command shapes, not authorization to select a real database:

```sh
"$PHOTOHOUSE_PYTHON" -B scripts/prepare_access_database.py initialize \
  --out "$PHOTOHOUSE_NEW_DATABASE"
"$PHOTOHOUSE_PYTHON" -B scripts/prepare_access_database.py backup \
  --database "$PHOTOHOUSE_DATABASE" --out "$PHOTOHOUSE_NEW_BACKUP"
"$PHOTOHOUSE_PYTHON" -B scripts/prepare_access_database.py rehearse-migration \
  --database "$PHOTOHOUSE_DATABASE"
```

An initialized file can feed `plan-owner`. A backup can feed `review`, which still
independently checks its complete logical state against the current target. A backup
command's success or digest never substitutes for plan review or operator authority.

## Reviewed migration/recovery candidate

First create a separate backup using `backup`. Independently review its
`source_snapshot_digest`, intended source, migration code and target revision,
operator authority, and stopped application/worker state. Then supply that exact
reviewed digest; do not silently pipe a newly calculated value past review.

```sh
"$PHOTOHOUSE_PYTHON" -B scripts/prepare_access_database.py migrate-candidate \
  --database "$PHOTOHOUSE_DATABASE" --backup "$PHOTOHOUSE_NEW_BACKUP" \
  --out "$PHOTOHOUSE_NEW_CANDIDATE" \
  --reviewed-snapshot-digest "$PHOTOHOUSE_REVIEWED_SNAPSHOT_DIGEST" \
  --authority-reference "$PHOTOHOUSE_AUTHORITY_REFERENCE" \
  --quiescence-reference "$PHOTOHOUSE_QUIESCENCE_REFERENCE"
```

The source and backup must be physically separate regular files with identical
logical contents, both matching the reviewed SHA-256 snapshot digest. Both read
transactions remain open through output verification. Stale content, same-file or
hardlink backups, invalid references, WAL and sidecars are refused. References are
opaque local review IDs (3–80 ASCII letters, digits, underscores or hyphens), never
phones, passwords or paths. They record external review; they do not authenticate
an operator, prove quiescence or provide a sealed/expiring approval protocol.

The candidate is upgraded through the actual Alembic chain to `b6e3f9a5c721`.
Within a separate memory transaction it uses the same quarantine mutation as
reviewed restore recovery: disable every active account, close every library,
revoke sessions, cancel unused invitations, replace the admission/plan key with
fresh random material, and clear admission buckets and stranded KDF claims.
Final access/key checks run after receipt insertion and before commit. Existing
password hashes, operator records, memberships, original grants, asset mappings,
media metadata and audit history are retained for later review. A pre-access
source acquires no accounts, libraries, mappings or access grants.

An unsigned preparation receipt is stored in `access_provisioning_receipts`, with
a fresh ID, operation, revisions, source/backup snapshot digest and review references.
It is preparation provenance, not an operator authentication event or proof of
cutover; no fictitious operator/audit actor is created. Output reports the new
file hash, logical digest, receipt ID/digest and quarantine flags, never the key.
Existing review-plan seals are invalidated in the candidate by key rotation.
Each separate candidate gets fresh key material; existing outputs cannot be reused.

Migration, entropy, quarantine or receipt failure discards the memory candidate
without an output. Failure while copying/fsyncing/verifying output can leave a
private incomplete file; use the exit/inspection rules below. Input files are
never updated, renamed, restored over or deleted by this tool.

For recovery from an older archive, explicitly select a private copy of that
archive as the source and create a separate matching backup before review. The
candidate closes resurrected access but cannot reconstruct revocations or changes
made after that archive. Never select the unchanged archive as a serving database.

**No cutover or reopening is implemented.** Keep the candidate offline and retain
the original/backup privately. A later reviewed procedure must recover the owner's
credentials, reconcile memberships/original grants, open only an approved library,
and select the new database in service configuration. Starting the legacy service
against a quarantined candidate can bypass this app's authorization entirely.
Returning service configuration to an old file can also resurrect access; this is
not a safe rollback procedure. No automatic startup restore detection is added.

## Limits and failure handling

The directory and local administrator must be trusted; this is not a sandbox against
a concurrent filesystem attacker. Paths must be absolute, direct, local and regular;
symlink parents/targets and network-share paths are refused. Source device/inode
identity is checked around copying. A read transaction pins the source snapshot.
Offline quiescence remains an operational prerequisite: identity checks do not prove
that another process cannot update the database after the snapshot was taken.

Only rollback-journal `delete` mode without `-wal`, `-shm` or `-journal` files is
accepted. The command never checkpoints WAL, removes sidecars or stops a writer.
WAL conversion/quiescence requires a separately reviewed operational procedure.
Known single Alembic revisions are required; unversioned, corrupt, unknown-revision
and foreign-key-invalid databases are refused. Rehearsal does not certify arbitrary
legacy schema drift, representative production data or future migration behavior.

This bounded implementation caps input/migrated databases at 64 MiB and uses in-memory
copies and temporary SQL storage. SQL progress and backup callbacks have 30-second
budgets; these are cooperative limits, not a process memory limit or guaranteed
wall-clock deadline. Large database performance and Windows behavior are unverified.
All migrations use an explicitly supplied in-memory connection; no ambient
`DATABASE_URL`, `.env`, default database or moving revision is selected.

Outputs are created with exclusive/no-overwrite semantics and POSIX mode `0600`.
Windows ACLs, reparse-point races, crash durability and directory fsync are not
certified. Backup files preserve admission secrets and any credential/revocation
history; they must remain outside Git and media roots in a private directory.
In-memory restore equality verifies a copy, not safe service recovery. An old backup
can resurrect access; retain the existing quarantine/recovery requirements in the
full repository's `docs/security/OFFLINE_RECOVERY.md` (not shipped in this ZIP).

Success prints only command/revision, opaque snapshot and file hashes where relevant,
and verification flags. No rows, paths, phones, keys, SQL or passwords are printed.
Snapshot hashes are versioned logical digests, not signatures or authentication.
New file data is fsynced before success. Failures never delete or overwrite an output;
an incomplete private file may remain and must not be treated as a valid database.

Exit `0` means command completion, `2` refusal or incomplete preparation, `3` output
failure after completion, and `130` interruption. Inspect any new output privately
after failure; do not retry over it. A failed status does not prove that no file was
created. No remote/service action is performed by any exit path.

## Local evidence and next step

Focused synthetic tests cover empty initialization, populated and pre-access backup,
copy-only migration, source preservation, no-overwrite/symlink/sidecar rejection,
invalid revision/integrity/foreign keys, size budget, poisoned environment, migration
interruption, identity/snapshot mismatch and output failure. Candidate tests additionally cover pre-access migration, old-password/session/invitation
and plan refusal, cookie/bearer/Range denial before media open, concurrent writer
commit exclusion, fresh keys across candidates, quarantine rollback and receipt
triggers attempting to reopen accounts or restore old keys. External socket/process
operations are denied during these checks. The extracted source package runs all
four preparation command types (five invocations), seven in-process ASGI checks and three operator commands,
including review of the generated backup against an owner plan.

The CPU dependency lock is implemented in [CPU_ENVIRONMENT.md](CPU_ENVIRONMENT.md).
Next local work is explicit owner recovery and selective library reopening, followed
by a reviewed service cutover/rollback procedure. In-place migration remains absent. A real host, private HTTPS
origin, approved audience, private backup/provisioning, ingress isolation and physical
Android acceptance remain separate, unverified gates.
