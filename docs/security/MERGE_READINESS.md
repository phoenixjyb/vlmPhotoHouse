# Authorized GitHub integration — 2026-09-12

The user authorized publishing and merging the accumulated backend work before
further development. Candidate branch is `codex/backend-home-tv-feed`, starting
at `2383162249b5bfcb79cf391ac87a64d39c58d69a` (64 commits absent from GitHub
master). GitHub master `b886aca9344c8f9e838f28e2a1b380caad0ec40e` contributed nine
commits absent from the candidate. A normal merge applied without conflicts;
no history was rewritten and no other worktree was changed. The caption policy,
tasks and legacy viewer JS/HTML/CSS match master's bytes after integration.

Validation of the combined source:

- 433 synthetic security tests passed in 97.965 seconds, no failures/errors/skips.
- 18 synthetic caption-policy tests passed.
- 14 Chromium protected-UI checks passed through a pipe to in-process ASGI, with
  synthetic SQLite and external network requests denied. The existing CPU
  interpreter was substituted into the test runner in memory; source was unchanged.
- The 162 method/path inventory entries are complete. Known retired/standalone
  authorization gaps remain recorded; route coverage is not security completion.
- Outgoing history secret scan reviewed all 11 findings: each was verified against
  a committed source checksum, an existing Git commit or an Alembic revision.
  No credential was found by that scan. This is bounded scanner evidence.
- `git diff --check` passed. No repository workflow exists; hosted PR checks are
  inspected separately before merge. No ML/GPU/runtime suite or device test ran.

Compatibility: `app.main:app` stays closed by default; protected setup requires the
explicit database/migration/provisioning/launch workflow. Retired launchers refuse
before intake/model startup; do not point public ingress at `legacy_main` to
restore old behavior. Legacy viewer and caption changes are retained in source,
not automatically exposed through the protected UI. The anonymous LAN TV contract
remains separate from authenticated phone/library access. The protected phone
search service remains unmounted. Full-library preparation is implemented but
has not run on real media; large/long media profiles and device acceptance remain
open. See [full coverage](HOME_FULL_COVERAGE_RETURN.md) and
[protected upgrade](PROTECTED_UPGRADE.md).

This integration changes GitHub source only. It does not update Windows releases,
activate the disabled candidate, restart services, pause captions or alter media,
access rules, credentials or network settings. Historical authorization/status
notes below are retained as dated evidence, not current approval requirements.

# Current review update — 2026-09-11

Launch integration now retires six old combined launch/coordinator scripts before
cleanup, intake, model loading or server startup. See [protected upgrade](PROTECTED_UPGRADE.md).
Native Windows PowerShell parsed and exercised all five PowerShell stubs with
former operational flags; all refused. The shell stub refused with external
executables unavailable. The local security suite passed: 277 tests in 34.102 s.
The package allowlist now also includes the protected upgrade guide; its three
focused archive tests pass.

GitHub visibility was restored per command by omitting stale ambient GH_TOKEN and
GITHUB_TOKEN overrides; no credential was changed. No open PR existed at inspection.
GitHub master is now `b886aca9344c8f9e838f28e2a1b380caad0ec40e`, unprotected,
with nine commits absent from this candidate, including caption and legacy viewer
work. The previous fast-forward assessment below is historical. Preserve those
changes during integration; do not force-update master or replace its viewer work.
No push or merge has occurred in this follow-up.

The user assigned backend launch/review and synthetic Windows staging here, with
Android acceptance owned by its separate task. Real captioning remains on its
existing release. [Windows synthetic staging](WINDOWS_STAGING_RETURN.md) is now verified separately.

---

# Backend merge-readiness review — 2026-09-11

**Git-compatible; merge approval withheld pending integration review.**
This assessment does not push, merge, deploy or change service configuration.

## Exact identities

- Candidate: `codex/backend-android-readiness` at
  `ceff3ab7ea89020b8909eff988177fa65a196179`, clean when reviewed.
- GitHub default branch, verified with remote symbolic HEAD: **master**.
- Remote HEAD and local `origin/master` both:
  `932263504ac5fcc3ed178e951991619d8ee87049`.
- Merge base is that exact master commit. Candidate is 32 commits ahead, zero behind;
  fast-forward integration is possible with no competing master changes at this check.
- Full delta: 127 files, 17,113 inserted and 2,201 removed lines, including the earlier
  access foundation. This is substantially more than the last owner-recovery slice.

GitHub PR/check inspection using the configured CLI failed with HTTP 401 (bad
credentials). PR existence, required checks, branch protection and review approval
were therefore not verified. No credential or remote setting was changed. There is
no `.github/workflows` directory in this candidate; local tests are not remote CI.

## Concrete integration concern

`scripts/start-dev-multiproc.ps1:449` still starts `uvicorn app.main:app`. The new
`backend/app/main.py` intentionally starts without database/media runtime or workers.
A fresh synthetic in-process check of that exact default app, with external I/O
denied, returned:

| Request | Result |
| --- | --- |
| `/health` | 403 |
| `/auth/session` | 503 |
| `/ui` | 200, protected UI shell only |

This is the intended fail-closed boundary, not a new authorization bug. However,
updating the existing checkout and using its old launcher no longer reproduces the
current legacy service. The full legacy application remains in `legacy_main.py`;
switching an externally reachable launcher back to it would bypass this protection
and is not an acceptable compatibility fix.

Review the explicit protected-launch path, legacy/internal worker ownership,
migration/provisioning prerequisites, health checks and rollback behavior before
approving this default-entry-point change for master. A source merge alone does not
deploy, but the repository must communicate and test what its normal launch/update
path does. Operational Windows/HTTPS/phone verification remains separately gated.

## Evidence already available

The candidate checkpoint retains 277 passing synthetic security tests and a verified
53-file source package. These cover the protected app and offline tooling; the old
ML/runtime backend suite was not run on the Mac. Inventory covers 152 entries, with
97 retired and 32 standalone routes still requiring exposure isolation. The unsafe
historical denial ledger is not replaced by the passing new-app tests.

Android completed the locked-profile replay follow-up at
`5773ec27db19012dd5d6de3d2717b2d781e6d664`, branch
`codex/android-pipeline-readiness-02`. Its return/evidence was read: 38 actual
in-process ASGI cases match every frozen response under the exact 21-package CPU
test profile; 12 verifier regressions pass. Its preceding compiled JVM result is
62 passing tests. No wire/source pin was relaxed, no new APK/device evidence was
claimed. The existing API pin remains `87a60b475b37b1d6873cd977bcb6e7254472da7e`.

## Next bounded work

1. Complete a local launch/upgrade compatibility review and synthetic regression
   checks. Keep the protected default closed; do not restore implicit legacy access.
   Prepare a reviewable PR description covering the entire 32-commit foundation,
   compatibility impact and verification tiers.
2. Restore authorized GitHub review visibility and inspect PR/check/protection state.
   Publication/merge still need explicit user authority; the user's question was a
   readiness question and did not override the earlier no-push/no-merge instruction.
3. Android task `PH-ANDROID-MVP-COMPLETION-01` was sent to finish demonstrated local
   gaps and produce a requirement/source/test mapping for the browsing MVP. Preserve
   historical evidence while updating current entry documents. Deferred search,
   albums, voice, upload/offline/export and store distribution are outside this MVP.
4. After source review, complete separately authorized synthetic Windows deployment,
   trusted served HTTPS/certificate lifecycle/ingress, exact synthetic audience and
   installed-phone acceptance. A DNS record, certificate, merge or APK file proves
   none of those remaining stages by itself.
