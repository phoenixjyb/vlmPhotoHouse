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
