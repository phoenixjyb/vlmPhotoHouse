# Offline restore quarantine — slice 16

This slice adds a reviewed, atomic quarantine operation for an **already restored**
PhotoHouse database. It invalidates restored access artifacts and leaves all accounts
disabled and libraries closed. It does not restore a file, reopen access, reset a
password, discover a database, stop a worker or expose an HTTP/CLI entry point.
All execution used disposable synthetic SQLite and the in-process ASGI test client.

## Candidate preparation addition — 2026-09-11

[Database preparation](DATABASE_PREPARATION.md) now exposes a new-file
`migrate-candidate` workflow for a reviewed source snapshot and separate matching
backup. It reuses this service's quarantine mutation, including final access/key
checks after receipt insertion. It runs migration/quarantine only in memory before
creating a new private file, so pre-access databases need no invented operator.
Its unsigned preparation receipt is distinct from this service's sealed review and
operator-attributed audit. It neither replaces this reviewed in-place quarantine
API nor implements cutover, owner recovery or reopening. The slice-16 evidence
below remains historical; current results are in [the Android return](ANDROID_READINESS_RETURN.md).

## Why session revocation alone is insufficient

An older backup can resurrect sessions, cancelled invitations, old password hashes,
previously revoked memberships and original-media permissions. A restored password
could create a new session even after old sessions were revoked. Recovery therefore
closes both accounts and libraries while retaining membership and mapping records
for later review. Simply restoring a backup and restarting services is unsafe.

## Reviewed workflow

The operator must independently establish authority, stop all application/worker
processes, select the exact restored file and retain a separate matching backup
before planning recovery. A required opaque `quiescence_reference` records the
review of stopped workers. It is not proof that processes have stopped and cannot
be supplied by a remote client as authorization. Clearing a KDF claim while an old
worker is still running could violate the single-worker memory limit.

`RecoveryPlanner` requires a read-only connection. Its sealed 15-minute plan binds
an existing operator record, the quiescence reference, a full database fingerprint
and the counts of affected account, library, session, invitation and admission
records. Disabled operator records are accepted for attribution when quarantining
a repeated restore; restored credentials do not authenticate the local operator.
The plan grants nothing and contains no credentials or private media paths.

`review_recovery_backup()` shares the existing exact-file and backup verification:
explicit target and separate backup, exact reviewed plan digest, authority and
restore review references, integrity/foreign-key checks, logical snapshot agreement
and restoration into memory. Review objects are local in-process artifacts, never
untrusted serialized requests. Snapshot scans can be expensive; the database must
remain quiescent. This verifies SQLite content, not host disaster recovery.

`quarantine_restored_access()` rechecks the plan, snapshot, backup and physical file
identities under one `BEGIN IMMEDIATE` reservation. It rechecks time-sensitive state
after scans and rejects expiry before committing.

| Atomic effect | Scope |
| --- | --- |
| Disable accounts | Every currently active account becomes disabled. Password hashes and operator records remain intact; no credential reset or account activation. |
| Close libraries | Every active library becomes closed. Membership roles, approvals, original grants, revisions and asset mappings remain intact for review, with access blocked. |
| Revoke sessions | All unrevoked restored sessions become revoked; old bearer and cookie credentials cannot authenticate. |
| Cancel invitations | Every unused, uncancelled invitation becomes cancelled, including expired records. Consumed invitations remain unusable. |
| Invalidate plans | Replace the shared admission/plan HMAC key with fresh random bytes. Old owner, asset and recovery plan seals fail. No key is accepted as input or returned in a receipt. |
| Reset admission | Delete old attempt buckets and the stranded KDF claim under the reviewed stopped-worker prerequisite. No automatic timeout-based claim stealing. |
| Record receipt/audit | Use the existing unique plan-ID/digest receipt table. Record affected counts, references, backup fingerprint and file identity, with `access_reopened=false`. Receipt, audit and all effects commit together. |

A failed insert, audit failure, expiry, target change or entropy failure rolls back
all database effects, including key replacement. Replaying the old recovery plan
fails. A separately authorized new recovery after another restore uses fresh random
material again; a database counter or timestamp would repeat after rollback.
No new migration is needed; required revision remains `b6e3f9a5c721`.

## Verification and limits

**198 Python security tests passed**, including 18 new recovery tests. Focused tests
cover unchanged read-only planning/review, affected state and redaction, old
password/session/invitation refusal, all old plan seals, operator/quiescence/digest
requirements, stale/replaced target/backup, expiry during scans and after audit,
receipt/audit/entropy rollback, concurrent application and replay, writer exclusion
in rollback-journal and WAL modes, and repeated restoration with distinct new keys.

The real closed ASGI app rejects old cookies and bearer tokens for session, gallery,
original Range, thumbnail and face-crop requests before opening media. An additional
synthetic partial-reopening test enables only an account and confirms that closed
libraries still deny access. These tests are not a supported reopening procedure.

Evidence: [Python suite](evidence/recovery-slice16/python-tests.txt) and
[inventory](evidence/recovery-slice16/inventory.txt). Inventory remains **152 entries:
23 active, 97 retired, 32 standalone**. The historical unsafe-handler ledger remains
**84/84 failed denial requirements**, expected exit 1; those handlers stay unmounted.
Inventory completeness is not proof of authorization.

No UI, route, runtime schema or browser transport changed. The previous 14 Chromium
UI/ASGI checks remain historical evidence from slice 15 and were not rerun here.
Their Fetch Metadata modeling and real TLS/proxy/CORP limitations still apply.
The legacy backend suite, live hosts, production-size data, Windows recovery,
mobile devices and deployment were not exercised.

## Required next review before reopening

This operation does **not** detect that a database was restored. An old backup can
still resurrect credentials until an independently authorized operator quarantines
it while services remain stopped. The unchanged archive still contains its old keys
and credentials. Repeating a restore requires repeating quarantine. Device/inode
checks and receipts are not protection against malicious filesystem administrators
or rollback of the entire database. No automatic startup safety claim is made.

The next bounded slice should define and test explicit owner recovery and library
reopening. It must require a new protected password, review the restored owner and
operator records, reconcile post-backup membership revocations and original grants,
and refuse to reactivate a restored audience wholesale. Missing post-backup records
cannot be reconstructed from the backup itself. Keep every unreviewed account and
library closed. Then package the reviewed services in an operator tool with exact
target/backup selection, protected input and redacted failures.

The 97 retired routes and 32 independently exposed model/diagnostic routes remain
separate gaps. Search, albums, curation, upload, destructive/jobs and voice features
remain closed. Live backup/restore, credentials, TLS/proxy isolation, runtime identity
and device acceptance need separate authorization and verification.

## Local checkpoint

Branch: `codex/mobile-access-foundation`. Parent:
`8728b7c14e781a4b235629ff2a2c8acb425f38d3`; base:
`932263504ac5fcc3ed178e951991619d8ee87049`. Local edits/tests/commit only; no push,
merge, deployment, real database/media access, model loading, network listener,
Windows/Mac mini access or mobile edits. Original backend and mobile checkouts remain
clean at the heads recorded in the [earlier handoff](FOUNDATION_HANDOFF_2026-09-09.md).

Changed files in this slice:

- [backend/app/access/provisioning_apply.py](../../backend/app/access/provisioning_apply.py)
- [backend/app/access/recovery.py](../../backend/app/access/recovery.py)
- [docs/security/FOUNDATION_HANDOFF_2026-09-09.md](../../docs/security/FOUNDATION_HANDOFF_2026-09-09.md)
- [docs/security/OFFLINE_PROVISIONING_APPLY.md](../../docs/security/OFFLINE_PROVISIONING_APPLY.md)
- [docs/security/OFFLINE_RECOVERY.md](../../docs/security/OFFLINE_RECOVERY.md)
- [docs/security/evidence/recovery-slice16/inventory.txt](../../docs/security/evidence/recovery-slice16/inventory.txt)
- [docs/security/evidence/recovery-slice16/python-tests.txt](../../docs/security/evidence/recovery-slice16/python-tests.txt)
- [tests/security/test_offline_recovery.py](../../tests/security/test_offline_recovery.py)
