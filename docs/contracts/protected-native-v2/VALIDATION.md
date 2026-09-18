# Validation receipt — 2026-09-16

## 2.0.0-candidate.11 — reissue after the album archive slice (2026-09-18)

Source baseline: `4674685cae782827cec6604ade1811e8e7ce23eb`.
Branch: `master`.

**Wire-neutral.** `cases.json` regenerated against the new source is byte-identical, still **61
cases**, 0 changed, 0 added, 0 removed. The closure stays at **109 files**
(`backend/app/access/albums.py` and `boundary.py` changed content; none added or removed). The
live route count moves **52 → 55**. The migration head is unchanged at `f2a6d8b4c915`, so this
reissue requires **no** database migration.

**Archive, not delete.** An album could be created and edited but never removed, so a mistake was
permanent. Archiving writes `albums.status='archived'`, a value every read already excludes, so no
migration was needed and **nothing is deleted** — the album, its selected assets and its cover all
survive. Deletion is not offered at all.

**The round trip found a design flaw that inspection had missed.** The first version required a
revision to restore. But the revision is an HMAC the client can only read from the album list, and
archiving removes the album from that list — so restore could never have been used. The asymmetry
is now deliberate and documented: **archiving is revision-bound** (it competes with edits, and
must not silently lose one), **restoring is not** (an archived album cannot be edited, so there is
no concurrent change for a revision to protect against). A no-op in either direction is refused
with `409` rather than reported as success.

**`GET /admin/albums/archived` is the recovery surface and is owner-only.** Without it, archiving
would hide an album with no way back. It is a separate route rather than a flag on the member list,
so an archived album stays invisible to members without a conditional capability on one route.

Properties enforced and tested: the pair hides and restores the album and leaves the list and the
recovery list consistent; archiving deletes no row in `albums`, `album_assets` or
`access_album_libraries`; an archived album is refused by the edit path, not merely hidden from the
list; a stale revision is refused; a no-op in either direction is refused; the whole pair is owner
only, with a viewer, another library's owner and no credential all refused; a missing or foreign
album is refused; and the change is audited as `album.archive.<id>`.

**Note for whoever adopts this:** the deployed library holds **no albums at all**, so none of this
has an observed use yet. It exists because creating without removing is an asymmetry the owner
asked to close, and because the cost was three routes and no migration.

Not verified here: the browser suite could not be run (no Playwright in this environment), so the
new owner controls are covered by 10 source tests, the element-id static check and `node --check`.
The ledger counts no browser checkpoint for this slice.


## 2.0.0-candidate.10 — reissue after the describe-a-photo slice (2026-09-18)

Source baseline: `b1bda66793f2729b8c802dac67d7a425d8259a8b`.
Branch: `master`.

**Wire-neutral.** `cases.json` regenerated against the new source is byte-identical, still **61
cases**, 0 changed, 0 added, 0 removed. The closure moves **108 → 109 files**
(`backend/app/access/captions.py` added; `main.py`, `boundary.py` and `service.py` changed
content). The live route count moves **51 → 52**. The migration head is unchanged at
`f2a6d8b4c915`, so this reissue requires **no** database migration.

**The need was measured first.** Of 27,842 active assets, **3,203 carry no caption**, and of the
caption failures **556 are permanent** — 283 rejected by the English-word policy, 201 by the
Chinese policy, 41 by a format rule, 24 by word-count. A retry produces the same rejected text, so
those photos would stay undescribed forever. The slice exists for exactly that set: a member can
describe a photo that has none.

Four properties were enforced rather than assumed, each pinned by a test:

- **Fill a gap, never replace.** An asset that already has a current caption is answered `409`, so
  this cannot take a description away. The check runs inside the write transaction, so two members
  racing cannot both succeed.
- **`user_edited=1`.** This is the mechanism the pipeline already honours: the generation path
  returns an existing user edit rather than replacing it, and the refresh script treats all
  historical user edits as protected. Without the flag a later worker run could silently discard
  what a member wrote, which would make the feature worse than useless.
- **Any approved member.** Deliberately not contributor-or-owner, which is what `story.write`
  requires: an invitation creates a viewer, and **no route changes a role**, so a
  contributor-gated write could never be reached at all. This matches the owner's upload decision.
- **Attributed through `access_audit`.** `captions` has no author column, and the audit already
  records the actor, so attribution costs no migration.

The asset is resolved through the same `access_asset_libraries` predicate the gallery uses, so a
deleted, foreign or unmapped asset is refused. Text is bounded at 1024 characters with control
characters refused, because a caption is one short human sentence and a newline would corrupt the
stored row and any later export.

Not verified here: the browser checkpoint is written but **unexecuted** (no Playwright in this
environment), so the ledger counts neither it nor the two from the earlier slices. The browser
fixture was deliberately **not** changed — adding an asset would shift the discovery index counts
that existing checkpoints assert — so the browser suite pins only that the describe control is
*absent* where a photo already has a caption. The write path itself is covered by 9 source tests,
the element-id static check, and `node --check`.


## 2.0.0-candidate.9 — reissue after the duplicate-review slice (2026-09-18)

Source baseline: `a4c54030c6f5593e46f6a1335f00843e6af65432`.
Branch: `master`.

**Wire-neutral.** `cases.json` regenerated against the new source is byte-identical, still
**61 cases**, 0 changed, 0 added, 0 removed. The closure moves **107 → 108 files**
(`backend/app/access/duplicates.py` added; `backend/app/main.py` and
`backend/app/access/boundary.py` changed content). The live route count moves **50 → 51**. The
migration head is unchanged at `f2a6d8b4c915`, so this reissue requires **no** database
migration.

**The scope was measured before it was built.** The deployed library holds **3,081 duplicate
groups covering 6,189 of 27,842 active assets** — 22%. Sizes are 3,056 pairs, 24 triples and one
group of five, and **every group sits inside a single library**. Inspecting the paths showed the
cause: the same material imported twice under two naming schemes, so one copy carries the
camera's own filename and the other a phone export's date-stamped name, with identical byte
sizes. That is the family's history rather than a defect, which is why the slice is a read-only
explanation and not a cleanup tool.

Four properties were enforced rather than assumed, each pinned by a test:

- **The repeat predicate is scoped to the library.** A copy that is deleted, in another library
  or unmapped never counts and never appears, so a photo this library holds once is not reported
  as a duplicate merely because another library also has it.
- **No path, no filename, no content hash.** The legacy route returned full filesystem paths; the
  group is identified by its lowest asset id instead, which is stable for paging without letting
  a caller test whether a known image is in the library.
- **Nothing writes.** The route is GET-only and the boundary admits exactly that method and path;
  no role can delete, hide or merge a copy, and deletion stays excluded.
- **Copies are bounded.** 25 groups per page and 25 copies per group, with the true count still
  reported and a `copies_truncated` flag, so a pathological import cannot turn one page into an
  unbounded response.

Not verified here: the browser checkpoint is written but **unexecuted** (no Playwright in this
environment), so the ledger records it as uncounted rather than passing. Covered instead by 9
source tests, a static check that every referenced element id exists, and a `node --check` syntax
pass on both JS files.


## 2.0.0-candidate.8 — reissue after the member photos-of-a-person slice (2026-09-18)

Source baseline: `45adbc410e3a38ccf91526b586f4dba1e37d2c36`.
Branch: `master`.

**Wire-neutral.** Unlike candidate.7, no captured exchange moves: `cases.json` regenerated
against the new source is byte-identical, still **61 cases**, 0 changed, 0 added, 0 removed. The
pinned closure stays **107 files**; two files changed content
(`backend/app/access/people.py`, `backend/app/access/boundary.py`) and none was added or removed.
The live route count moves **49 → 50**. The migration head is unchanged at `f2a6d8b4c915`, so
this reissue requires **no** database migration — unlike candidate.7.

The slice closes a dead end: `GET /people` let a member see 49 names with thumbnails and open
none of them, while **13,246 of 27,842** active assets carry a face. `GET /people/{person_id}/assets`
returns that person's photos, one row per photo, 25 per page.

Four properties were enforced rather than assumed, each pinned by a test:

- **`library.read`, not an owner capability**, matching the directory it completes.
- **The person is resolved through the same library-scoped visibility check**, so a person owned
  by another library is refused exactly as the directory refuses to list them.
- **A person with no display name is refused.** This is the rule the directory applies, and
  person IDs are sequential, so without it a member could enumerate ids to reach an unnamed
  cluster the directory deliberately never offered. This was found while writing the test, not
  anticipated in the design.
- **One row per photo, and nothing about faces.** A photo holding two faces of one person
  appears once, and the body carries no face id, bounding box, confidence or vector, so it
  cannot be used to learn where a face is or to enumerate faces.

Not verified here: the browser suite could not be run in this environment (no Playwright), so
the new member control is covered by source tests, a static check that every referenced element
id exists, and a `node --check` syntax pass. The browser checkpoint was written but is
**unexecuted**, and the ledger's browser-suite count is therefore not restated for this slice.


## 2.0.0-candidate.7 — reissue after the member-upload slice (2026-09-18)

Source baseline: `a8b1d74a6e953f9567beee4f237a8985e0c4412e`.
Branch: `master`. The slice commits and this reissue are local at the time of writing.

**This is the first reissue in this pack that is not wire-neutral.** Unlike candidates.3–.6,
which added routes outside the documented surface, this one moves two existing responses and
adds one route inside it. The change was measured by regenerating `cases.json` from a live
capture against the new source and diffing against candidate.6: **7 cases changed, 1 added, 0
removed**, 60 → 61 cases.

- **`POST /auth/register` now requires `name`.** A display name is required because the family has
  to recognise a member by something other than a phone number, and the name is the source of that
  member's incoming upload folder label. An invalid name is refused the same non-enumerating way
  as a bad phone or a bad code, so registration still reveals nothing about which invitations
  exist. Four cases move: `registration_requires_invitation`, `registration_password_7`,
  `registration_password_129`, `invited_registration_8` — all four still return their previous
  statuses (401, 401, 401, 201).
- **`GET /auth/session` now returns `display_name`.** Three cases move:
  `invited_viewer_session`, `accepted_second_library_session`,
  `revoked_session_still_authenticated`.
- **`POST /uploads` is mounted in the default application** and answers `503` until a deployment
  opts in with an explicit incoming root, so no existing deployment gains a write surface by
  accident. It is deliberately **not** library-scoped: an accepted photo is written into the
  uploader's own incoming folder and into **no** library, so it is invisible to every member until
  an operator promotes and assigns it. One case is added: `upload_requires_opt_in`. The live route
  count moves **48 → 49**.

**A client tested against candidate.6 must be updated**: registration must send `name`, and a
session reader may now see `display_name`. This is a deliberate, reviewed break rather than a
drift, and it is why the pack is still `candidate_requires_coordinator_adoption`.

The pinned source closure moves **101 → 107 files**: six added, none changed in identity and none
removed — `backend/app/access/upload_schema.py`, `upload.py`, `upload_transport.py`,
`promotion.py`, `task_recovery.py`, and
`backend/migrations/versions/f2a6d8b4c915_protected_upload.py`. Many existing files did change
content, so most hashes move; the closure *set* is what grew by six.

**The migration head moves `d8e5b2f7a904` → `f2a6d8b4c915`**, adding a nullable
`access_accounts.display_name` and the `access_uploads` provenance table. This reissue therefore
**cannot be adopted without a database migration**, and the worker gates move with the head:
`scoped_face_worker`, `run_face_worker.REVISION`, `run_caption_worker.REVISIONS` and
`apply_access_schema.TO_REVISION`. A payload carrying the new head **refuses to run against an
un-migrated database**, so the agreed order is **migrate first, then deploy**. `library.upload`
and the new `upload.submit` remain disabled in every profile.

The migration is additive and was verified against both build paths: a database built from
migrations already carries `display_name` because the foundation migration composes
`access/schema.py`, so the `ADD COLUMN` is conditional; a database that predates the revision
(the deployed one) gains it. A test drops the column to reproduce the older shape and proves the
conditional branch does the work rather than being dead code.

## 2.0.0-candidate.6 — reissue after the protected discovery wiring slice (2026-09-17)

Source baseline: `0ea007535545003b0c7fc2bae5efad6b75132278`.
Branch: `master`. The two earlier commits of this session were pushed; the slice and this
reissue are local.

This reissue moves the pinned source closure and the pack version. Mounting the
already-reviewed protected discovery transport in the **default** application adds the
offline artifact loader `backend/app/access/discovery_index.py`, so the closure moves
**100 → 101 files**: one added, three changed (`backend/app/access/boundary.py` for the
two allowlist entries, `backend/app/main.py` for the router registration, and
`backend/app/access/runtime.py` for the explicit opt-in), none removed.

Like candidates.3–.5, this slice adds routes, and both are again **outside the wire
surface this pack documents**. The 60 captured ASGI exchanges cover 28 paths and none of
them is under `/libraries/*/discovery/`.

**Wire neutrality was measured, not assumed.** `cases.json` was regenerated from a live
capture against the new source and compared with the candidate.5 file: identical, 0 diff
lines. After bumping the probe `VERSION`, re-capturing reproduced the committed file
exactly — `capture() == cases.json` evaluated `True` at candidate.6. A client already
tested against candidate.5 needs no rework.

What changed is the default application's **composition**, not its authorization. The
default app now registers the same `discovery_transport` router, and the closed boundary
admits exactly those two method/path pairs bound to endpoint identity as every other
entry is; the live route count moves **46 → 48**. This is the deliberate departure from
the capsule's original statement that `create_app()` and its boundary remain
byte-identical — that sentence is superseded by this reissue, and the route inventory
gained the matching `app.include_router(discovery_router)` topology entry (199 discovered
method/path entries, no UNINVENTORIED, STALE or TOPOLOGY CHANGED).

Mounting is not enabling. `RuntimeConfiguration.discovery_indexes` defaults to empty, so
every existing deployment keeps its current behaviour, and with no runtime the routes
refuse `503 discovery_unavailable` after the same authorization-first check every other
protected route performs — an unauthenticated caller is refused `401` before the runtime
is consulted. No index is derived, globbed or inferred from configuration: the
operator-produced artifact is the only source, it is read read-only, and it is
re-validated through the service's own `validate` and index budget before a runtime
exists.

**The slice was mutation-tested, so the new tests are known to be able to fail.** Removing
the two `allowed()` patterns from the closed boundary failed the admission test with
`403 == 403`; removing `app.include_router(discovery_router)` failed the mounting test;
relaxing the loader's exact key-set check failed the unexpected-key test; and disabling
the loader's `OSError` guard failed the missing-artifact test with a raw
`FileNotFoundError`. All four mutations were reverted byte-identically (SHA-256 compared
against pre-mutation copies).

```sh
PYTHONPATH=tests/security:backend python -m unittest \
  test_protected_native_contract test_access_foundation test_access_transport \
  test_library_reads test_family_stories.FamilyStoryTests \
  test_protected_photo_delivery test_closed_application test_phone_discovery \
  test_discovery_index_producer test_discovery_wiring test_inventory
```

**211 tests passed in 18.5 seconds**, no skips — the candidate.5 receipt battery (170
tests) plus this slice's 21 new wiring and loader tests plus `test_inventory` (20).

`python3 scripts/verify_protected_native_contract.py`:
`PASS 2.0.0-candidate.6: 60 cases; 101 source hashes; 7 payload hashes; profile defaults
off`.

All 101 source hashes were recomputed from the worktree while building the manifest, and
the closure was re-derived independently (added 1, changed 3, removed 0) rather than
carried forward. The database migration head remains `d8e5b2f7a904`.

The whole `tests/security` tree was run with the same runner
(`python -m unittest discover -s tests/security -t tests/security -p 'test_*.py'`):
**836 collected / 3 errors / 7 skipped**. The collection count moves 815 → 836, which is
exactly this slice's 21 new tests. Before this manifest was regenerated the run showed a
fourth error — `test_manifest_pins_source_and_complete_payload`, failing with
`Unexpected backend source pin` — which is the pin assertion this reissue satisfies, not a
regression; the three remaining errors are the same pre-existing fixture-setup
observations as candidate.5 (`/bin/ps` process inspection unavailable, the host-resource
observation, and the `test_suppressed_ownership_repair` full-suite order dependence).

Deploy gap — **this slice necessarily widens the payload allowlist.** The default app now
imports `app.access.discovery_transport`, so the bundle would fail at import on the host
unless the discovery modules ship. `scripts/build_staging_package.py` therefore gains four
modules (`discovery`, `discovery_provider`, `discovery_transport`, `discovery_index`) and
the producer script `scripts/prepare_access_discovery_index.py`, taking the allowlist
**88 → 93 entries** and the relative-import closure inside `backend/app/**` to **0
unresolved imports** (re-checked, not assumed). Against the deployed `4022a57` the
allowlisted changed set moves **13 → 16 files (11 M, 5 A)**; `runtime.py` enters as a
changed file and `discovery_index.py` plus the producer enter as additions. The host
staging script's changed-file assertion must list all 16, and the three pins (bundle SHA,
`runtime-pins.json:protected_manifest`, the commit asserted in `server_entry.py`) move
with them. The pack itself is still not in the payload allowlist, so this reissue never
moves the gap. Nothing was staged or deployed to the host.

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
