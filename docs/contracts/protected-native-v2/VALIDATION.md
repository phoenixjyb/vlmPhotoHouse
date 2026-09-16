# Validation receipt — 2026-09-16

## 2.0.0-candidate.5 — reissue after the member tag-catalog source slice

Source baseline: `2ced43e3063773d4344c04ba8f5de1d415fd4bf7`.
Branch: `master`, local and unpushed.

This reissue moves the pinned source closure and the pack version. Opening the read-only
tag catalog to ordinary library members adds two member-scoped read routes, `GET /tags`
and `GET /tags/{tag_id}/assets`, and — unlike candidates.3 and .4 — it adds a module:
`backend/app/access/tags.py`. The closure therefore moves **99 → 100 files**: one added,
two changed (`backend/app/access/boundary.py` for the two allowlist entries and
`backend/app/main.py` for the router registration), none removed. A coordinator
comparing file lists will see a new name, not only new digests.

Like candidates.3 and .4, this slice adds routes, and both are again **outside the wire
surface this pack documents**. The 60 captured ASGI exchanges cover 28 paths — accounts,
gallery, asset detail, captions, stories, search, members, invitations, upload and
voice — and none of them is `/tags`.

**Wire neutrality was measured, not assumed.** `cases.json` was regenerated from a live
capture against the new source and differs from the candidate.4 file by exactly one
line — the version string. Every one of the 60 exchanges, including status codes,
selected headers and normalized bodies, is identical. A client already tested against
candidate.4 needs no rework.

The two routes are narrower than the retired legacy tag surface they partially answer,
which matters because "read-only" alone would not say so. Both are gated on
`library.read`, so every approved role may read them. The catalog returns only tags
linked to an asset that is active (or status-less) **and** mapped into the selected
library, and each count counts that library's own visible assets — so another library's
tag is neither listed nor countable and no global total is revealed. Neither a tag's
`type` nor a link's `source` (`cap` / `img` / `cap+img` / `manual` / `rule`) is
returned; legacy `/tags` returned both. A tag with no visible asset in the library is
refused as access denied rather than answered empty, so tag existence is never
confirmed to a non-member. The photo list reuses the gallery's library-scoped predicate
and its asset row, so it adds no second asset or media surface. The module contains no
POST, PUT or DELETE at all. Both narrowings are asserted, and both assertions were
mutation-tested (see below).

```sh
PYTHONPATH=tests/security:backend python -m unittest \
  test_protected_native_contract test_access_foundation test_access_transport \
  test_library_reads test_family_stories.FamilyStoryTests \
  test_protected_photo_delivery test_closed_application
```

**134 tests passed in 18.035 seconds**, no skips — the same runner count as candidate.4,
including seven contract tests and the complete replay comparison of 60 captured ASGI
exchanges. Synthetic and in-process; no network listener.

`python3 scripts/verify_protected_native_contract.py`:
`PASS 2.0.0-candidate.5: 60 cases; 100 source hashes; 7 payload hashes; profile
defaults off`.

All 100 source hashes were independently compared with `git show 2ced43e:<path>` while
building the manifest — 0 worktree mismatches and 0 git-blob mismatches. The database
migration head remains `d8e5b2f7a904` and `backend/app/access/library.py` remains
byte-identical to the frozen v1 backend, SHA-256
`5c280e0047771a43274615b77617f896ef2ef075b4fa3f926ae05bf8c49372fe`.

The whole `tests/security` tree was run on both sides with the same runner
(`python -m unittest discover -s tests/security -t tests/security -p 'test_*.py'`) to
attribute the failure set rather than count it: **794 passed / 3 failed / 7 skipped**
(804 collected) on this source versus **788 passed / 3 failed / 7 skipped** (798
collected) at `d477d71` in a clean control worktree. The three failing node ids are
identical on both sides — `test_home_library` native-memory observation (`/bin/ps`
process inspection is unavailable in this sandbox), `test_home_media_profiles`
large-baseline-JPEG subsampling (host resource observation), and one pre-existing
full-suite order dependence in `test_suppressed_ownership_repair` — and the 6 extra
collected tests, all passing, are exactly this slice's six new tag-catalog tests. The
pack reissue itself adds no test outcome. Elapsed times are not compared: this host
carried unrelated load (load average 9–21) throughout both runs.

The protected-WebUI browser suite is **48 checkpoints, exit 0** (was 47), one of them
new: a plain member — not the owner — opens the tag panel, sees exactly the two tags
that carry visible assets in this library while a foreign-library-only tag and a
deleted-asset-only tag stay absent, opens one tag and sees its two photos, finds one
input and one form and no tag *control* in the panel, and sees every owner panel still
hidden. Counting the visible tags is the leak detector: an over-broad catalog renders
more than two.

**Both narrowings were mutation-tested, so the tests are known to be able to fail.**
Removing the active-asset predicate from the catalog's visible-asset CTE let a
foreign-library tag and a deleted-asset-only tag surface and failed three tests.
Removing the access-denied precondition on `/tags/{tag_id}/assets` let a non-member
probe a tag by id and failed
`test_no_foreign_deleted_or_linkless_tag_is_listed_or_probeable_by_id` with
`200 != 401`.

Deploy gap — **this slice exposes a gap in the payload allowlist itself.** Against the
deployed `4022a57`, the allowlisted changed set moves 11 → **12 files (10 M, 2 A)**,
because `backend/app/main.py` now carries the router registration. Separately,
`backend/app/access/tags.py` was **not** in the allowlist: the bundle built at this
source held 87 files including `main.py` (which imports `app.access.tags`) and
`boundary.py` (which imports `.tags`) but **not** `tags.py` itself — measured, not
inferred. That payload would have failed at import on the Windows host. The allowlist is
an explicit closed list in `scripts/build_staging_package.py`, so this is not
self-healing; it was repaired here by adding the module (bundle now 88 files), and the
relative-import closure inside `backend/app/**` was re-checked at 0 unresolved imports.
The correct staging set is therefore **13 files (10 M, 3 A)**, and the host staging
script's changed-file assertion must list all 13. The pack itself is not in the payload
allowlist, so this reissue never moves the gap.

## 2.0.0-candidate.4 — reissue after the member people-directory source slice

Source baseline: `99078f1d127d5577b2548cc202dc75593ce77ab3`.
Branch: `master`, local and unpushed.

This reissue moves the pinned source closure and the pack version. Opening the people
directory to ordinary library members adds one member-scoped read route, `GET /people`,
so `backend/app/access/people.py` (the route, the service method and a narrower
presenter) and `backend/app/access/boundary.py` (the closed-boundary allowlist entry
that admits it) both changed again.

Like candidate.3, this slice adds a route, and the route is again outside the wire
surface this pack documents. The 60 captured ASGI exchanges cover 28 paths — accounts,
gallery, asset detail, captions, stories, search, members, invitations, upload and
voice — and none of them is `/people`, `/admin/*` or `/faces/*`. Member-visible people
browsing is a protected-WebUI capability, not part of the native client profile.

**Wire neutrality was measured, not assumed.** `cases.json` was regenerated from a live
capture against the new source and differs from the candidate.3 file by exactly one
line — the version string. Every one of the 60 exchanges, including status codes,
selected headers and normalized bodies, is identical. A client already tested against
candidate.3 needs no rework.

The new route is narrower than the owner route beside it, which matters because
"member-visible" would otherwise read as "the owner view, loosened". It is gated on
`library.read`, so every approved role may read it, and it returns **only named
persons** — an unnamed clustering artifact is never exposed. A person with no active
face in the selected library is omitted, so a person owned by another library cannot
surface even when it holds faces in this one. Each row carries a name, a face count and
one thumbnail URL pointing at the already member-scoped crop route; it carries no
revision, no rename affordance and no vector, bbox or embedding field. Nothing in it is
writable. Both narrowings are asserted, and both assertions were mutation-tested (see
below).

```sh
PYTHONPATH=tests/security:backend python -m unittest \
  test_protected_native_contract test_access_foundation test_access_transport \
  test_library_reads test_family_stories.FamilyStoryTests \
  test_protected_photo_delivery test_closed_application
```

**134 tests passed**, no skips — the same runner count as candidate.3, including seven
contract tests and the complete replay comparison of 60 captured ASGI exchanges.
Synthetic and in-process; no network listener.

Wall-clock is deliberately not quoted as a comparison figure: this host was running an
unrelated test suite in another session throughout (load average 14–19), so the same
battery measured 41.7 s here against 17.6 s on an idle host for candidate.3. The count
is the stable fact, not the elapsed time.

`python3 scripts/verify_protected_native_contract.py`:
`PASS 2.0.0-candidate.4: 60 cases; 99 source hashes; 7 payload hashes; profile
defaults off`.

Closure count is unchanged at 99: two changed (`boundary.py`, `people.py`), none added
and none removed. All 99 source hashes were independently compared with
`git show 99078f1:<path>` while building the manifest — 0 worktree mismatches and
0 git-blob mismatches. The database migration head remains `d8e5b2f7a904` and
`backend/app/access/library.py` remains byte-identical to the frozen v1 backend,
SHA-256 `5c280e0047771a43274615b77617f896ef2ef075b4fa3f926ae05bf8c49372fe`.

The whole `tests/security` tree was run on both sides to attribute the failure set
rather than count it: **788 passed / 3 failed / 7 skipped** on this source versus
**783 passed / 3 failed / 7 skipped** at `33c42c6` in a clean control worktree. The
three failing node ids are identical on both sides (the sandbox cannot inspect
processes with `/bin/ps`, and one pre-existing full-suite order dependence), and the
5 extra passes are this slice's new people-directory tests. The pack reissue itself
adds no test outcome. Elapsed times for both runs are inflated by the unrelated host
load described above and are not reported.

The protected-WebUI browser suite is **47 checkpoints, exit 0** (was 46), one of them
new: a plain viewer — not the owner — opens the directory, sees a real name and a
decoding face thumbnail, pages to the end while every owner panel stays hidden, and
sees no blank name on either page. That last assertion is the leak detector: an unnamed
cluster renders as an empty heading.

**Both narrowings were mutation-tested, so the tests are known to be able to fail.**
Re-gating the route on `library.people.manage` made four tests fail. Removing the
`display_name <> ''` clause leaked the unnamed cluster and failed both the Python test
(`4 != 3`) and the browser checkpoint (the first card became person `50`, the unnamed
cluster, instead of person `1`).

Deploy gap: the payload allowlist is unchanged and the gap stays at **11 files
(9 M, 2 A)** against the deployed `4022a57`. All five allowlisted files this slice
changes (`access/boundary.py`, `access/people.py`, `ui/access/{app.js,index.html,styles.css}`)
were already in the gap, so the bytes moved without the count moving — the same
distinction candidate.3 recorded. The pack itself is not in the payload allowlist, so
this reissue never moves the gap.

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
