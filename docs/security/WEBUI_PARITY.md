# Protected WebUI parity ledger

## Scope and method

This is a source-level comparison of the legacy page (`backend/app/ui/index.html`,
`backend/app/ui/app.js`, the unscoped routes in `backend/app/legacy_main.py` and
friends) against the protected page (`backend/app/ui/access/*`) and its routes in
`backend/app/access/`.

It is a **decided ledger**, not a to-do list. Every legacy capability that is not
present in the protected UI carries an explicit disposition and the dependency that
blocks it, so "parity" means a recorded decision rather than a pending question.

Static route/control counts rechecked on September 19 against the readiness branch.
Runtime and historical test receipts below are separate evidence:

| Measure | Value | How it was derived |
| --- | --- | --- |
| Legacy-surface routes | 114 | Route decorators under `backend/app/**` excluding `access/`, excluding `@*.head` |
| Protected routes | 45 | Route decorators under `backend/app/access/`, excluding `@*.head` |
| Protected routes reachable from the protected UI | 44 of 45 | Route static segments matched against `access/app.js` |
| Legacy control ids | 184 | `id="…"` in `backend/app/ui/index.html` |
| Protected control ids | 166 | `id="…"` in `backend/app/ui/access/index.html` |
| Browser suite | 53 checkpoints, exit 0 | September 19 Chromium/ASGI synthetic run; includes people photos, duplicates, missing-caption write and album archive/restore |
| Python security suite | 986 run, 0 failures, 0 errors, 7 skipped | September 19 full unittest run; native Windows and unavailable optional-runtime tests remain separate gates |

**The contract pin is Python-only.** The pinned closure is `backend/app/**/*.py` plus
`backend/migrations/**/*.py`, `backend/alembic.ini`, the two requirements locks and one test
JPEG — 109 pinned source entries and no UI asset. `app.js`, `index.html` and `styles.css` are **not**
pinned, so a slice that changes only the protected UI needs **no reissue**; the date/media
filter slice below was pin-neutral for exactly that reason. A slice that adds or changes a
*route* does drift the pin, because routes live in Python.

**Limits of this measure.** Reachability is a source-level property. It does not
prove that a route authorizes correctly, that a control is operational at runtime,
or anything about deployment. A control in the legacy page is evidence that the old
UI *attempted* a feature, not proof it worked. Neither column is device or TV
acceptance.

**One protected route is deliberately not reachable from the protected UI:** `POST /uploads`,
added 2026-09-18. There is no upload control, and there is deliberately no UI surface that serves
an **unmapped** asset — a pending upload is in no library, so it cannot be rendered, and the
family reviews incoming photos by opening the folder plus an operator listing instead. Building
that surface would be the first route serving an asset with no library, which is a new
authorization surface and belongs in its own reviewed slice.

The two routes that were previously unreachable — `GET /libraries/{id}/discovery/v1/facets` and
`POST …/discovery/v1/search` — gained controls in the 2026-09-17 date/media filter slice (see
below). Being reachable is a source-level property only: it does not mean the capability is
switched on in any given deployment.

The filter is offered **only where the deployment has opted in**. `RuntimeConfiguration.
discovery_indexes` defaults to empty, and an artifact must be produced offline and loaded by
`backend/app/access/discovery_index.py`, which re-validates it through the service's own
`validate` and index budget. With no opt-in the routes refuse `503 discovery_unavailable`
and the UI hides the panel entirely rather than showing a control that cannot work — absence
of the filter is a deployment state, not an error a member can act on.

Windows source `45f2123` was deployed September 19. Native and public HTTPS checks
pass; authenticated owner/member and device acceptance remain pending. See the
[Windows rollout return](WINDOWS_READINESS_ROLLOUT_20260919.md).

## Dispositions

- **PARITY** — the capability is present in the protected UI.
- **AHEAD** — the protected implementation exceeds the legacy one.
- **GAP·CONTRACT** — wanted, but needs a new library-scoped protected contract or an
  explicit authorization/privacy decision before any UI exists.
- **EXCLUDED** — deliberately not offered to library members; reason recorded.
- **SUPERSEDED** — the legacy mechanism was replaced by a different, better one.

### Browsing and finding

| Capability | Legacy evidence | Protected status | Disposition |
| --- | --- | --- | --- |
| Gallery browse and pagination | `/assets`, `library-grid` | `/assets`, grid, previous/next | **PARITY** |
| Jump to a specific page | `library-page-input` (wired at `app.js:940,2263,3946`) | `#page-input` + `#page-jump` | **PARITY** (closed in this slice) |
| Viewer: preview, captions, fit/width/height/actual, zoom, pan, fullscreen | `/assets/{id}/thumbnail|media`, `preview-*` | `#photo-viewer`, `view-*` | **PARITY** |
| Viewer: previous/next and slideshow | `btn-preview-prev|next|play` | `#view-previous|next|play` | **PARITY** |
| Viewer: filmstrip over the loaded view | `preview-filmstrip`, windowed at `app.js:2931-2937`, click at `3833` | `#viewer-filmstrip` | **PARITY** (closed in this slice) |
| Search: family stories and AI/earlier captions | `/search/captions` | `POST /library/search` | **PARITY** |
| Search: local path / filename | `search-mode`, `library-result-meta` | none | **GAP·CONTRACT** |
| Search: smart, vector, video, video segments | `/search/smart`, `/search/vector`, `/search/video`, `/search/video-segments` | none | **GAP·CONTRACT** |
| Search: person by name or face | `/search/person/name/{name}`, `/search/person/{id}`, `/search/person/vector` | member-visible `GET /people` (names + thumbnails) and `GET /people/{id}/assets` (that person's photos) | **CLOSED 2026-09-18** for browsing by name and opening a person's photos. The read is scoped to the library and to people the directory already lists, returns one row per **photo**, and carries no face id, bounding box, confidence or vector. Face **vector** search and cross-library person identity remain absent, deliberately |
| Tags catalog and tag-to-asset browsing | `/tags`, `/tags/{id}/assets`, `/search/tags`, `tag-*` | member-visible `GET /tags` and `GET /tags/{tag_id}/assets` (25/page, library-scoped) | **GAP·CONTRACT** — the catalog and tag-to-asset halves are now implemented (see "Closed in the member tag-catalog slice"); `/search/tags` autocomplete is still absent and tag **writes** stay EXCLUDED |
| Date / media filtering | `/albums/time` | member-visible `#discovery-panel` → `GET /libraries/{id}/discovery/v1/facets` + `POST …/search` | **CLOSED 2026-09-17** for capture date and media kind (see "Closed in the member date/media filter slice"). It requires an operator index opt-in; without one the panel is hidden. A calendar or month view is still absent, so the *browsing* half of `/albums/time` is not reproduced. |
| Map / geolocation browsing | `/assets/geo`, `geo-map` | **none — and no data path**: the protected asset projection is `a.id,a.mime,a.width,a.height,a.duration_sec,a.taken_at`, so no coordinate is ever selected | **GAP·CONTRACT** — needs a coarse-location privacy contract. The legacy endpoint returned raw `gps_lat`/`gps_lon` floats **and the asset's filesystem `path`**, up to 20,000 points per call; porting it as-is would leak precise location and server paths, and neither is replicated. `gps_lat`/`gps_lon` exist only in the original `0001_initial` schema; no protected code reads them. |
| Home dashboard: featured, recent, people, story highlights, quick search | `tab-home`, `home-*` | none | **GAP·CONTRACT** (separate surface; see also `app/home_*.py`) |
| Duplicate detection and similarity reduction | `/duplicates*`, `/duplicates/reduction/*`, `sim-*` | member-visible `GET /duplicates` (exact duplicate groups) | **CLOSED 2026-09-18 for exact duplicates.** Groups of active assets the library maps that share a `hash_sha256`; 25 groups per page. Read-only — nothing deletes, hides or merges a copy, and **deletion stays EXCLUDED**. The response carries **no path, no filename and no content hash**: a group is identified by its lowest asset id, so a caller cannot test whether a known image is in the library. Measured on the deployed library: **3,081 groups covering 6,189 of 27,842 active assets**, caused by the same material imported twice under two naming schemes. **Similarity reduction (`/duplicates/reduction/*`) is still GAP·CONTRACT** — near-duplicates need the `phash` task output and an explicit threshold decision, a separate contract. |
| Suppressed / restore groups | `/assets/suppressed` | none | **GAP·CONTRACT** |
| Video browsing and segments | `/videos/{id}`, `/videos/{id}/segments` | thumbnail/display only | **GAP·CONTRACT** |

### Contributions

| Capability | Legacy evidence | Protected status | Disposition |
| --- | --- | --- | --- |
| Upload (single and multipart) and ingest scan | `/assets/upload`, `/assets/upload/multipart`, `/ingest/scan`, `btn-ingest` | member-visible `POST /uploads` → `backend/app/access/upload_transport.py` | **CLOSED as source 2026-09-18** for single-file upload, per `PROTECTED_UPLOAD_CONTRACT.md`. Any approved member may submit; no aggregate quota (owner decision); requests are bounded to 25 MiB and header-declared dimensions to 64 × 1024 × 1024 pixels, face detection allowed, and bytes land in a **per-member folder under the incoming root** with **no library**, so the photo is invisible to every member until an operator promotes and assigns it. Review is filesystem browsing plus an operator listing; there is deliberately no UI surface that serves an unmapped asset. The route answers `503` until a deployment opts in with an incoming root, and `upload.submit` is enabled in no profile. **Still absent:** multipart, `/ingest/scan`, resumable chunks, cancel of an incomplete item, quotas, and any client adoption. |
| Family Stories on an asset | `/albums/stories` | `assets/{id}/stories`, `/stories/{id}`, `/stories/{id}/history` | **AHEAD** (conflict-safe revisions and retained history) |
| Caption read | `/assets/{id}/captions` | `assets/{id}/captions` (bounded, read-only) | **PARITY** |
| Caption edit, delete, regenerate | `PATCH|DELETE /captions/{id}`, `/assets/{id}/captions/regenerate`, `btn-caption-regenerate` | member-visible `POST /assets/{id}/captions` (describe a photo that has none) | **CLOSED 2026-09-18 for filling a gap.** **3,203 of 27,842** active assets carry no caption and **556** caption tasks failed **permanently** on policy validation (283 English policy, 201 Chinese policy, 41 format, 24 word-count), so those photos stay undescribed forever unless the family can write one. The route refuses an asset that already has a caption (409) rather than replacing it, so it cannot take a description away, and writes `user_edited=1`, which the generation and refresh paths already honour rather than overwriting. The actor is recorded in `access_audit`. **Still absent:** replacing or removing an existing caption (so a *wrong* AI description cannot be corrected), `/regenerate`, and any moderation or rate limit. |

### People and albums

| Capability | Legacy evidence | Protected status | Disposition |
| --- | --- | --- | --- |
| People list, rename, search, pagination | `/persons`, `/persons/{id}/name`, `/search/person/*` | `/admin/people`, `PUT /admin/people/{id}` | **PARITY** (owner-only, library-scoped) |
| Person asset and face crops | `/search/person/{id}`, `/faces/{id}/crop` | `/admin/people/{id}/faces`, `/faces/{id}/crop` | **PARITY** |
| Attach or detach a face to a person | `/faces/{id}/assign`, `/faces/{id}/assign-stranger` | `/admin/faces/{id}/assignment`, `new-person`, `unassign` | **PARITY** |
| Filter named vs unnamed people | `people-show-unnamed` | `/admin/people?named=all\|named\|unnamed` | **PARITY** (owner-only) |
| Review unassigned faces as a worklist | `unassigned-faces`, `btn-unassigned-*` | `GET /admin/faces` (25/page, library-scoped) | **PARITY** (owner-only) |
| Merge people, delete people, delete faces, recluster | `/persons/merge`, `/persons/{id}/delete`, `DELETE /faces/{id}`, `/persons/recluster` | none | **EXCLUDED** (irreversible clustering mutations; need a separate reviewed design) |
| Albums: list, compose, order, cover, bilingual title | `/albums/drafts*`, `album-*` | `/library-albums`, `/admin/albums` | **AHEAD** (library-owned, revision-bound) |
| Album drafts as a separate object | `/albums/drafts`, `/albums/drafts/{id}` | — | **SUPERSEDED** by library-owned albums |
| Album delete / archive | none in legacy UI | owner `POST /admin/albums/{id}/archive`, `POST …/restore`, `GET /admin/albums/archived` | **CLOSED 2026-09-18 as archive, not delete.** Archiving writes `albums.status='archived'`, which every read already excludes, so **no migration** was needed and **nothing is deleted** — the album, its selected assets and its cover all survive. That is the reversibility the owner asked for: a mistake is put away and can be brought back, and deletion is not offered at all. Restoring takes **no revision**, because an archived album cannot be edited, so there is no lost update to guard against — and a revision could not be obtained anyway, since archiving removes the album from the list. A separate owner-only read lists what has been put away, without which archiving would hide an album with no way back. **Note:** the deployed library has **no albums at all** (0 rows), so this capability has no observed use yet. |
| Publish an album to the TV surface | `home/v2|catalog` | none | **GAP·CONTRACT** (keep separate from authenticated albums) |

### Owner, session and operations

| Capability | Legacy evidence | Protected status | Disposition |
| --- | --- | --- | --- |
| Sign in, session, sign out | `auth` | `/auth/login`, `/auth/session`, `/auth/logout` | **PARITY** |
| Invitations: create, accept, cancel | none in legacy UI | `/libraries/{id}/invitations`, `/invitations/accept`, `/invitations/cancel` | **AHEAD** |
| Member list and revoke | none in legacy UI | `/libraries/{id}/members`, `/members/{id}/revoke` | **AHEAD** |
| Delete an asset or photo | `/assets/{id}/delete`, `btn-delete-asset`, `btn-delete-photo` | none | **EXCLUDED** (destructive; needs confirmation, audit and recovery semantics) |
| Tag writes | `POST|DELETE /assets/{id}/tags`, `btn-add-tags` | none | **EXCLUDED** |
| Voice: chat, command, transcribe, TTS, photo description | `/voice/*` (14 routes), `btn-voice-*` | none | **EXCLUDED** (separate local-runtime surface) |
| Health, metrics, system usage, task queue, index rebuilds, recluster triggers | `/health*`, `/metrics*`, `/system/usage`, `/tasks*`, `/vector-index/rebuild`, `/video-index/rebuild` | none | **EXCLUDED** (operator surface, not family access) |

## Deliberate deviations from legacy

These are intentional and should not be "fixed" toward the legacy behaviour:

1. **A failed viewer step commits to the requested item.** The viewer drops the
   previous photo when a step starts (`closeViewer` clears the media on every open),
   so a step that fails reports that item's error rather than appearing to roll back.
   The suite asserts the requested item is not skipped past, not retried, and stays
   recoverable via Previous. See `PROTECTED_WEBUI_VIEWER.md`.
2. **The filmstrip window keeps its width at the end of a list.** Legacy computed
   `start = max(0, index-5)` then `end = min(len, start+11)`, which shrank the strip to
   as few as 6 buttons on the last item; the protected strip clamps `start` so the
   window stays 11 wide. The cost bound (at most 11 thumbnails) is identical.
3. **The page jump has two independent refusals.** The input carries `min`/`max`, so
   the browser blocks an out-of-range page before the form submits at all; the submit
   handler independently refuses a value that is not a page number. Legacy had only
   the handler.
4. **The protected UI is a single page, not nine tabs.** Legacy's `Home`, `Library`,
   `Map`, `People`, `Tags`, `Stories`, `Similarity`, `Tasks` and `Admin` tabs
   (`tab-*`, wired by `.tab`/`data-tab` at `app.js:1818,3891`) are not a layout to
   reproduce; the protected page is gallery-first with progressive `details` panels.

## Closed in the viewer/gallery parity slice

- `#viewer-filmstrip`: a bounded, windowed strip over the loaded gallery-page or album
  order, marking the current item and jumping on click. Thumbnails reuse the exact
  `/assets/{id}/thumbnail?library=…` URL the grid already requested (`size` defaults
  to 256), so navigation adds no new media variant and no new authorization surface.
- `#page-input` / `#page-jump`: jump to a gallery page, with the two refusals above.
- Browser checkpoints: *"Viewer filmstrip mirrors the loaded order, marks the current
  item, and jumps to it"* and *"Gallery page jump accepts an in-range page and refuses
  an out-of-range one"*. The page-jump checkpoint runs last because it grows the
  fixture library past one page, which would change what every earlier checkpoint sees.

## Test reconciliation — September 19

The current suite completes **986 tests, 0 failures, 0 errors, 7 skipped**. The three
errors reported on September 18 are no longer the current status:

- Both native process-observation checks run successfully in this unrestricted Mac
  environment. They were not disabled or converted into skips.
- The ownership-repair schema-refusal check failed only after another test reloaded
  `app.access.runtime`, replacing its exception class. Restoring the identity-bearing
  symbols after the import-side-effect test fixes the pollution without weakening the
  refused-schema assertion.
- SQLite fixture cleanup warnings are tracked separately from assertion outcomes.
  The traced discovery/export fixtures now explicitly close connections and preserve
  transaction commits. See the current [readiness return](READINESS_DEPLOYMENT_20260919.md)
  for final warning and platform qualification limits.

The browser suite now runs the previously unexecuted person and duplicate checkpoints.
Positive caption and archive/restore flows add two checks, for **53** total. They exposed
and fixed a missing archived-panel toggle loader and a stale empty-caption message after
save. Rendered synthetic screenshots were inspected; no physical phone/TV result is implied.

## Closed in the owner-tools slice

- `/admin/people?named=all|named|unnamed` — an owner-side filter over the existing
  person directory. It is additive: `all` is the default and preserves the previous
  response shape exactly, while an unrecognized value is refused with 400 rather than
  silently treated as `all`.
- `GET /admin/faces` — the unassigned-face worklist the legacy page called
  `unassigned-faces`. Library-scoped, bounded at 25 rows per page, reusing the same
  face presentation and assignment flow as the per-asset panel (`personPicker`), so
  assigning from the worklist does not introduce a second assignment path.
- Both are **owner-only** by nesting: the controls live inside `#people-panel`, which
  is hidden unless the owner panel is shown (`#people-panel.hidden = owner-panel.hidden`).
  The route itself is denied earlier, at the closed boundary — the authorization test
  asserts a viewer, contributor, foreign-library and anonymous caller are refused
  *before* any SQL runs.
- The worklist intentionally does **not** reuse `.face-label-card`; it renders
  `.unassigned-card`, so the per-asset panel's card count stays unambiguous.

Two of these were the only GAP·CONTRACT rows in "People and albums" that needed no
new privacy decision, which is why they could be closed first.

## Closed in the member people-directory slice

- `GET /people` — the first *member-visible* people route. Gated on `library.read`, which
  every approved role holds, so a viewer, contributor or member may use it while
  `library.people.manage` (rename, assign) stays owner-only.
- It is deliberately narrower than the legacy person-search surface it partially answers,
  and each narrowing is a test rather than a comment:
  - **named persons only** — a person with no `display_name` is omitted, so a member
    cannot enumerate an unnamed face cluster the owner has not reviewed.
  - **library-scoped** — the face count joins `access_asset_libraries`, so a person owned
    by another library with no face in this one is neither returned nor probeable by id.
  - **presentation only** — a row is exactly `{id, display_name, name_truncated,
    face_count, thumbnail_url}`; no revision, rename affordance, bbox, vector or
    embedding path crosses the boundary.
  - the thumbnail reuses the existing member-scoped `/faces/{id}/crop?library=…` route
    rather than adding a second media surface, and the page renders it only when the URL
    starts with `/faces/`.
- The route authorizes *before* reading `persons`: anonymous, foreign-library and revoked
  callers are refused with no `FROM persons` SQL executed.
- Still not offered, deliberately: "all photos of this person" (`/search/person/{id}`) and
  face **vector** search.

## Closed in the member tag-catalog slice

- `GET /tags` — the tag catalog of the selected library: 25 rows per page, ordered by
  visible asset count, with an optional literal name search. Gated on `library.read`,
  which every approved role holds, so a viewer, contributor or member may use it.
- `GET /tags/{tag_id}/assets` — the photos carrying one tag, in the same row shape the
  gallery already renders.
- It is deliberately narrower than the legacy tag surface it partially answers, and each
  narrowing is a test rather than a comment:
  - **library-scoped counts** — the visible-asset CTE joins `access_asset_libraries` and
    skips non-active assets, so a tag used only by another library, or only by a deleted
    asset, is neither listed nor countable. No cross-library or global total exists.
  - **no `type`, no link `source`** — legacy `/tags` returned both; a member sees exactly
    `{id, name, name_truncated, asset_count}`.
  - **existence is not confirmable** — a tag with no visible asset in the library is
    refused as access denied rather than answered empty, so the route cannot be used to
    probe whether a name exists elsewhere.
  - **no second media surface** — the photo list reuses the gallery's library-scoped
    predicate and its asset row, and the page renders a thumbnail only when the URL
    starts with `/assets/`.
- The panel is a sibling `details`, not a nested one: `#tags-panel` sits beside
  `#people-panel` rather than inside it, so the member panel cannot inherit an owner
  panel's visibility or id.
- Still not offered, deliberately: `/search/tags` (tag autocomplete) and tag **writes**
  (`POST|DELETE /assets/{id}/tags`), which were already EXCLUDED.
- Browser checkpoint: *"Member browses the read-only tag catalog and its photos without
  tag controls"* — a plain member sees exactly the two tags that carry visible assets,
  not the foreign-only or deleted-only ones, and the panel exposes one input and one
  form and no control that could write.

## Closed in the discovery-index producer slice

This slice answers the dependency that blocked date/media filtering since it was
approved: **who supplies `ReviewedIndex` in production**. It adds no route and no UI,
so nothing member-visible changed; members still cannot filter.

- `scripts/prepare_access_discovery_index.py` — an operator-run offline tool. It opens an
  existing database read-only (`mode=ro`, `query_only=ON`, and an authorizer that permits
  only `SELECT`/`READ`/`TRANSACTION` plus the single `length()` the projection uses), then
  derives one `ReviewedIndex` for one library and writes it once with `O_EXCL`.
- **It reads through the service's own code, not a copy of it**: `scoped_source`, `digest`
  and the service's default `ReadBudget`, so the artifact is by construction one the
  service can consume. A test asserts the produced `source_digest` and `scope_ids` equal
  what the service computes for itself; a mutant that digests a narrower projection fails
  five tests.
- **It approves nothing.** `enabled` is exactly `('date','media')` and people, places,
  assignments and regions are empty, because those two filters read native library fields
  (`taken_at`, media kind) rather than operator assertions. Only a future
  people/locations phase needs reviewed evidence, and it is not this tool's job to invent
  it. A mutant that also enables `people` fails two tests.
- **Freshness is whole-library, not incremental.** `scope_ids` is the full ordered visible
  asset set and the digest covers the whole library projection, so one new photo — or a
  finished caption batch, a new tag, a face assignment — invalidates the artifact. The
  service answers `409 discovery_changed` rather than serving older results, and the
  invalidation is confined to that library. Re-deriving re-emits the artifact; it does not
  re-review anything.
- Refusals, each with a test: implicit or indirect paths, an existing output file, a
  revision that is not a canonical positive decimal, a library with no visible assets, and
  a database missing any projected table. The database is verified unchanged after a run.
- **No contract drift**: a new file under `scripts/` and a new test file are both outside
  the pinned closure (only `scripts/home_media_worker.py` and three named test files are
  in it), so the pack stayed at **100 source hashes** and this slice needed no reissue.
- Where it feeds in: `DiscoveryRuntime` needs an object with a `get(library_id)` method
  and one shared `ReadBudget`, which `MemoryIndexProvider` already satisfies, so the
  artifact loads straight into the reviewed HTTP candidate
  (`GET .../discovery/v1/facets`, `POST .../discovery/v1/search`) without new transport
  design. **Superseded 2026-09-17:** the producer and the four discovery modules are now in
  the Windows staging allowlist and were deployed with the `e718b84` payload upgrade, because
  the default app now imports `discovery_transport` and the bundle would otherwise fail at
  import. See `PROTECTED_PAYLOAD_UPGRADE_E718B84_RETURN.md`.

## Closed in the member date/media filter slice

- `#discovery-panel` — a sibling `details`, member-visible, and **hidden unless the
  deployment has an index**. It is the control that finally reaches the two discovery routes
  the wiring slice mounted.
- Controls: a media-kind select (photos and videos / photos only / videos only), a date
  `from` and `to` bounded by the range the facets route reports, Apply, and Clear. Nothing is
  listed until a filter is chosen — the panel narrows, it does not duplicate the gallery
  beneath it.
- **Two independent refusals on the date range**, matching the page-jump precedent: the
  inputs carry the captured range as native `min`/`max`, and the service independently
  refuses an inverted or malformed range.
- It is deliberately narrower than the legacy `/albums/time` surface it partially answers.
  It offers **capture date and media kind only**: no path or filename search, no vector,
  video-segment or person search, and no calendar or month view. `/albums/time` as a
  *browsing* mode is not reproduced.
- **Read-only by construction**: one form, one select, no file input, and no control that
  could write. Results reuse the gallery's asset row and its `/assets/{id}/thumbnail` URL, so
  the panel adds no new media surface and no new authorization surface.
- **Two failure modes are explicit rather than silent.** With no index the routes answer
  `503`, and the panel hides — a deployment state, not an error the member can act on. When
  the snapshot goes stale the service answers `409`, and the panel clears its results and says
  the library changed rather than showing a list the service no longer stands behind.
- Browser checkpoint: *"Member narrows the library by date and media without any write
  control"*. The load-bearing assertion is the **video** case: every fixture photo is an
  image, so a video filter can only return zero if the filter reached the server rather than
  the client rendering an unfiltered list.
- **The checkpoint was mutation-tested, and the first version failed it.** The original video
  assertion waited on an empty result list, which is *also* true while the request is in
  flight — a hardcoded media kind survived it. It now waits on the response itself, and both
  a hardcoded media kind (`24 !== 0`) and a dropped date filter (timeout) are caught. The
  slice also fixed a real bug the checkpoint found: both date inputs were being given the
  same bound as `min` *and* `max`, so the native validator silently blocked every request.
- **The browser harness now exercises the whole chain.** It derives the artifact with the
  real producer's own functions — in-process, because the harness forbids subprocess and
  network I/O — and passes it through `RuntimeConfiguration.discovery_indexes`, so the
  checkpoint covers producer → artifact → loader → runtime rather than a hand-written index.
  Because the artifact is a whole-library snapshot and earlier scenarios change captions and
  faces, the checkpoint refreshes it first through a new `refresh-discovery-index` scenario.

## Owner decisions on member-facing gaps (2026-09-16)

The owner reviewed which currently owner-only capabilities may be opened to ordinary
library members. Three were approved in principle, each still needing its own scoped
slice, route and negative authorization tests before any UI is exposed. Two are now
implemented; one is not:

1. **Person names + thumbnails** — **implemented** as `GET /people` (see "Closed in the
   member people-directory slice"). Members may browse people by name and see face
   thumbnails. This is deliberately narrower than legacy `/search/person/{id}`: no
   face *vector* search, no cross-library person identity, and no raw biometric
   artifact is exposed to a member. The person directory itself stays owner-only for
   edits.
2. **Date / media filtering** — members may narrow a library by date and media kind.
   The dependency this used to carry (who supplies `ReviewedIndex`) is **answered**:
   an operator-run offline producer derives it (`scripts/prepare_access_discovery_index.py`,
   see "Closed in the discovery-index producer slice"). What remains is not a dependency
   but work: nothing mounts the provider or exposes the filter yet, so members still
   cannot use it.
3. **Tags read-only catalog** — **implemented** as `GET /tags` and
   `GET /tags/{tag_id}/assets` (see "Closed in the member tag-catalog slice"). Members
   may browse the catalog and open a tag's photos. Tag *writes* remain EXCLUDED.

Everything else on the GAP·CONTRACT list either stays owner-only or stays excluded;
no other row changed disposition as a result of this review.

## Recommended sequence

1. **Date/media filtering** — **done as source** (`0ea0075` wiring, `e718b84` payload, plus the
   2026-09-17 filter slice; see "Closed in the member date/media filter slice"). The two
   historical blockers are settled and the UI control now exists. The only thing left is
   **deployment**: an operator produces an artifact with `scripts/prepare_access_discovery_index.py`
   and sets `RuntimeConfiguration.discovery_indexes`. Until then the routes answer `503` and
   the panel stays hidden, which is the intended state rather than a defect.
2. **Member-visible person browsing** — **done**, and now **complete**: `99078f1` added the
   directory (names + thumbnails), and the 2026-09-18 slice added `GET /people/{id}/assets`
   so a member can open a listed person's photos. Person *editing* stays owner-only, and the
   directory was a dead end before this slice — a member could see 49 names and open none.
3. **Tags catalog** — **done** (`2ced43e`, the member tag-catalog slice; see "Closed in
   the member tag-catalog slice"). Tag writes stay excluded. Unlike item 1 this needed no
   provider: `tags` and `asset_tags` are already in the protected read schema
   (`migrations/versions/a5d2e8f4b610_legacy_read_schema.py`) and `access/discovery.py`
   already reads both scoped to a library, so a member-facing catalog was a scoped read
   rather than a new contract.
4. **Contributions (upload)** — the largest family-visible gap, and the largest contract:
   provenance, quota, content handling and the contributor role.
5. **Duplicate review** — **done** (2026-09-18, exact duplicates; see the duplicates row).
   Similarity reduction stays a separate contract.
6. **Album delete/archive**, then **TV publication** as a separate surface.
6. **Discovery-driven browsing in the protected UI** — the provider question is answered and
   the transport is mounted, so this is now purely the UI control from item 1. It must not
   be presented as a drop-in for legacy `/search`: it offers date and media-kind narrowing
   over a reviewed snapshot, not path/filename, vector, video-segment or person search.

## Acceptance gates

For each slice, require source tests plus protected route authorization and negative
tests for wrong library, viewer/contributor/owner role, revoked membership, stale
revision, and missing original permission as applicable. Then separately re-run browser
checks, deploy/runtime checks, and real family device/TV acceptance. A green local
browser run, HTTP 200, or a visible button is not evidence of those later gates.
