# Library-owned people and album management

Local source implementation, 2026-09-15. Builds on
[face assignment](OWNER_FACE_ASSIGNMENT.md) and the
[owner setup gate](OWNER_SETUP_GATE.md). No live service, password or database was
changed for this work.

## Implemented user workflows

- From a detected face, create a named person and assign that face atomically.
  Prefer searching existing names first; equal names never merge identities.
- Explicitly remove a face assignment after confirmation. Keep the person record,
  name, history, face vector, crop and original photo. The person remains selectable
  even with zero faces, through explicit library ownership.
- Create a family album with title, optional Chinese title, description and theme.
  Pick up to 60 photos/videos from paged library thumbnails; reorder the selections,
  choose a cover, remove selections and save. An empty album retains ownership.
- Owners edit albums; current approved members can view the album and open its
  individually authorized photos. No album is automatically published to TV, SMB,
  the public internet or another library.
- Keep English/Chinese UI, confirmation, stale-edit refusal, lost-save readback,
  and private-DOM clearing. Album drafts stay in tab memory only, and restore only
  after same-account, same-library owner revalidation. They are not stored in
  browser storage. Closing an edited draft requires discard confirmation.

Album deletion, bulk face editing, person merging and theme generation/export are
not implemented in this slice. Removing a selection never deletes media.

## Database ownership, not inferred access

The additive migration `d8e5b2f7a904` follows `c7f4a9e2b610`. It adds
`access_person_libraries` and `access_album_libraries`, each with an explicit
library and creator, foreign keys and positive revisions. It copies or deletes
no existing records and does not automatically claim any legacy entity.

New-person creation is tied to a current scoped face revision. Creation and face
assignment share one write transaction; an active face-job conflict or audit error
rolls back the new person too. Correcting/unassigning an exclusively scoped legacy
person retains its ownership explicitly before it can become an orphan. A person
explicitly owned elsewhere is not shown merely because a linked asset moves into
this library. Shared/unmapped face references still forbid management.

New album creation commits the album, library ownership, selected assets and audit
together. A caller-generated UUID makes an identical creation retry return the
existing album; reuse for different content/audience/actor is refused. Existing
album updates require an opaque revision over the selected library, current album,
ownership revision and ordered items. Saving checks every asset under the same
write transaction and increments ownership revision, preventing stale/ABA edits.
An audit failure rolls everything back. Lost update responses require refreshed
readback, not a blind overwrite.

Album reads require current membership and explicit ownership before listing or
counting. Moved, inactive and deleted assets are excluded, including their IDs and
cover reference. `needs_review` warns the owner that saving the visible selections
will remove unavailable entries from this album; there is no media deletion.

## HTTP contract

| Route | Required input / capability |
| --- | --- |
| `POST /admin/faces/{id}/new-person?library=...` | String `display_name`, opaque `revision`; owner people capability |
| `POST /admin/faces/{id}/unassign?library=...` | Opaque string `revision`; owner people capability |
| `GET /library-albums?library=...&page=1` | Current member; 10 albums/page, at most 60 selected assets/album |
| `POST /admin/albums?library=...` | Owner; album content plus canonical UUID string `mutation_id` |
| `PUT /admin/albums/{id}?library=...` | Owner; album content plus opaque string `revision` |

Album content has exactly string fields `title`, `title_zh`, `description`, `theme`,
`asset_ids` and `cover_asset_id`. `asset_ids` is an ordered comma-separated sequence
of unique decimal IDs, or empty; the response uses an array of decimal strings.
`cover_asset_id` is one selected ID, or empty for the default first item/no cover.
Themes are `custom`, `birthday`, `trip`, `growing_up`, `grandparents`,
`year_in_review` and `seasonal`. Titles allow 160 characters and description 1,000;
these album metadata bounds do not change caption/story word limits.
Existing strict body/query, CSRF, origin, no-store and generic-denial rules apply.
No token can be supplied as a query parameter. No global media path or biometric
vector is returned. The inventory covers 195 method/path entries / 42 app routes.

## Migration and runtime gates — still open

The protected runtime and source package now require `d8e5b2f7a904`. The offline
application tool still accepts only an explicitly reviewed **pre-access**
`d2b7e4f6a901` source, now applying through the expanded target. It continues to
refuse an already protected database; a `c7f4a9e2b610` to new-head operational
upgrade needs a separate reviewed procedure. No automatic startup DDL was added.

Earlier native Windows full-size qualification covered only `c7f4a9e2b610`; its
timing, preservation and memory evidence must not be reused for this new target.
Requalify source package, migration/backup/restore, owner and asset provisioning,
service account and protected serving on Windows before cutover.

Legacy unowned orphan people and existing albums remain preserved but unclaimed.
Their ownership import is **not yet implemented or authorized by a guessed
library match**. Before transition, inventory them privately and explicitly review
the selected library, IDs, mixed-library contents, creator and backup. The final
import must be transactional and audited; do not use ad-hoc SQL or bypass the old
UI protection boundary to make them visible. This remains a cutover blocker if
the family needs those existing records in the replacement UI.

Automatic face workers are another separate gate. Known queued/running face jobs
block protected corrections, but the legacy clustering/reclustering/propagation
implementations are not qualified to preserve every manual negative/unassignment
or respect the new ownership boundaries. Do not enable those workers with this
release until reviewed and tested; the source-only caption runner accepts the new
revision but this is not a native caption-worker compatibility result. Caption-only
operation and face inference must be qualified separately.

## Evidence

Tests use migrated synthetic SQLite and the actual protected ASGI app. Coverage
includes schema/foreign keys, orphan retention, moved-asset privacy, duplicate
creation recovery, stale revisions, ordering/cover validation, member/owner rules,
audit rollback, empty-album preservation and unchanged original/task rows.
The real Chromium harness uses an isolated pipe bridge, not a live HTTP service.
It covers both new people flows, bilingual ordered album creation, lost creation
response, member read-only access, concurrent edits, empty albums and same-owner
draft recovery. English desktop and Chinese narrow-screen album renders were
visually inspected; dialog horizontal overflow was checked.

Final evidence: the full security run completed 696 tests in 141.761 seconds,
OK with five skips (four Windows-native checks and one legacy-worker dependency
check). After the final bounded metadata-read hardening, all eight focused album
tests passed, including the additional oversized-record test. All 34 Chromium
checks passed, as did source-package, inventory and whitespace checks. This is
Mac/synthetic source evidence, not approval or proof of live Windows behavior.
