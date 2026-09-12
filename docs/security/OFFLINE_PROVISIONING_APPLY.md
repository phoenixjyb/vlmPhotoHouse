# Offline provisioning apply — slice 15

Continuation: [slice 16 offline restore quarantine](OFFLINE_RECOVERY.md) invalidates
restored plans/sessions/invitations and leaves accounts and libraries closed.
The slice 15 implementation and evidence below remain the historical checkpoint.

This continues the completed 14:00 checkpoint following the user's renewed request.
The offline service now applies a reviewed owner or asset plan atomically. It has
**no HTTP route, automatic startup hook or command-line entry point**. All executed
operations used disposable synthetic SQLite. No live accounts, credentials, media,
services, mobile files, Windows or Mac mini were accessed or changed.

## Review and application contract

The caller must already have independently established local database authority.
`review_backup()` requires explicit existing target and separate backup `Path`
objects, the SHA-256 digest of the exact reviewed plan, and opaque references to
that authority review and the independently reviewed restore procedure. References
are audit labels, **not authentication**. `ApplyReview` is a local in-process object;
it must never be accepted from HTTP or deserialized from untrusted input.

The review checks the plan's HMAC and current state, direct regular-file identities
(device/inode), SQLite integrity and foreign keys. It compares complete logical
SQLite snapshots of target and backup, then restores the backup into memory and
checks it again. It creates no backup file, grants nothing and opens both supplied
files in read-only mode. Logical SQL and credential records stay in process memory;
only fingerprints are retained. The restore rehearsal checks SQLite content; it
does not certify the host's recovery procedure, file permissions, backup retention,
operator authority or disaster recovery.

`apply_reviewed()` performs a read-only preflight, then reserves SQLite's writer
with `BEGIN IMMEDIATE`. Under that same reservation it repeats seal, expiry, actor,
audience, asset, exact target, receipt and backup checks before inserting anything.
Any database change since review, including an unrelated login/audit write, refuses
application and requires a fresh backup/review. This intentionally requires an
operationally quiescent database. Snapshot scans may be expensive on large databases;
no production-size performance claim is made.

| Operation | Effect and deliberate limits |
| --- | --- |
| New owner | Protected password and confirmation prompts; echoed-input fallback is rejected. Scrypt runs before the write reservation. Creates exactly one new account, operator, library and approved owner membership. Creates no session, original grant or asset mapping. Existing targets are refused. |
| Assign assets | Applies only the exact sorted active unmapped IDs to the selected active library. The selected actor must still be both operator and approved owner. Audience, original permissions and all selected asset fingerprints must still match. No reassignment, media access or file writes. |
| Receipt | Plan UUID and digest are unique. The receipt contains exact asset IDs, actor/library, time, reviewed audience/state, database identity, backup fingerprint and review references. Receipt, audit and effects commit together; any failure rolls everything back. No phone, password, session token, raw key, media path or media hash is included. |

Assigning assets makes them available to the library's existing approved audience,
including its already authorized original readers. `originals_granted=false` means
**no new original permission**, not that the audience has none.

The new additive migration is `b6e3f9a5c721` after `a5d2e8f4b610`. It creates only
`access_provisioning_receipts`. The explicit runtime adapter now requires this
revision and table, so an older database fails closed until separately migrated.
No automatic migration or downgrade was added. The original low-level bootstrap
helper remains for synthetic fixtures; direct database administrators remain trusted
and can bypass any application workflow with their existing filesystem authority.

## Verification

- **180 Python security tests passed**, including 18 new apply tests and the existing
  11 read-only plan tests. No skips or expected failures.
- **14 Chromium UI/ASGI checks passed** against the new migrated schema.
- Inventory stays **152 method/path entries: 23 active, 97 retired, 32 standalone**.
- Tests cover unchanged review files; mismatched/replaced targets and backups;
  exact digest/reference requirements; password fallback and hashing outside the
  lock; expiry after prompting and backup scans; audience, asset and unrelated changes; concurrent
  application; writer exclusion in rollback-journal and WAL modes; partial-batch,
  receipt and bootstrap-audit rollback; durable replay rejection even after a mapping
  is removed; and restoration to a separate synthetic file.

Evidence: [Python suite](evidence/provisioning-apply-slice15/python-tests.txt),
[browser result](evidence/provisioning-apply-slice15/browser-result.json), and
[inventory](evidence/provisioning-apply-slice15/inventory.txt).

Browser evidence retains the previous limitation: Fetch Metadata is modeled from
request frames in the pipe/ASGI harness. Real network header emission, TLS/proxy
behavior, CORP and Windows/mobile deployment remain unverified. The old backend
suite was not run; it still depends on retired startup/anonymous interfaces and
potential model-loading fixtures. Source inventory is not proof of authorization.
The historical denial ledger still reports 84/84 failed requirements in retired
implementations; this slice does not repair or remount those handlers.

## Recovery limitation and next slice

Receipts prevent replay within the current database history. **Restoring a pre-apply
backup also removes later receipts.** Device/inode binding rejects reuse of the old
in-process review against a separately restored file, but a new authorized review
can validate an otherwise still-fresh old plan against restored content. Local file
identities are not persistent host identities and can be reused by the filesystem.
Database administrators and filesystem writers remain trusted. There is no claim
of replay protection across rollback, malicious administrator writes or backup
clones. A recovery procedure must invalidate outstanding plans and restored
sessions before reopening access; simply restoring and restarting is insufficient.

Next: review and implement the offline recovery contract with synthetic restoration,
explicit invalidation of pre-restore plans/sessions and handling of admission/KDF
state. Then package the reviewed provisioning/recovery services in an explicit
operator tool with protected input, redacted failures and target/backup review.
Live use still requires separately authorized host backup/restore and migration
rehearsal, exact runtime identity, TLS/proxy isolation and web/device acceptance.
Legacy search, albums, curation, uploads, destructive/jobs and voice endpoints stay
closed; independently exposed model/diagnostic services remain a separate gap.

## Local checkpoint and changed files

Branch: `codex/mobile-access-foundation`. Continuation parent:
`d5f531ebcee85cb5a1ed40093f92e046f914b66b`; original base:
`932263504ac5fcc3ed178e951991619d8ee87049`. This slice is committed locally only.
The original backend and mobile checkout remain clean at their recorded heads in
the [earlier handoff](FOUNDATION_HANDOFF_2026-09-09.md). No push or merge occurred.

- [backend/app/access/metadata.py](../../backend/app/access/metadata.py)
- [backend/app/access/provisioning.py](../../backend/app/access/provisioning.py)
- [backend/app/access/provisioning_apply.py](../../backend/app/access/provisioning_apply.py)
- [backend/app/access/runtime.py](../../backend/app/access/runtime.py)
- [backend/migrations/versions/b6e3f9a5c721_offline_receipts.py](../../backend/migrations/versions/b6e3f9a5c721_offline_receipts.py)
- [docs/security/FOUNDATION_HANDOFF_2026-09-09.md](../../docs/security/FOUNDATION_HANDOFF_2026-09-09.md)
- [docs/security/OFFLINE_PROVISIONING_APPLY.md](../../docs/security/OFFLINE_PROVISIONING_APPLY.md)
- [docs/security/OFFLINE_PROVISIONING_PLANS.md](../../docs/security/OFFLINE_PROVISIONING_PLANS.md)
- [docs/security/evidence/provisioning-apply-slice15/browser-result.json](../../docs/security/evidence/provisioning-apply-slice15/browser-result.json)
- [docs/security/evidence/provisioning-apply-slice15/inventory.txt](../../docs/security/evidence/provisioning-apply-slice15/inventory.txt)
- [docs/security/evidence/provisioning-apply-slice15/python-tests.txt](../../docs/security/evidence/provisioning-apply-slice15/python-tests.txt)
- [tests/security/test_legacy_read_migration.py](../../tests/security/test_legacy_read_migration.py)
- [tests/security/test_orm_migrations.py](../../tests/security/test_orm_migrations.py)
- [tests/security/test_provisioning_apply.py](../../tests/security/test_provisioning_apply.py)
