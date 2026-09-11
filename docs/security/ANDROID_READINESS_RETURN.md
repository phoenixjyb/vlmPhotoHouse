# Return to Android — backend readiness, 2026-09-11

**First-owner recovery and selective reopening verified locally. Protected-backend
rollout and real-phone credentials remain NO-GO until operational gates are met.**

Implementation: `5103abdd0861c2dbb7553d6edeccddbb170deed7`, branch
`codex/backend-android-readiness`, worktree `_worktrees/backend-android-readiness`
under the PhotoHouse workspace. Parent checkpoint:
`75b702f17a3e460a632d580e8ee8ea12dba0d47f`. Local commits only; no push or merge.

## Backend outcome

[Owner recovery](OWNER_RECOVERY.md) adds sealed planning, backup review and explicit
application for one recorded bootstrap owner and one library in a fully quarantined
database. The operator enters a fresh password through protected prompts; reuse of
the restored password is refused. Application revalidates the entire snapshot,
identities and time window after password work, then commits changes/audit/receipt
atomically. Only the selected account/library opens, every other membership is
revoked, every original grant is removed, and old sessions/invitations remain invalid.

The [migration-candidate workflow](DATABASE_PREPARATION.md) remains copy-only and
closed by default. Empty/pre-access databases use reviewed new-owner provisioning.
Recovery does not bulk-reactivate old family accounts: other existing disabled users,
other libraries, lost post-backup history and service cutover remain separate work.
A recovered owner can issue a fresh phone-bound invitation to a new account through
the existing app. No HTTP/source pin/schema change is required for Android.

## Backend evidence

- **277 synthetic security tests pass**, including 15 new first-owner recovery tests.
  Protected prompt/fallback/password reuse, stale state after hashing, expiry,
  wrong owner, backup/identity mismatch, revision overflow, concurrent application,
  receipt/audit/entropy rollback and old-plan invalidation are covered.
- Actual in-process ASGI permits the freshly logged-in owner's selected gallery and
  captions; other-library, original Range and old-token thumbnail requests are
  denied before media opens. Protected-resource denial remains 401 under the frozen
  contract; the retired-route boundary returns 403. Fresh-phone invitation succeeds;
  old/consumed invitations and restored credentials remain denied.
- Inventory completeness passes: **152 entries** (23 active, 97 retired, 32 standalone).
  The historical unsafe-handler ledger remains 84/84 failed denial requirements;
  it was not rerun or relabeled. Inventory is not authorization.
- Immutable **53-file source package**, source commit above, SHA-256
  `bcb7767f9493084c0a1b9c6bf0f9401f2d9c20b4998291a99be25ba0d287ebe1`.
  Manifest hashes and extracted smoke pass: seven ASGI checks, nine operator
  commands and eight preparation invocations, including owner provisioning ->
  backup -> quarantined candidate -> reviewed owner recovery -> durable receipt.
  Source/locks/manifest only; no media, database, wheel or credential bundle.
- The existing exact **21-package test profile** passes the offline Mac environment
  probe. CPU runtime/test locks remain unchanged, including Starlette 1.3.1. Windows
  execution and fresh advisory scanning were not performed. HTTPX's test-only
  deprecation warning remains. All ten Android API source hashes remain unchanged.

[Structured evidence](evidence/android-readiness/owner-recovery-validation.json).
No live host/database/media, service, model, credential, port, deployment or backend
mobile-file edit occurred. DNS/certificate preparation remains a separate earlier
infrastructure step; it does not establish an approved served origin or phone access.

## Android coordination and evidence

The user authorized a message to the existing **Implement Android fixture app** task.
It was sent, that task became active, and it completed `PH-ANDROID-PIPELINE-READINESS-02`
at `ad6b9d9e079383c7e062fe4ba8138117022dc0e3`, branch
`codex/android-pipeline-readiness-02`, sibling worktree
`mobileAppForPhotoHouse-android-readiness`. Its checked-in return and JSON were read.

Android reports **62 directly compiled JVM tests passed**, including nine new checks
for admission, unavailable libraries, session denial, cancellation-resistant late
thumbnails and unset origin. Production sources were unchanged; no new APK/device
claim is made. Its current app already includes original/video/UI work beyond the
historical repin checkout. Keep the first synthetic audience's originals disabled.
The frozen API pin remains `87a60b475b37b1d6873cd977bcb6e7254472da7e` with 12
operations, 38 stored cases and eight checksummed files. Canned JVM/fixture results
are separate from actual backend authorization/TLS evidence.

The Android return reported two replay blockers: unavailable cached wheels and the
shared replay generator's Pillow import, absent from the CPU test lock. The coordinator
verified an existing exact 21-package environment and sent its read-only interpreter
path privately. A bounded follow-up was sent authorizing a fixed synthetic JPEG in
mobile test tooling, preserving the exact strict backend pin, every frozen response
and all contract files, without installing Pillow or adding a runtime dependency.
That follow-up completed at `5773ec27db19012dd5d6de3d2717b2d781e6d664`: its return
and evidence report 38 actual in-process cases passing with every frozen response
unchanged, plus 12 verifier regressions. The earlier failed cache attempt remains
historical evidence. No new Kotlin/TLS, APK or device result is claimed.

The user then requested Android completion; `PH-ANDROID-MVP-COMPLETION-01` was sent
to close demonstrated local MVP gaps and produce a requirement/source/test mapping.
Completion of that new task is not claimed here. The [backend merge review](MERGE_READINESS.md)
finds fast-forward Git compatibility but retains launch/upgrade and remote-review gates.
These messages do not authorize deployment or phone installation.

## Remaining pipeline sequence

1. The exact pinned 38-case replay under the CPU test lock is complete. Finish the
   Android MVP completion handoff and backend launch/upgrade integration review.
2. Design/rehearse explicit service selection and rollback on synthetic local
   artifacts. Never switch back to an old access-enabled archive as a casual rollback.
3. Separately review Windows CPU execution, host patch/ACL/reparse behavior, service
   identity, private synthetic DB/media/previews, trusted served HTTPS and certificate
   reload, and isolation from legacy/standalone listeners/file shares.
4. Provision an approved synthetic owner/library, manually deliver a phone-bound
   invitation, then verify Android registration -> logout -> login -> gallery/detail/
   captions/thumbnail, with invalid invitation, foreign library and revocation denial.
5. Authorize exact APK configuration/installation and real-phone/outside-home routing
   acceptance separately. DNS, certificate issuance and an APK file do not prove it.

Other restored-account recovery, WAL/large database behavior, Windows crash durability
and production-scale performance remain unverified. Search, albums, uploads, voice
and operational routes remain closed. The [staging decision](ANDROID_STAGING_DECISION.json)
and [proposal](ANDROID_STAGING_PROPOSAL.md) retain these delivery gates.

## Changed files in this slice

- `backend/app/access/owner_recovery.py`
- `scripts/provision_access.py`
- `scripts/build_staging_package.py`
- `tests/security/test_owner_recovery.py`
- `tests/security/package_smoke.py`
- `docs/security/OWNER_RECOVERY.md`
- `docs/security/OPERATOR_TOOL.md`
- `docs/security/DATABASE_PREPARATION.md`
- `docs/security/OFFLINE_RECOVERY.md`
- `docs/security/ANDROID_READINESS_RETURN.md`
- `docs/security/ANDROID_STAGING_DECISION.json`
- `docs/security/ANDROID_STAGING_PROPOSAL.md`
- `docs/security/STAGING_LAUNCHER.md`
- `docs/security/evidence/android-readiness/owner-recovery-validation.json`
