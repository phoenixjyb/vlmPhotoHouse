# Return to Android — backend readiness, 2026-09-11

**CPU dependency/source-package slice verified locally. Protected-backend deployment
and real-phone credentials remain NO-GO until the remaining gates are met.**

- Implementation: `ce91cf68cd53dd5692042ee79ed7948f2231a50d`, branch
  `codex/backend-android-readiness`. The [CPU environment](CPU_ENVIRONMENT.md)
  contains 18 hash-locked runtime packages and a separate 21-package test profile.
  Starlette 1.0.0 had published advisories; the candidate uses patched 1.3.1.
- **247 synthetic security tests passed**, including seven environment/launcher
  checks. Inventory remains **152 entries**: 23 active, 97 retired, 32 standalone.
  The inventory does not make retired/standalone handlers safe.
- A fresh Mac CPython 3.12.12 environment passes package compatibility, exact
  dependency inventory, scrypt known-answer/application-cost, in-memory SQLite FK,
  and TLS-context checks. The Windows target is correctly refused on the Mac.
  All 18 Windows x64 CPython 3.12 wheels downloaded with required hash verification;
  **Windows execution was not performed**.
- PyPI's version-specific vulnerability metadata was checked for all 21 candidate
  packages and reported no advisories at this checkpoint. This is not an exhaustive
  audit or a guarantee against future advisories. The old baseline's findings are
  retained in the [validation receipt](evidence/android-readiness/cpu-environment-validation.json).
- The immutable **51-file source package** passes manifest hash checks, the offline
  environment probe, seven in-process ASGI checks, three database-preparation
  commands and three operator commands. ZIP SHA-256:
  `2e341587736410e96e4aafd42b26cc61630698bf63220b05bdb252b8288e2ab3`.
  It contains source/locks/manifest only; no wheels, database, media or credentials.
- Android's frozen contract validates: 12 operations, 38 fixture cases, eight
  checksummed files; eight verifier regression tests pass. All ten backend source hashes still match its pin
  `87a60b475b37b1d6873cd977bcb6e7254472da7e`. No source/schema repin is requested.
  The complete 38-case ASGI/Kotlin/device replay was not repeated in this slice;
  final deployment acceptance must use the selected dependency lock as well as source.
- The test-only HTTPX TestClient emits Starlette's deprecation warning; all tests
  pass. Migrating that harness to httpx2 is deferred and not a serving dependency.

No mobile repository, live database/media, Windows/Mac mini runtime, model, service,
router, credentials or listener was changed by this **CPU development slice**.
No push or merge occurred. The earlier separately authorized DNS/certificate setup
is infrastructure preparation; private details remain outside the repository and
are not an approved protected-backend URL or phone-access claim.

**Next local implementation:** explicit existing-database migration apply/recovery,
with exact target/backup identities, stale-state refusal, rollback and restored-access
quarantine tests. Current [database preparation](DATABASE_PREPARATION.md) only creates
new empty databases, creates new backups and rehearses migration in memory. It refuses
WAL/sidecars and inputs over 64 MiB; existing-database migration/restore are not implemented.

**Then:** review Windows execution of the CPU lock, host patch/ACL/reparse behavior,
synthetic staging deployment, protected TLS serving and certificate reload lifecycle,
legacy/standalone ingress isolation, explicit owner/library provisioning and physical-phone
acceptance. Schema stays `b6e3f9a5c721`; default app stays closed. Search, albums, voice,
upload and operational APIs remain closed, not newly implemented secure features.

The [staging decision](ANDROID_STAGING_DECISION.json) and
[proposal](ANDROID_STAGING_PROPOSAL.md) preserve those gates. Earlier handoff-file
queueing to Android was not a sent message, task wake-up or acknowledged receipt;
this slice does not claim a new notification. Preserve all receiving worktrees.

## Changed files in this CPU slice

- `backend/requirements-access.in`
- `backend/requirements-access.lock`
- `backend/requirements-access-test.in`
- `backend/requirements-access-test.lock`
- `backend/requirements-security-test.txt`
- `scripts/check_access_environment.py`
- `scripts/build_staging_package.py`
- `tests/security/test_access_environment.py`
- `docs/security/CPU_ENVIRONMENT.md`
- `docs/security/STAGING_LAUNCHER.md`
- `docs/security/ANDROID_READINESS_RETURN.md`
- `docs/security/ANDROID_STAGING_PROPOSAL.md`
- `docs/security/ANDROID_STAGING_DECISION.json`
- `docs/security/evidence/android-readiness/cpu-environment-validation.json`
