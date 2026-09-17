# Protected upload contract — proposed 2026-09-17

**Status: PROPOSED, not implemented.** This is the contract the parity ledger's
`GAP·CONTRACT` row for upload is gated on. It records the owner's decisions, the narrowings
against the legacy surface, and the invariants the implementation must carry.

## Why this is a contract and not a port

The legacy upload path (`backend/app/legacy_main.py`) is a poor template to copy:

- it validates the file type from the **client-supplied filename extension**, and writes the
  bytes before anything inspects them;
- it writes into the **shared originals root** the media routes serve from;
- it deduplicates **globally** by sha256, so a hit on a file owned by another library returns
  that asset's id — an existence oracle across tenants;
- it records **no uploader, no library, no quota**, and enqueues five tasks including `face`.

Porting it would import all of those.

## What a library is, and why it shapes this contract

Read from the schema (`backend/app/access/schema.py`):

- **`access_libraries(id TEXT PRIMARY KEY, state, bootstrap_operator)`** — the id is free
  text and **is** the name; there is no display-name column. `state` is `active` or `closed`.
  A library is created by an operator.
- **`access_memberships(account_id, library_id)`** — status, role, revision, expiry and a
  separate `originals` flag. This is the **unit of authorization**: what a member is a member
  *of*.
- **`access_asset_libraries(asset_id INTEGER PRIMARY KEY REFERENCES assets(id), library_id)`**
  — and `asset_id` is the **primary key**, so an asset belongs to **at most one** library. This
  is a classification, not a tag.

So a library is **the authorization and visibility boundary for a set of photos**. Every read
joins `access_asset_libraries` on the selected library, which has one consequence this
contract depends on: **an asset with no row in that table is invisible to every member.**
(It is also why the fixture's unmapped asset 999 is a useful negative control.)

That is exactly the state an incoming upload should be in.

**A photo cannot be in two libraries, and no indirect path reaches across.** Because
`asset_id` is the primary key, the classification is exclusive; and the other two
library-scoped entities cannot be used to route around it:

- **Albums** — `albums.py` filters an album's assets by joining `access_asset_libraries` on
  the *reading* library, and refuses to save an album whose assets are not all mapped to it.
  A foreign reference is not rendered: the row is excluded and `needs_review` flips true.
- **People** — a person is owned by one library (`access_person_libraries`), and `_person()`
  **denies** access when the owner is a different library even if faces exist locally; a
  person with no face in this library is not listed at all.
- **Discovery** — the index is derived per library from `scoped_source`, which joins the same
  table, so a photo is in at most one library's index by construction.

## Decisions taken by the owner (2026-09-17)

| question | decision |
| --- | --- |
| who may upload | **any approved member** — viewer, contributor or owner |
| caps and quota | **none for now** — accepted deliberately for a family-run system |
| face detection on upload | **allowed**, on the same reasoning |
| where bytes land | **a per-member folder under `INCOMING`** |
| which library they join | **not decided at upload** — the family decides later |
| member identity | **a display name is required**, not just a phone number |
| how the family reviews | **filesystem browsing plus an operator listing** — no UI review surface |
| is the decision reversible | **yes** — a wrong assignment must be correctable |

The last two are the significant ones: upload is a **pre-library** action. A member submits
bytes to their own incoming area, and an operator later decides which library each photo
belongs to. So this is not a library-scoped write at all.

## The organizing structure

**The folder is a human interface; the database stays authoritative.** This is forced by the
existing model, not chosen: `assets.path` is a database column constrained to configured
roots, and derived files are addressed flat by asset id, so the on-disk layout of originals is
whatever the database says and "which library" is never a filesystem concept. Putting libraries
in the folder tree would create a second source of truth that can drift silently.

Three stages:

1. **Upload** — bytes are written to `INCOMING/<member-label>/<batch>/`; an `assets` row is
   written with `path` pointing into `INCOMING`, plus the provenance row; **no**
   `access_asset_libraries` row exists, so the photo is visible to nobody.
2. **The family decides** — one reviewed operation **promotes and assigns together**: the file
   moves into the originals root, `path` is updated, and the library mapping is written.
3. **In the library** — the photo is an ordinary asset and every existing route treats it as
   one.

**`INCOMING` sits outside `original_roots`.** This is the invariant worth the most: it makes an
unassigned upload unservable **by construction**, rather than by an authorization check that
could later be misconfigured. The media route resolves an original from `row['path']` and
requires it to sit under a configured root, so bytes in `INCOMING` are unreachable even if an
authorization decision were wrong.

### Review, and why there is no UI for it

An unmapped asset is **unreachable through every media route** — every lookup happens after
current parent authorization, and the parent is library-scoped. So a pending upload cannot be
rendered in the protected UI at all.

Given that, the family reviews two ways, both of which need no new authorization surface:

- **by opening the incoming folder** — the folder is the interface, which is why the label must
  be human-readable;
- **by an operator listing** that reports, per pending upload, the uploader, batch, original
  filename, byte size and time. No thumbnails: deciding from names and dates is the point.

A UI review surface is deliberately **not** built. It would require the first route that serves
an asset with **no library**, which is a new authorization surface and belongs in its own
reviewed slice, not smuggled in behind upload.

## Contract

```
POST /uploads
  Authorization: Bearer <token>            (or the same-origin cookie, with CSRF)
  Content-Type: application/octet-stream
  X-Upload-Filename: <bounded original name>
  <raw bytes>
```

**No library in the path**, because no library is chosen yet. The uploader is the
authenticated account. No query string is accepted.

Response `201`:

```json
{"account_id":"…","asset_id":"…","incoming":"<opaque member folder label>",
 "kind":"image","width":640,"height":480,"sha256":"…","bytes":12345,
 "library_id":null,"tasks_enqueued":5}
```

`library_id` is returned as `null` on purpose: it documents that the photo is not yet visible
to anyone. Errors reuse the existing shapes — `400` malformed or unsupported content, `401`
missing/expired/revoked session or no active membership, `403` wrong transport or origin,
`413` over the byte cap, `503` storage unavailable.

**Capability.** This needs a new capability, proposed as **`upload.submit`** rather than the
existing `library.upload`, because it is not scoped to a library: an account holding at least
one approved, unexpired membership in an active library may submit bytes to its own incoming
area. Nothing about it grants read access to anything.

## Invariants the implementation must carry

1. **Content, not extension.** The declared filename is advisory only. The accepted type is
   decided by sniffing the leading bytes, and only JPEG and PNG are accepted — the protected
   renderer supports those two, so accepting a third would promise a thumbnail that cannot be
   produced.
2. **Bounds before storage.** A hard byte cap enforced before the bytes reach a writable path,
   and a decoded-pixel cap so a decompression bomb is refused rather than written. *(Owner
   decision: no quota and no per-member cap. A byte cap per file is still required — it is a
   safety bound on a single request, not a quota on a member.)*
3. **The upload is unassigned by construction.** It writes an `assets` row and **no**
   `access_asset_libraries` row. It therefore appears in no library, no gallery and no
   discovery index until an operator assigns it. This is the invariant that makes an
   open-to-all-members upload safe to accept.
4. **Provenance.** The upload records the submitting account, the original filename, the
   content hash, the byte size and the time. With no quota, this record is the only control.
5. **Library-scoped dedup.** A content hash matching an asset already mapped into a library
   must **not** return that asset's id — that would confirm the file exists elsewhere. Since
   an incoming asset is unmapped, a hash that matches any mapped asset is stored as a new
   asset instead.
6. **Quarantine, not originals.** The service writes only under its configured upload root, in
   a per-member subfolder. Promotion into the originals tree stays an operator action, so the
   media routes never serve a file that has not been accepted.
7. **Audit.** One `access_audit` row per accepted upload, with `library_id` null. A refused
   upload writes nothing.
8. **Idempotence under retry.** The same bytes from the same account must not produce two
   assets; a retry after a lost response returns the first result.

## The operator operations this needs

The decision step partly exists: `assign_unmapped_assets` (`backend/app/access/provisioning.py`)
is an offline, **sealed-plan** operation that requires an approved **owner** of the target
library *and* a registered operator with an active account, is bounded, validates every asset
id, and accepts **only currently unmapped assets**.

Two new operations are needed, both in the same offline sealed-plan family:

1. **Promote and assign, together.** `assign_unmapped_assets` reports
   `moves_or_media_writes: False`, and it must stay that way for existing callers. If a photo
   were assigned without being promoted, `path` would still point into `INCOMING` — outside
   `original_roots` — so the media route would refuse it: the photo would be *in* a library but
   unviewable. Promotion and assignment must therefore happen in one operation; one operation
   is safer than an ordering rule that a later caller can get wrong.
2. **Reassign, bounded.** Because `asset_id` is the primary key of `access_asset_libraries`, a
   photo is in exactly one library, so correcting a mistake means **updating** that mapping
   rather than adding a second. The owner has decided the decision must be reversible, so a
   bounded reassign plan is required before upload opens to members.

Reassign is a database-only change — after promotion the bytes are already in the originals
root — but it has consequences the codebase already anticipates: the asset leaves one library's
reads and joins another's; a person whose faces were exclusive to the old library stops being
renameable; a containing album reports `needs_review`; and both libraries' discovery indexes go
stale until re-derived. The album read already carries the comment *"A moved/deleted asset is
excluded, including its ID and cover reference"*, so the defensive handling exists — only the
reviewed operation does not.

**Out of scope:** un-accepting a photo, i.e. sending an assigned asset back to `INCOMING`.
Reassign covers the mistake the family will actually make, which is the wrong library.

## Required schema changes

Two, in one migration.

**1. A display name on accounts.** `access_accounts` holds only `id`, `phone_login`,
`password_hash` and `state`, so a member currently has no name to show — or to name a folder
with. A `display_name` column is required, and because it becomes a **path component** it needs
more than a length bound:

- it is bounded, and non-empty for an approved member;
- the folder label is a **path-safe slug derived from it**, made unique at first upload with a
  numeric suffix if two members collide, and **recorded in the database** so it is never
  recomputed. A rename therefore does not silently move a folder, and a later name change
  cannot break a stored path;
- the raw name is display-only and is never used to build a path directly.

**2. Provenance.** `access_audit` records an action and an actor but has no payload column, so a
new table is required (`access_uploads`: asset id, account, incoming label, batch, original
filename, sha256, bytes, state, created_at).

Both are **migrations**, and migrations are inside the pinned contract closure — so unlike the
date/media filter slice, **this slice does drift the pin and needs a reissue**.

## Explicitly out of scope

- Multipart upload and the `/ingest/scan` directory scan — the first is an encoding, the
  second is a filesystem capability the protected service should not have.
- Replacing, deleting or versioning an existing asset. Deletion stays `EXCLUDED`.
- The promotion and assignment tooling itself (operator-side, already exists as above).
- Publication to the TV surface.
- Any client adoption. This is a source contract.

## Decisions closed

- **Reversibility** — a bounded reassign plan is required before upload opens to members.
- **Review surface** — filesystem browsing plus an operator listing; deliberately no route that
  serves an unmapped asset.
- **Member identity** — a display name is required, and it drives the incoming folder label.
- **One incoming folder or one per library** — settled by construction: the upload route carries
  no library, so there is exactly one incoming folder per account. A per-library folder would
  require choosing a library *at upload*, which is the thing this contract exists to avoid.

## Still open

- **Batch granularity** — proposed: one folder per upload session, so that the review unit, the
  provenance receipt and a "this whole batch → library X" action all line up. Not yet confirmed.
- **Who may set or change a display name** — the member at registration, an operator, or both.
  Registration is the natural place; an operator override matters when a name is wrong or
  duplicated.
