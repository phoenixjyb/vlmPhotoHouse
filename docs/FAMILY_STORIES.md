# Family stories — first backend/WebUI slice

Source base: `470f42c`, isolated branch `codex/family-stories`.
This is local implementation, not Windows deployment or installed APK acceptance.

## Local verification — 2026-09-15

- Full security discovery: 557 tests run, 553 passed, four native-Windows checks
  skipped on macOS. No failures. Existing fixture resource/deprecation warnings
  remain warnings, not evidence of Windows runtime health.
- Expanded migration suite: 13 passed, including interrupted-story-migration
  rollback and byte-preservation of legacy human edits/AI provenance.
- Narrow story/read suite: 38 passed (includes inherited library-read regressions),
  covering concurrent connections, idempotency, transaction rollback, video search,
  short Chinese queries, revocation, parent scope and CSRF.
- Route inventory: 180 method/path entries reviewed; protected application has 32
  routes, including the six additive story/search handlers. Default app still closed.
- Staging manifest tests: three passed; all 65 allowlisted source files exist.
  Worktree startup/migration smoke passed (7 ASGI checks, 9 synthetic operator
  commands, 8 synthetic database-preparation commands). Immutable source packaging and the independent review are recorded in
  [the review return](FAMILY_STORIES_REVIEW.md); no deployment is implied.
- JavaScript syntax and `git diff --check` passed. All 22 real Chromium-to-ASGI
  bridge scenarios passed, covering existing session/library/privacy flows and story editing,
  history, stale revisions, lost-response retries and narrow EN/ZH rendering.
  Synthetic photos only; screenshots inspected. Fetch Metadata is modeled by the
  existing intercepted-browser bridge, not proof of real proxy/header behaviour.

Reproduce with the repository's hash-locked access-test environment, plus separate
test-only Pillow 11.3.0 and an existing Playwright/Chromium installation:

```sh
.venv/bin/python -m unittest discover -s tests/security -p 'test_*.py'
.venv/bin/python -m unittest discover -s tests/security -p test_orm_migrations.py -v
.venv/bin/python scripts/security_inventory.py
node --check backend/app/ui/access/app.js
node tests/security/test_web_browser.cjs
```

`PLAYWRIGHT_MODULE` may select an existing installation. Browser test artifacts
are generated under a temporary directory and its `result.json` records scenario
names, browser version and bridge limitations. This Mac environment is not the
Windows production interpreter. No Windows connection, runtime mutation, push or APK build was performed.
The review return records local commit/package identity.

The independent continuation reproduced and repaired ambiguous-delete retry,
overlapping pagination/history and hidden-tab draft restoration failures. See the
[review return](FAMILY_STORIES_REVIEW.md) for retained evidence and release gates.

## Product boundary

Family stories and model captions coexist on the same photo/video asset. Multiple
members may contribute independent stories. Stories have optional titles, original
text, a language hint (`en`, `zh`, `mixed`, `und`) and an optional byline. A byline is
an author-supplied display name, not verified identity. The immutable author account
ID comes from the session; client-supplied author IDs are rejected. No phone login
is exposed in story responses. Owner edits retain the original author and record
the actual editor separately in history.

Stories are library-visible, not public and not exported to the anonymous TV feed.
Viewer membership grants reading/search only. Existing contributors can create
stories and edit/remove their own; owners can moderate all stories. This feature
does not promote invited viewers or add membership-administration powers.

No editorial word count, truncation, speculative-word filtering, translation or
model call applies to family writing. Technical limits return explicit errors:
title 512 UTF-8 bytes, byline 256 bytes, text 65,536 bytes; story JSON body 524,288 bytes (512 KiB), including escaping.
Nonempty text is required. Content is rendered literally, never as HTML.

## Database and inference safety

Migration `c7f4a9e2b610` follows `b6e3f9a5c721`, creating `access_stories` and
`access_story_revisions` plus indexes. These tables are migration-only metadata,
not added to legacy ORM startup `create_all`. Runtime revision/table checks now
require the new schema. Upgrade an explicitly selected offline candidate, never
rely on startup schema repair. The migration does not modify captions, assets,
account grants, mappings, media, job queues or face data.

Every write uses one `BEGIN IMMEDIATE` transaction containing current authorization,
parent/child scope checks, expected revision, current content, immutable history,
idempotency receipt and content-free audit action. A failed history insert rolls
everything back. Concurrent stale revisions return 409, with no overwrite.

Legacy `captions.user_edited` rows remain intact, visible through the existing
caption API and searchable as `legacy_family`. They are NOT silently reassigned to
an account, automatically copied, deleted, or reclassified as machine output.
The old worker's skip-on-edited-caption policy remains unchanged. New stories never
enter `captions`, so they do not trigger that skip. A future owner-reviewed legacy
conversion must preserve source caption IDs, record unknown provenance honestly,
and coordinate with any caption refresh. Overwritten historical AI originals
cannot be reconstructed by this migration.

Removal is a versioned tombstone: normal listing/search excludes it immediately;
restricted history remains accessible by known story ID to owner/author contributors.
It is not permanent erasure. The WebUI keeps a History link after removal until the
viewer closes. A deleted-story recovery browser and permanent-erasure/retention policy
are deferred. Existing story edits can be restored by copying an older revision into
a new, reviewed draft; restoring never rewrites history.

## Additive client contract (v1 proposal for mobile adoption)

Existing caption/gallery wire contracts are unchanged. New endpoints are mounted
only in the protected application and explicitly inventoried in its closed boundary.
They are not mounted in the separate phone-discovery candidate or home/TV apps.
Adopting them there requires deliberate integration, not a legacy endpoint fallback.

All endpoints require `?library=<id>` and verified current membership. Native clients
use the existing Bearer transport over the configured trusted HTTPS origin; WebUI
uses the existing HttpOnly cookie and CSRF header for every mutation/search POST.
Unknown/duplicate query parameters and unknown JSON fields are rejected. No raw
filesystem paths, model diagnostics, original-media grants or auth tokens in URLs.

| Method/path | Request | Response |
| --- | --- | --- |
| GET `/assets/{asset_id}/stories` | Optional `page`, starts at 1 | `library_id`, `asset_id`, `page`, `has_more`, `can_create`, `items`; 5 whole stories/page |
| POST `/assets/{asset_id}/stories` | `title`, `text`, `byline`, `language`, `mutation_id` | 201, full story |
| PUT `/stories/{story_id}` | Same fields plus `revision` | 200, full story with incremented revision |
| DELETE `/stories/{story_id}` | `revision`, `mutation_id` | 200, tombstoned story |
| GET `/stories/{story_id}/history` | Optional `page` | Current `story`, `page`, `has_more`, 5 revisions/page; owner/author contributor only |
| POST `/library/search` | `text`, `source`, `media`, `page` | `library_id`, `page`, `page_size=24`, `total`, `items` |

All request values are strings. `mutation_id` is a canonical UUID generated once per
logical save; retry an uncertain save with the identical body and UUID. Receipt
uniqueness is scoped to authenticated editor, not bearer session. Exact retries
return the current story after rechecking authorization; they never create a second
story/revision. Reusing a UUID with a different request returns 409. Retrying an old
successful write does not roll current content back. Revision is a positive decimal
string on write; asset IDs remain decimal strings and story IDs UUIDs. API-generated
timestamps are Unix seconds. Responses include author ID, title/text/byline/language,
revision, created/updated times, `deleted`, `source=family`, `can_edit` and
`can_view_history`. History includes actual editor ID and full text, never receipt
digests or mutation IDs.

Status handling: 400 malformed transport/fields; 401/403 generic access denial;
409 conflicting revision/mutation; 413 body too large; 422 text/filter validation;
503 unavailable storage or exceeded SQL budget. Preserve unsaved text on recoverable
errors; clear private content after access loss. Every response is `no-store`. Story endpoints have a separate **3 MiB serialized
JSON response ceiling**, including escaping. Five whole stories fit; history also
includes the current story plus five revisions. Oversized responses fail with 503,
never silently truncate or skip a record. Existing caption/account transport limits
are unchanged. A mobile adapter must adopt this endpoint-specific bound explicitly.
Story/history `revision`, timestamps and response page/count fields are JSON numbers;
request `revision` and `page` remain strings. History row `deleted` is 0/1 while
current story `deleted` is boolean; clients must not conflate these shapes.

Story and history pagination is a current offset view, **not a snapshot**. Concurrent
insertions/removals can move page boundaries. Refresh from page 1 after a mutation;
clients should deduplicate story IDs/revision numbers and must not promise snapshot
completeness. Exact mutation retries return the latest current story; if its revision
is newer than the retried write, show that current version without claiming the
retried draft won. Deletion retries also retain the original UUID/body.

## Search and presentation

Search accepts 1–160 characters, `source=all|family|ai`, `media=all|image|video`,
and a decimal-string `page`. Family includes both independent stories and legacy
user edits. Uses parameterized literal LIKE (escaped `%`, `_`, backslash), supporting
short Chinese substrings and ASCII case-insensitive matches. It is NOT semantic
search, automatic cross-language translation, stemming or full Unicode case folding.

Both SQL source branches are scoped before matching/ranking/counting. Current family
matches rank ahead of machine matches, then date/ID; one result per asset, with a
240-character excerpt and `match.source=family|legacy_family|ai`. Superseded machine
captions, removed stories, old revisions, deleted/unmapped/foreign assets are excluded.
No separate index can retain stale deleted text. A two-second SQLite progress budget
limits scans; a performance failure returns 503, not partial success. Full-library
Windows performance still needs a read-only benchmark before rollout.

The protected WebUI adds a warm story panel, editor, version comparison/history,
literal text rendering, permission-driven controls, save status, unsaved-navigation
confirmation and source-labelled search. AI/legacy captions remain in a separate
collapsible section. Drafts are memory-only in the current tab, not localStorage,
IndexedDB, permanent offline storage or cloud synchronization. Browser reload/close
can discard them after the browser's unsaved-change warning. Background/revalidation
temporarily clears private DOM and restores a draft only to the same authorized
account/library/asset.

## Delivery gates and next slices

1. Local synthetic schema/API/security/browser checks, including real concurrent
   writes, lost-response retry, Chinese queries, permission loss and narrow layout.
2. Review/commit/push and package from the exact immutable reviewed source. The
   staging allowlist includes story modules and migration. No publication this turn.
3. Separately approved Windows maintenance: verify deployed lineage (protected vs
   legacy UI), back up and rehearse candidate migration, preserve/quiesce active
   workers as explicitly authorized, validate Windows runtime/ACL/TLS and rollback,
   then controlled rollout. Do not restart or interrupt captioning just to test UI.
   Old application code cannot serve the new revision; do not downgrade a live DB
   containing new stories. Prefer disabling the new UI while retaining schema/data;
   backup restoration requires explicit handling of any post-backup writes.
4. Freeze the tested additive native contract and synthetic fixtures in the mobile
   repository under coordinator ownership; Android/iOS read/search/edit integration,
   signed artifacts and real-device testing are separate. No APK has been changed.
5. TV needs an explicit approved-story publication policy and revision-bound export,
   then remote-readable story/search screens. Private stories must not simply enter
   the anonymous feed. Voice, translations, featured story, tags/person/event links,
   video timestamp notes and themed albums remain subsequent features.
