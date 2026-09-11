# Return to Android — backend readiness, 2026-09-11

**Quarantined migration candidates verified locally. Protected-backend deployment
and real-phone credentials remain NO-GO until the remaining gates are met.**

Implementation: `4d6c4c5d982212b403d04845e1fd8df0c9e61556`, branch
`codex/backend-android-readiness`, worktree `_worktrees/backend-android-readiness`
under the PhotoHouse workspace. Parent checkpoint:
`55266b51aca7d1393d27019fd4c1bc5951a4035a`. No push or merge occurred.

## What this slice implements

[Database preparation](DATABASE_PREPARATION.md) adds `migrate-candidate`: select an
explicit source, separate matching backup and reviewed snapshot digest, record
operator/quiescence review references, migrate a memory copy and write a new private
candidate. Existing source/backup files remain untouched. Pre-access databases gain
no accounts, memberships or photo mappings. Existing accounts/libraries are closed,
sessions revoked, unused invitations cancelled and the admission/plan key rotated.
This shares quarantine logic with [offline recovery](OFFLINE_RECOVERY.md).

A fresh unsigned preparation receipt records provenance. It is not authentication,
proof that workers stopped, or a sealed approval. No in-place migration, source-file
replacement, service cutover, owner recovery or library reopening is implemented.
An old archive retains its credentials; serving it or returning to it is not safe
rollback. The legacy service can bypass the protected app's access checks.

## Verified evidence

- **262 synthetic security tests pass**, including 15 new candidate tests and all
  18 existing recovery tests. Coverage includes pre-access migration, input byte
  preservation, stale/mismatched backups, hardlink/no-overwrite refusal, WAL/sidecar
  refusal, failed migration/entropy/receipt/copy, fresh keys, rollback and concurrent
  writer commit exclusion. Receipt-trigger attempts to reopen access or restore an
  old key are refused before output.
- The candidate's actual in-process ASGI app rejects old cookies/bearer tokens for
  session/gallery/original Range/thumbnail/face-crop requests before opening media.
  Old passwords, invitation codes and sealed review plans also fail.
- Inventory completeness passes: **152 entries**, 23 active, 97 retired and 32
  standalone. This inventory does not authorize or secure retired/standalone routes.
  The historical unsafe-handler ledger remains 84/84 failed denial requirements;
  it was not rerun or relabeled as passing in this slice.
- The immutable **51-file source package** passes manifest SHA-256 verification,
  the 18-package Mac runtime probe, seven in-process ASGI checks, five preparation
  command invocations (four command types) and three operator commands. ZIP SHA-256:
  `ade79983129bd6b338df9b1b4c5d0255dc1463512d04fc6665eb41d90e1fae4c`.
  It contains source/locks/manifest only; no database, media or credentials.
- Android's frozen contract validates: 12 operations, 38 fixture cases, eight
  checksummed files; eight verifier regression tests pass. All ten backend source
  hashes still match pin `87a60b475b37b1d6873cd977bcb6e7254472da7e`.
  **No API/schema repin is requested.** The 38-case ASGI/Kotlin/device replay was
  not repeated; final acceptance must use the selected source and dependency lock.
- The [CPU lock](CPU_ENVIRONMENT.md) remains unchanged (18 runtime/21 test packages,
  Starlette 1.3.1). Windows wheel availability/hash verification is earlier evidence;
  no Windows execution or new advisory scan occurred. HTTPX TestClient's known
  deprecation warning remains test-only.

Machine-readable [validation receipt](evidence/android-readiness/migration-candidate-validation.json).
Only synthetic databases and in-process clients were used. No mobile repository,
live database/media, Windows/Mac mini, model, service, router, credential or listener
was changed. Earlier authorized DNS/certificate preparation is separate from
protected-backend deployment. No new Android task notification is claimed.

## Next implementation and remaining gates

Implement reviewed **owner credential recovery and selective library reopening**:
bind an exact quarantined candidate and matching backup; require protected new
password input; review the restored owner/operator identity and reconcile membership
revocations and original grants; enable only the explicitly approved account/library.
Keep all other accounts closed and old sessions/invitations invalid. Prove rollback,
replay/stale-state refusal and denial for the unreviewed audience with synthetic data.
Post-backup history cannot be reconstructed from the archive itself.

Then design reviewed service cutover/rollback, execute the CPU lock on Windows,
verify host patch/ACL/reparse behavior and legacy/standalone ingress isolation,
serve a synthetic staging instance over protected HTTPS with certificate reload,
and complete authorized physical-phone acceptance. WAL, databases over 64 MiB,
Windows filesystem/crash durability and production-size performance are unverified.
Search, albums, voice, uploads and operational routes remain closed.

The [staging decision](ANDROID_STAGING_DECISION.json) and
[proposal](ANDROID_STAGING_PROPOSAL.md) retain these delivery gates.

## Changed files in this slice

- `backend/app/access/recovery.py`
- `scripts/prepare_access_database.py`
- `tests/security/test_migration_candidate.py`
- `tests/security/package_smoke.py`
- `docs/security/DATABASE_PREPARATION.md`
- `docs/security/OFFLINE_RECOVERY.md`
- `docs/security/ANDROID_READINESS_RETURN.md`
- `docs/security/ANDROID_STAGING_PROPOSAL.md`
- `docs/security/ANDROID_STAGING_DECISION.json`
- `docs/security/STAGING_LAUNCHER.md`
- `docs/security/evidence/android-readiness/migration-candidate-validation.json`
