# Offline access-schema application

`scripts/apply_access_schema.py` applies only the reviewed additive transition from
`d2b7e4f6a901` to `c7f4a9e2b610`. It is an operator tool, not an API/startup hook.
It creates no account, password, session, library, media mapping or HTTP listener.
The default operation reviews the selected target and separate backup read-only.

Execution requires explicit `--execute --all-writers-stopped`. The latter is an
operator assertion, not automated proof that every process has stopped. The
operator must drain and fence all writers, review target/backup identities and
ACLs, and arrange recovery and the next serving configuration before using it.
The standalone caption worker is separate from the API and must be drained too.
Do not start a maintenance outage while waiting for an unavailable owner to enter
a password or while the replacement/rollback service configuration is unresolved.

Both files must already be offline DELETE-journal databases without sidecars.
The tool does not checkpoint WAL, create backups, replace files, stop services or
change scheduler actions. Use a fresh backup made at the actual stopped boundary;
earlier online rehearsal snapshots are not current production backups.

```text
python -I scripts/apply_access_schema.py
  --database ABS_OFFLINE_DATABASE --backup ABS_MATCHING_BACKUP
  --reviewed-backup-digest REVIEWED_FULLSIZE_SNAPSHOT_DIGEST
  --max-bytes 2147483648 --timeout-seconds 900
```

Review verifies integrity, foreign keys, the pre-access revision, no access tables,
no running tasks and identical streamed logical fingerprints. Execution repeats
the comparison under a DELETE-mode exclusive SQLite transaction, uses that same
explicit SQLAlchemy connection for transactional Alembic DDL, verifies the required
schema and every pre-existing table/column value except the revision ledger, then
commits once. A competing writer, stale backup, preservation failure or exception
before commit refuses/rolls back. Ambient DATABASE_URL does not select a target.
The resource budget uses the existing disk-backed rehearsal limits; this is not
an OS memory reservation. Host-native qualification remains necessary.

An exclusive transaction does not replace process fencing: another process could
reconnect after commit. A lost success message or interrupted controller is not
permission to rerun or restore a backup. Inspect the actual revision, data and
private receipt. Once new captions or credentials have been committed, an old
database restore would discard them; use a write-preserving recovery decision.

After schema application, owner creation still uses the separately reviewed
[operator workflow](OPERATOR_TOOL.md), including a fresh matching backup, an
unexpired plan and hidden interactive password confirmation. No password argument,
stored password file or HTTP bootstrap shortcut is introduced. Do not claim the
legacy unauthenticated UI is protected merely because access tables now exist.
Protected serving, legacy route isolation and media mapping remain distinct gates.

Tests use only synthetic catalogs and cover default read-only behavior, successful
preservation, empty grants, refused running/WAL/stale/repeated targets, explicit
shutdown confirmation, a racing writer, and rollback after DDL/data-change/timeouts.
