# Full-size, copy-only migration rehearsal

`scripts/rehearse_fullsize_database.py` is preparation, **not a cutover tool**.
It does not change the existing 64 MiB offline/operator tools, migrate the live
database, create accounts, start a listener, stop captioning or retry jobs.

1. `snapshot` opens an explicitly selected source with SQLite `mode=ro` and
   `query_only`. It pins one transaction, including committed WAL content, and
   uses SQLite backup to create a new disk-backed rollback-journal snapshot.
   Streaming row fingerprints and integrity/foreign-key checks verify the copy.
   A concurrent WAL writer can continue; the snapshot is necessarily stale as
   soon as later commits happen. It is **never a cutover-ready backup**.
2. Independently inspect the snapshot result/digest, exact target and source
   revision. `rehearse` requires that reviewed digest and an offline DELETE-mode
   snapshot with no sidecars. It exclusively creates a second file, migrates only
   that copy using an explicit connection, then quarantines access with a fresh
   admission key. It creates no user or access grant.
3. Compare every pre-existing column/row except the revision ledger and the seven
   intentionally quarantined authentication tables. This includes AI captions,
   legacy edits, tasks, media metadata, family stories and revisions when present.
   Additive columns are permitted; changes to existing values fail closed.
4. Create a third disk-backed restore copy and verify all migrated rows and the
   quarantine barrier. Keep snapshot, rehearsal and restore files private and
   offline. Neither output is automatically eligible for activation.

Commands require canonical, explicit native paths and explicit resource budgets:

```text
python -I scripts/rehearse_fullsize_database.py snapshot
  --database ABS_LIVE_DATABASE --out ABS_NEW_SNAPSHOT
  --max-bytes 2147483648 --timeout-seconds 480

python -I scripts/rehearse_fullsize_database.py rehearse
  --database ABS_REVIEWED_SNAPSHOT --out ABS_NEW_REHEARSAL
  --restore-out ABS_NEW_RESTORE --reviewed-snapshot-digest REVIEWED_DIGEST
  --max-bytes 2147483648 --timeout-seconds 480
```

The examples are shapes, not permission to select any database. Paths, accounts,
credentials and real data belong in private host receipts, never source control.
Each invocation prints a small JSON result only after all its checks finish.
Exit 2/130 means refused/incomplete/interrupted: retain and inspect partial outputs,
never reuse them as successful backups and never overwrite them on retry.

## Resource and trust limits

- No whole database is copied into Python memory. SQLite cache is 8 MiB per
  connection, memory mapping is off and sorting uses file-backed temporary storage.
  This is not an OS-enforced memory cap; a host supervisor should bound and record
  memory, runtime and temporary disk use before real execution.
- Explicit size budget: 1 MiB–8 GiB. SQL and backup callbacks share a monotonic
  deadline (at most 30 minutes). A value/row larger than 16 MiB is refused.
- Output creation requires free space exceeding three database sizes plus 256 MiB.
  This check is not a reservation; concurrent disk consumers remain a host concern.
- A pinned WAL reader can delay checkpoints and grow WAL while writers continue.
  Use a bounded maintenance preparation window; do not leave a stalled reader.
- Require a trusted private directory on local storage, with Windows ACLs reviewed
  **before** copying credentials/metadata. POSIX 0600 is not a Windows ACL. Put
  temporary storage under the same private directory. Filesystem administrators
  and hostile concurrent path replacement are outside this tool's threat model.
- Existing files, symlinks, unversioned/unknown/corrupt/FK-invalid databases,
  oversized values and virtual tables are refused. Outputs are retained, not
  automatically removed. Restore equality proves a disk copy, not recovery of a
  running service or preservation of changes made after the snapshot.

## Remaining production gates

Actual rollout still needs a reviewed pause/drain of **every** database writer,
a fresh backup at the safe boundary, qualified provisioning at full database size,
worker-only compatibility with the new schema, TLS and ingress isolation, owner
password entry, explicit asset mapping and a rollback plan that preserves writes
after activation. Owner/asset provisioning can now use an explicit new disk restore
file for each review/apply invocation; see [Operator tool](OPERATOR_TOOL.md). The
default and recovery workflows remain in-memory. This rehearsal does not silently
raise or bypass those limits. Do not serve
a quarantined copy through the legacy unauthenticated HTTP entry point.

The WebUI defaults bare 11-digit phone inputs to +86 for sign-in, invitation-based
registration and owner invitations. Full international numbers starting with +
remain supported. The server and stored identities still require explicit E.164;
API/operator clients must normalize deliberately. No phone number or password is
hard-coded in source and no SMS verification is implied.

## Bounded native qualification (2026-09-15)

On a private Windows copy of the 955,658,240-byte catalog, the actual operator CLI
completed plan, disk-backed review, apply with an independent disk restore, and
receipt lookup. Only a fictional owner was created, then disabled with its library
closed and the admission key rotated. No asset mapping, session or original-media
grant was created. The run took 154 seconds with about 172 MiB peak sampled memory.
The source and live databases were not updated.

`tests/security/fullsize_provisioning_canary.py` implements that copy-only check.
It requires an already quarantined source and a new private working directory.
It is not an owner-setup shortcut: its fictional password injection belongs only
to the offline test. Real setup retains the operator's private password prompt.

`tests/security/legacy_caption_schema_canary.py` then exercised the **installed**
legacy ORM and caption handler against the migrated offline copy. It bypasses
executor initialization, supplies a generated image and fake bilingual Qwen3
provider, and forbids network/process calls and other SQLite targets. AI refresh,
preservation of a user-edited caption, separate stories and revision history, and
unchanged task counts passed. Unique synthetic identifiers retain failed-attempt
evidence without overwriting fixtures. The successful run took 2.5 seconds with
about 79 MiB peak sampled memory and did not import Torch.

The first handler attempt exceeded its 384 MiB test-process watchdog; a repeat with
test-local numeric-library thread counts set to one stayed below that budget.
This is not a diagnosis or fix of production memory use. A second attempt exposed
a mismatched mock model label; only the fixture was corrected, preserving the
production Qwen3/bilingual validation gate. Failed receipts are retained privately.

These checks do **not** qualify queue startup, real inference, GPU behavior,
protected HTTP/TLS traffic, or a worker-only service. The installed worker still
belongs to the legacy API process. A separately qualified worker-only lifecycle
and private owner password setup remain prerequisites to controlled cutover.
