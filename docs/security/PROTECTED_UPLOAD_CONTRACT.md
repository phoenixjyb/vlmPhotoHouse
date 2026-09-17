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

## Decisions taken by the owner (2026-09-17)

| question | decision |
| --- | --- |
| who may upload | **any approved member** — viewer, contributor or owner |
| caps and quota | **none for now** — accepted deliberately for a family-run system |
| face detection on upload | **allowed**, on the same reasoning |
| where bytes land | **a per-member folder under `INCOMING`** |
| which library they join | **not decided at upload** — the family decides later |

The last two are the significant ones: upload is a **pre-library** action. A member submits
bytes to their own incoming area, and an operator later decides which library each photo
belongs to. So this is not a library-scoped write at all.

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

## The decision step already exists — with one gap

"Let us decide which library these photos go into" is `assign_unmapped_assets`
(`backend/app/access/provisioning.py`), an existing **offline, sealed-plan** operator
operation:

- target is `{library_id, operator_account_id, asset_ids}`;
- it requires the operator to be an approved **owner** of that library *and* a registered
  operator, with an active account and library;
- it is bounded and validates every asset id;
- and it accepts **only currently unmapped assets**.

**The gap worth knowing: assignment is one-shot.** The operation rejects already-mapped
assets and reports `moves_or_media_writes: False`, and because `asset_id` is the primary key
of `access_asset_libraries`, a photo cannot be in two libraries. So if the family assigns a
photo to the wrong library, **there is currently no reviewed way to move it** — only a new
reviewed operation would provide one. Either accept that, or add a bounded "reassign" plan
before opening upload to members.

## Required schema change

Provenance needs somewhere to live. `access_audit` records an action and an actor but has no
payload column, so a new table is required (`access_uploads`: asset id, account, original
filename, sha256, bytes, state, created_at). That is a **migration**, and migrations are inside
the pinned contract closure — so unlike the date/media filter slice, **this slice does drift
the pin and needs a reissue**.

## Explicitly out of scope

- Multipart upload and the `/ingest/scan` directory scan — the first is an encoding, the
  second is a filesystem capability the protected service should not have.
- Replacing, deleting or versioning an existing asset. Deletion stays `EXCLUDED`.
- The promotion and assignment tooling itself (operator-side, already exists as above).
- Publication to the TV surface.
- Any client adoption. This is a source contract.

## Open items for the owner

1. **The one-shot assignment gap above** — accept it, or require a reassign operation first.
2. **Whether the incoming area is per-account or per-account-per-library.** "Their own
   designated folders" is decided; what is not is whether a member who belongs to two
   libraries gets one incoming folder or one per library. One folder is simpler and keeps
   upload library-agnostic, which matches the rest of this contract.
