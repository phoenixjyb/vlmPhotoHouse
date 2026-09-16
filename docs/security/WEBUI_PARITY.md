# Protected WebUI parity ledger

## Scope and method

This is a source-level comparison of the legacy page (`backend/app/ui/index.html`,
`backend/app/ui/app.js`, the unscoped routes in `backend/app/legacy_main.py` and
friends) against the protected page (`backend/app/ui/access/*`) and its routes in
`backend/app/access/`.

It is a **decided ledger**, not a to-do list. Every legacy capability that is not
present in the protected UI carries an explicit disposition and the dependency that
blocks it, so "parity" means a recorded decision rather than a pending question.

Measured counts on this source (`f697fa8` + the viewer/gallery slice):

| Measure | Value | How it was derived |
| --- | --- | --- |
| Legacy-surface routes | 114 | Decorators under `backend/app/**` excluding `access/` |
| Protected routes | 34 | Decorators under `backend/app/access/` |
| Protected routes reachable from the protected UI | 32 | Route static segments matched against `access/app.js` |
| Legacy control ids | 184 | `id="…"` in `backend/app/ui/index.html` |
| Protected control ids | 111 | `id="…"` in `backend/app/ui/access/index.html` |
| Browser suite | 44 checkpoints, exit 0 | `node tests/security/test_web_browser.cjs` |
| Python security suite | 789 tests, 0 failures, 3 errors | `unittest discover -s tests/security`; the 3 errors are pre-existing and unrelated (see "Known-red tests") |

**Limits of this measure.** Reachability is a source-level property. It does not
prove that a route authorizes correctly, that a control is operational at runtime,
or anything about deployment. A control in the legacy page is evidence that the old
UI *attempted* a feature, not proof it worked. Neither column is device or TV
acceptance.

The two routes that are *not* reachable from the protected UI are
`GET /libraries/{id}/discovery/v1/facets` and `POST /libraries/{id}/discovery/v1/search`.
Both are composed only by `app/phone_discovery_candidate.create_candidate()`, which
requires an explicit `DiscoveryRuntime` built from operator-supplied, in-memory
`ReviewedIndex` records (`backend/app/access/discovery_provider.py`). They are not
wired into the production protected app, so this is **not** a case of a finished
capability hiding behind a missing button.

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
| Search: person by name or face | `/search/person/name/{name}`, `/search/person/{id}`, `/search/person/vector` | owner-only `/admin/people?q=` | **GAP·CONTRACT** (member-visible person search needs a privacy decision) |
| Tags catalog and tag-to-asset browsing | `/tags`, `/tags/{id}/assets`, `/search/tags`, `tag-*` | none | **GAP·CONTRACT** |
| Date / calendar browsing | `/albums/time`, `/home/discovery/v3/calendar` | none | **GAP·CONTRACT** |
| Map / geolocation browsing | `/assets/geo`, `geo-map` | none | **GAP·CONTRACT** (needs a coarse-location privacy contract; raw location must not be copied) |
| Home dashboard: featured, recent, people, story highlights, quick search | `tab-home`, `home-*` | none | **GAP·CONTRACT** (separate surface; see also `app/home_*.py`) |
| Duplicate detection and similarity reduction | `/duplicates*`, `/duplicates/reduction/*`, `sim-*` | none | **GAP·CONTRACT** |
| Suppressed / restore groups | `/assets/suppressed` | none | **GAP·CONTRACT** |
| Video browsing and segments | `/videos/{id}`, `/videos/{id}/segments` | thumbnail/display only | **GAP·CONTRACT** |

### Contributions

| Capability | Legacy evidence | Protected status | Disposition |
| --- | --- | --- | --- |
| Upload (single and multipart) and ingest scan | `/assets/upload`, `/assets/upload/multipart`, `/ingest/scan`, `btn-ingest` | none | **GAP·CONTRACT** (needs provenance, quota, storage, content-handling and role policy) |
| Family Stories on an asset | `/albums/stories` | `assets/{id}/stories`, `/stories/{id}`, `/stories/{id}/history` | **AHEAD** (conflict-safe revisions and retained history) |
| Caption read | `/assets/{id}/captions` | `assets/{id}/captions` (bounded, read-only) | **PARITY** |
| Caption edit, delete, regenerate | `PATCH|DELETE /captions/{id}`, `/assets/{id}/captions/regenerate`, `btn-caption-regenerate` | none | **GAP·CONTRACT** |

### People and albums

| Capability | Legacy evidence | Protected status | Disposition |
| --- | --- | --- | --- |
| People list, rename, search, pagination | `/persons`, `/persons/{id}/name`, `/search/person/*` | `/admin/people`, `PUT /admin/people/{id}` | **PARITY** (owner-only, library-scoped) |
| Person asset and face crops | `/search/person/{id}`, `/faces/{id}/crop` | `/admin/people/{id}/faces`, `/faces/{id}/crop` | **PARITY** |
| Attach or detach a face to a person | `/faces/{id}/assign`, `/faces/{id}/assign-stranger` | `/admin/faces/{id}/assignment`, `new-person`, `unassign` | **PARITY** |
| Filter named vs unnamed people | `people-show-unnamed` | none — `/admin/people` accepts only `library, page, q` | **GAP·CONTRACT** |
| Review unassigned faces as a worklist | `unassigned-faces`, `btn-unassigned-*` | none (per-asset face review only) | **GAP·CONTRACT** |
| Merge people, delete people, delete faces, recluster | `/persons/merge`, `/persons/{id}/delete`, `DELETE /faces/{id}`, `/persons/recluster` | none | **EXCLUDED** (irreversible clustering mutations; need a separate reviewed design) |
| Albums: list, compose, order, cover, bilingual title | `/albums/drafts*`, `album-*` | `/library-albums`, `/admin/albums` | **AHEAD** (library-owned, revision-bound) |
| Album drafts as a separate object | `/albums/drafts`, `/albums/drafts/{id}` | — | **SUPERSEDED** by library-owned albums |
| Album delete / archive | none in legacy UI | none | **GAP·CONTRACT** |
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

## Known-red tests

The Python suite reports 3 errors against this source. All three reproduce at `f697fa8`
in a clean control worktree with no changes applied, and none touch the WebUI:

- `test_home_library…test_native_memory_observation_reports_current_process` — sandbox
  process inspection is unavailable.
- `test_home_media_profiles…test_large_baseline_jpeg_is_subsampled…` — environment
  dependent.
- `test_suppressed_ownership_repair…test_stale_audience_backup_expiry_and_schema_are_refused`
  — passes in isolation and errors only in full-suite order; a pre-existing order
  dependence, not a regression.

## Recommended sequence

1. **Date/media filtering** — the narrowest genuinely useful family gap, and the only
   one whose contract is already designed (`discovery` facets `date`, `media`). Blocked
   on deciding who supplies `ReviewedIndex` in production.
2. **Member-visible person browsing** — needs a privacy decision: today person data is
   owner-only and library-scoped on purpose.
3. **Tags catalog** — read-only tag browsing is the cheap half; tag writes stay excluded.
4. **Contributions (upload)** — the largest family-visible gap, and the largest contract:
   provenance, quota, content handling and the contributor role.
5. **Album delete/archive**, then **TV publication** as a separate surface.
6. Discovery-driven browsing in the protected UI, once the provider question above is
   answered; it must not be presented as a drop-in for legacy `/search`.

## Acceptance gates

For each slice, require source tests plus protected route authorization and negative
tests for wrong library, viewer/contributor/owner role, revoked membership, stale
revision, and missing original permission as applicable. Then separately re-run browser
checks, deploy/runtime checks, and real family device/TV acceptance. A green local
browser run, HTTP 200, or a visible button is not evidence of those later gates.
