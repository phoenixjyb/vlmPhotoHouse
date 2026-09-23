# Library organization

An assigned asset has one library (`access_asset_libraries.asset_id` is the primary
key). It may appear in multiple albums owned by that library. Pending incoming
uploads remain unassigned until separately approved. Libraries define access;
albums organize content within that access boundary.

Public product presets, with stable IDs and presentation labels:

| ID | 中文 | English |
| --- | --- | --- |
| yanbo-work | 砚波的工作 | Yanbo’s Work |
| documents | 文档 | Documents |
| chuan-work | 曹川的工作 | Chuan’s Work |
| scenery | 风景 | Scenery |
| concerts | 音乐会 | Concerts |
| home-renovation | 装修 | Home Renovation |
| expense-receipts | 报销单 | Expense Receipts |

`scripts/create_library_presets.py --database ABSOLUTE_PATH --operator-account UUID`
previews the exact preset list. Explicit `--apply` creates empty libraries and
approved owner memberships only for that existing active system operator, with
no original-download grant. It audits creation, is idempotent for the same owner,
and refuses a collision with an existing foreign/closed library. No startup DDL,
account creation, membership copying, automatic classification or asset move occurs.
Names are compiled product presets; custom library naming remains future work.

## Protected API

- `GET /library-catalogue`: current available memberships only, bilingual labels,
  active-asset counts and owner/operator management availability. Session profile
  wire shape stays unchanged. At most 100 libraries and a three-second SQL budget.
- `GET /admin/library-transfers?library=SOURCE`: destinations currently owned by
  the caller; only an operator with owner membership may move assets.
- `POST /admin/library-transfers/review?library=SOURCE`, string fields `asset_ids`
  (comma-separated unique IDs, at most 50) and `destination`: seals the asset,
  story/history, source album, actor, audience and source-library state. Returns
  plan plus asset/story/album/face counts and destination audience counts.
- `POST /admin/library-transfers/confirm?library=SOURCE`, string field `plan`:
  rechecks ownership in both libraries and session inside a writer transaction.
  Mapping and story library changes commit atomically with audit and receipt.
  A stale review returns 409. An exact retry succeeds only while its selected
  assets still belong to the reviewed destination. Confirmation body max 16 KiB.

Cookie writes require same-origin and CSRF; native bearer transport uses the same
authorization. No public route or global-admin bypass is introduced. Story review
hashing is incremental with 10,000-row/8 MiB limits. Asset bytes, paths, captions,
face vectors, original grants and independent workers are unchanged.

## What follows a move

Saved stories (including author, deleted state and complete revision history) move
with the asset, by the user's explicit decision. Their content becomes visible to
destination members under normal story permissions. Source-library access ends.
Source album links remain stored, but current-library joins hide the moved asset
and its cover; the album reports that its selections need review. No album is moved
and no destination album membership is created. Moving the asset back may reveal
its retained source album links unless they were subsequently removed by an edit.
Source-owned person identities are not transferred or exposed to the destination.

Prepared-video records remain source-file-bound, so an already prepared video can
be read through its new library after normal current-membership authorization.
Explicit current-library region rules refresh after a move. Empty new libraries
can have refreshing region indexes prepared before their first asset arrives;
static snapshot generation still rejects an empty library.

Home/TV publications are independent snapshots. Moving a protected-library asset
does not recall an existing anonymous publication or downloaded bytes. The move
dialog states this; changing the published TV selection is a separate operation.

## Clients and validation

Secured WebUI: bilingual library selector; checkboxes beside photo/video tiles;
bulk moves and viewer single-item move; destination/audience review; stale-response
protection on destination changes, closing/reopening, library change and logout.
Phone: bilingual labels and existing authorized multi-library browsing. Native
admin move controls remain a follow-up; use the secured WebUI for organization.

Synthetic tests cover membership isolation, preset rollback/idempotency, mixed
selection refusal, metadata drift, story/history preservation, old album hiding,
full 50-video batches, revoked sessions, CSRF and exact replay. Chromium exercises
photo/video selection, late destination replies, confirmation and destination
browsing at desktop and narrow Chinese layouts. Live creation/deployment and
family/device acceptance are separate receipts.
