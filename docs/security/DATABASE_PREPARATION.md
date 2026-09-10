# Offline database preparation

`scripts/prepare_access_database.py` implements three explicit local commands.
Only disposable synthetic databases have been tested. The tool does not connect
to a service, load models, read media, consult environment database settings or
modify an existing database. It is included in the source-only staging package.

| Command | Input | Effect | Verification |
| --- | --- | --- | --- |
| `initialize --out ABS_NEW_FILE` | No existing database | Migrate empty memory database to `b6e3f9a5c721`, then create a new private file | Required tables/key, integrity, foreign keys and in-memory restore equality |
| `backup --database ABS_EXISTING --out ABS_NEW_FILE` | Explicit known-revision database | Copy one read transaction to memory, then a separate new private file | Source/copy logical equality, integrity, foreign keys and in-memory restore equality |
| `rehearse-migration --database ABS_EXISTING` | Explicit known-revision database | Upgrade an in-memory copy to the required revision and discard it | Actual Alembic chain, required tables/key, integrity and foreign keys |

There is no command to migrate an existing file, restore over a target, activate
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
interruption, identity/snapshot mismatch and output failure. External socket/process
operations are denied during these checks. The extracted source package runs all
three preparation commands, seven in-process ASGI checks and three operator commands,
including review of the generated backup against an owner plan.

Next local work is a reviewed CPU dependency lock and a separately designed
existing-database migration apply/recovery procedure. A real host, private HTTPS
origin, approved audience, private backup/provisioning, ingress isolation and physical
Android acceptance remain separate, unverified gates.
