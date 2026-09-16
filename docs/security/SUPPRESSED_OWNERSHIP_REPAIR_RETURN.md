# Suppressed-person ownership repair — source return

Branch `codex/suppressed-person-ownership-repair`, owned worktree
`_worktrees/suppressed-person-ownership-repair`, based on `97c5d62`, which is also
the pinned backend source of the
[protected native v2 candidate pack](../contracts/protected-native-v2/VALIDATION.md).
All changes in this slice are local and uncommitted at this return. No push, merge,
deployment, service restart, worker control, database write or media access was
performed, and no production database, account, model or asset was read.

The operation itself is documented in [the operator-facing guide](OWNERSHIP_REPAIR.md).
The private pre-repair inventory and the collateral review stay outside repository
publication and are not reproduced here.

## Source changes

- `backend/app/access/ownership_repair.py` (new): bounded offline operation
  `repair_suppressed_person_ownership`. It validates schema revision, foreign-key
  enforcement, rollback-journal mode and stopped writers; requires an active
  approved owner; resolves the affected reference closure and refuses foreign,
  missing or drifted rows; computes a per-person capability delta and refuses any
  selection that would change another identity; seals a SHA-256/HMAC plan state
  including a source fingerprint; and applies the inserts plus audit and receipt
  inside the existing reviewed transaction.
- `backend/app/access/provisioning_apply.py`: registers the operation as an offline
  apply (independent all-writer confirmation, offline restore source), installs an
  insert-only authorizer for the sealed apply, and verifies the repaired
  postcondition plus `PRAGMA foreign_key_check` before commit.
- `backend/app/access/provisioning.py`, `scripts/provision_access.py`: planner and
  `plan-person-repair` CLI wiring with exact request-field validation.
- `docs/security/OWNERSHIP_REPAIR.md` (new), `docs/security/OPERATOR_TOOL.md`.
- `scripts/build_staging_package.py`: adds the new module and guide to the fixed
  staged-file allowlist.
- `tests/security/test_suppressed_ownership_repair.py` (new),
  `tests/security/package_smoke.py` (staged `plan-person-repair` round trip).

## Completed in this return

The interrupted run left the module and the synthetic suite written but unverified.
Four test-side defects were corrected: three calls used the local review helper
without its plan argument, one replay assertion expected a receipt message that the
shared reviewed pre-state check raises earlier (as it already does for the existing
management import), and one assertion expected `PlanRejected` for a wrong migration
revision where the storage adapter already refuses to open the database with
`RuntimeUnavailable`. The orphan-reference case now builds its corrupt row with
foreign keys disabled for that fixture write only, because the enforced schema
cannot otherwise hold a face pointing at a missing asset. Two safety tests were
added for behaviour that had no coverage: refusal when the mapping would unlock a
second identity, and denial of trigger-driven writes outside the reviewed inserts.

## Verification

Disposable macOS arm64 Python 3.13.12 environment, dependency versions installed
from the repository lock pins (FastAPI 0.135.2, Starlette 1.3.1, SQLAlchemy 2.0.52,
Alembic 1.19.2, httpx 0.28.1, Pydantic 2.12.5). Running the suites against
unpinned newest releases instead produced 19 failures in untouched baseline code,
so the lock pins are required for a trustworthy signal.

```sh
PYTHONPATH=tests/security:backend python -m unittest \
  test_suppressed_ownership_repair test_access_foundation test_library_reads \
  test_access_transport test_management_import test_management_migration \
  test_face_job_control test_apply_access_schema
```

**124 tests passed in 17.378 seconds**, including 13 repair tests. The same command
against the clean `protected-native-contract-v2` worktree passes 71 of 71 for the
shared baseline, so no regression is attributable to this slice.

`PYTHONPATH=tests/security:backend python -m unittest test_family_stories.FamilyStoryTests
test_protected_photo_delivery test_closed_application`: **56 tests passed**.

`tests/security/package_smoke.py` run against an extracted root assembled from the
staged-file allowlist printed
`{"package_smoke": "pass", "operator_commands": 19, "listeners_opened": false,
"live_data_accessed": false}`, covering the new staged `plan-person-repair`
round trip. Removing `ownership_repair.py` from that root fails the smoke, so the
allowlist entry is load-bearing.

## Contract drift and remaining gates

The slice edits pinned contract source (`backend/app/access/provisioning.py`,
`provisioning_apply.py`) and adds `backend/app/access/ownership_repair.py`, so the
pack's `backend/app/**` closure moved from 98 to 99 files and two source hashes
changed. The pack was therefore reissued as `2.0.0-candidate.2` by the commit that
follows this one, using the same source-then-pack order as the original
(`4022a57` committed before `97c5d62`). `cases.json` was regenerated from a live
capture against this source and changed by exactly one line — the version string —
so all 60 wire exchanges are provably unchanged and a client already tested
against candidate.1 needs no rework. The reissued pack still reads
`candidate_requires_coordinator_adoption`; adoption itself remains a coordinator
decision rather than a slice-level one.

The operation is source-complete and synthetically verified only. A live apply still
requires the owner's exact-scope decision, a separate maintenance approval, a
verified full backup and rehearsed restore, quiescent writers, a sealed preflight
against the frozen database, public suppression re-checks, and the owner's own
post-repair face assignment and device acceptance. Windows runtime, model, GPU,
SMB/TV audience and physical-device evidence are untouched by this slice.
