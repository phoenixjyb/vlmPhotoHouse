# Validation receipt — 2026-09-16

## 2.0.0-candidate.3 — reissue after the owner-tools source slice

Source baseline: `37979480415ba50180804a9c8e2032ff826009ed`.
Branch: `master`, local and unpushed.

This reissue moves the pinned source closure and the pack version. Closing the two
owner-only people gaps in the protected WebUI edits `backend/app/access/people.py`
(a `named` filter on `/admin/people` and a new `GET /admin/faces` worklist) and
`backend/app/access/boundary.py` (the closed-boundary allowlist entry that admits
that route). Both sit inside the pinned `backend/app/**` closure.

Unlike candidate.2, this slice **does add a route**, and that is worth stating
plainly rather than filing under "operator tooling only". The route is nevertheless
outside the wire surface this pack documents: the 60 captured ASGI exchanges cover
28 distinct paths and none of them is under `/admin/`. The route is owner-only,
default-denied for every other account, and requires the pre-existing
`library.people.manage` capability, so it grants no account a capability it did not
already hold.

**Wire neutrality was measured, not assumed.** `cases.json` was regenerated from a
live capture against the new source and differs from the candidate.2 file by exactly
one line — the version string. Every one of the 60 exchanges, including status codes,
selected headers and normalized bodies, is identical. A client already tested against
candidate.2 needs no rework.

```sh
PYTHONPATH=tests/security:backend python -m unittest \
  test_protected_native_contract test_access_foundation test_access_transport \
  test_library_reads test_family_stories.FamilyStoryTests \
  test_protected_photo_delivery test_closed_application
```

**134 tests passed in 17.630 seconds**, no skips — the same runner count as
candidate.2, including seven contract tests and the complete replay comparison of
60 captured ASGI exchanges. Synthetic and in-process; no network listener.

`python3 scripts/verify_protected_native_contract.py`:
`PASS 2.0.0-candidate.3: 60 cases; 99 source hashes; 7 payload hashes; profile
defaults off`.

Closure count is unchanged at 99: two changed (`boundary.py`, `people.py`), none added
and none removed. All 99 source hashes were independently compared with
`git show 3797948:<path>` while building the manifest — 0 worktree mismatches and
0 git-blob mismatches. The database migration head remains `d8e5b2f7a904` and
`backend/app/access/library.py` remains byte-identical to the frozen v1 backend,
SHA-256 `5c280e0047771a43274615b77617f896ef2ef075b4fa3f926ae05bf8c49372fe`.

The whole `tests/security` tree was run on both sides to attribute the failure set
rather than just count it: **783 passed / 3 failed / 7 skipped** on this source versus
**779 passed / 3 failed / 7 skipped** at `f61028e` in a clean control worktree. The
three failing node ids are identical on both sides (`/bin/ps` process inspection is
unavailable in this sandbox, and one pre-existing full-suite order dependence), and
the 4 extra passes are this slice's new people-management tests. The pack reissue
itself adds no test outcome.

## 2.0.0-candidate.2 — reissue after the ownership-repair source slice

Source baseline: `3d8cc8f9f5563c3d3c72f20869e4a8cdf4d38642`.
Branch: `codex/suppressed-person-ownership-repair`.

This reissue moves only the pinned source closure and the pack version. The
offline suppressed-person ownership repair edits
`backend/app/access/provisioning.py` and `backend/app/access/provisioning_apply.py`
and adds `backend/app/access/ownership_repair.py`, all of which sit inside the
pinned `backend/app/**` closure. It adds no route, migration, serializer or
server response field, so the pack's wire surface is unchanged.

```sh
PYTHONPATH=tests/security:backend python -m unittest \
  test_protected_native_contract test_access_foundation test_access_transport \
  test_library_reads test_family_stories.FamilyStoryTests \
  test_protected_photo_delivery test_closed_application
```

**134 tests passed in 17.967 seconds**, no skips — the same runner count as
candidate.1, including seven contract tests and the complete replay comparison of
60 captured ASGI exchanges. Synthetic and in-process; no network listener.

`python3 scripts/verify_protected_native_contract.py`:
`PASS 2.0.0-candidate.2: 60 cases; 99 source hashes; 7 payload hashes; profile
defaults off`.

**Wire neutrality was measured, not assumed.** `cases.json` was regenerated from a
live capture against the new source and differs from the candidate.1 file by
exactly one line — the version string. Every one of the 60 exchanges, including
status codes, selected headers and normalized bodies, is identical. A client
already tested against candidate.1 needs no rework.

Closure moved 98 → 99: one added (`backend/app/access/ownership_repair.py`), two
changed (`provisioning.py`, `provisioning_apply.py`), none removed. The database
migration head remains `d8e5b2f7a904` and `backend/app/access/library.py` remains
byte-identical to the frozen v1 backend, SHA-256
`5c280e0047771a43274615b77617f896ef2ef075b4fa3f926ae05bf8c49372fe`.

The repair's own synthetic suite is 13 tests; the adjacent
access/library/transport/management/face-job/schema batch is 111 tests. Both pass
on this source.

## 2.0.0-candidate.1 — initial pack

Source baseline: `4022a57f56e6b2f976931a20569e15c879871d93`.
Branch: `codex/protected-native-contract-v2`.
Changes are contract documentation, synthetic wire cases, probe, replay tests and
an offline hash verifier. Application/backend source is unchanged.

### Checks

Using the already available disposable Mac test environment (Python 3.13.15,
FastAPI 0.135.2, Starlette 1.3.1, httpx 0.28.1, SQLAlchemy 2.0.52,
Alembic 1.19.2), from repository root:

```sh
PYTHONPATH=tests/security:backend python -m unittest \
  test_protected_native_contract test_access_foundation test_access_transport \
  test_library_reads test_family_stories.FamilyStoryTests \
  test_protected_photo_delivery test_closed_application
```

**134 tests passed in 62.689 seconds**, no skips. This includes seven new contract
tests, a complete replay comparison of **60 captured ASGI exchanges**, and existing
account/admission/library/Stories/photo/closed-application tests. Test discovery
includes inherited library cases; 134 is the runner count, not 134 unique new
scenarios. These tests are synthetic and in-process; no network listener is used.

`python3 scripts/verify_protected_native_contract.py`: passes source and payload
hash closure, case count/IDs/version and off-by-default profile checks. All 98
source hashes were independently compared with `git show <source>:<path>` when
building the manifest. `backend/app/access/library.py` is byte-identical to the
frozen v1 backend; SHA-256:
`5c280e0047771a43274615b77617f896ef2ef075b4fa3f926ae05bf8c49372fe`.

Markdown links/whitespace/fences and staged diff whitespace checked. The first
replay exposed a wall-clock default in synthetic caption data; the probe now
sets deterministic fixture timestamps before calling the unchanged serializer.
The final full-wire comparison passes without masking response date fields.

### Boundaries

The test environment emits a Starlette/httpx deprecation warning; no packages
were installed or upgraded. Windows dependencies/runtime were not inspected.
On-demand JPEG rendering is stubbed in the contract probe; existing protected
photo tests exercise the authorization boundary. This receipt is not Windows
decoder, ACL, device, APK or live-service acceptance.

No production database/media/accounts, GPU/model operations, service changes,
network port exposure, mobile repository edits, push or merge. Android owns its
client verification/adoption. Integration owns configured deployment approval.
The pack remains a candidate requiring explicit coordinator adoption; immutable
commit and manifest digest are supplied in the task handoff after local commit.

No application deployment is needed for this documentation/test slice. Upload,
refresh tokens, native voice/STT and prepared-video access without original
permission are not implemented by this work.
