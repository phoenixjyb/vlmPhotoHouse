# Protected upload contract — proposed 2026-09-17

**Status: PROPOSED, not implemented.** This is the contract the parity ledger's
`GAP·CONTRACT` row for upload is gated on. It records the owner's decisions, the narrowings
against the legacy surface, and the invariants the implementation must carry. Nothing here
exists in code yet.

## Why this is a contract and not a port

The legacy upload path (`backend/app/legacy_main.py`) is a poor template to copy:

- it validates the file type from the **client-supplied filename extension**, and writes the
  bytes before anything inspects them;
- it writes into the **shared originals root** the media routes serve from;
- it deduplicates **globally** by sha256, so a hit on a file owned by another library returns
  that asset's id — an existence oracle across tenants;
- it records **no uploader, no library, no quota**, and enqueues five tasks including `face`.

Porting it would import all of those. The protected surface is a different thing: a
library-scoped write, by a known account, with provenance, bounds and an audit trail.

## Decisions taken by the owner (2026-09-17)

| question | decision |
| --- | --- |
| who may upload | **any approved member** — viewer, contributor or owner |
| where bytes land | **a separate quarantine root**; an operator promotes into the originals tree |
| derived work | **all five tasks**, including `face` detection |

**Consequence of the first decision, stated plainly.** Every other write capability in the
protected surface is owner-only, and the capability table originally proposed upload as a
separately granted capability that would start disabled. Making it available to *any approved
member* means upload becomes read-adjacent: an approved viewer can add content, not only
consume it. That is a deliberate widening, and the invariants below are what keep it from
being a widening of anything else. It also means the capability is **not** withdrawn by
membership role, so revocation (which already exists) is the only lever — and the audit row
is the only record of who added what.

## Contract

```
POST /libraries/{library_id}/uploads
  Authorization: Bearer <token>            (or the same-origin cookie, with CSRF)
  Content-Type: application/octet-stream
  X-Upload-Filename: <bounded original name>
  <raw bytes>
```

`library` is in the **path**, not a query parameter, matching the discovery routes. No query
string is accepted. Response is `201` with:

```json
{"library_id":"…","asset_id":"…","kind":"image","width":640,"height":480,
 "sha256":"…","bytes":12345,"tasks_enqueued":5}
```

Errors reuse the existing shapes: `400` malformed request or unsupported content, `401`
missing/expired/revoked or not a member of that library, `403` wrong transport or origin,
`413` over the byte cap, `429` over quota, `503` storage unavailable.

## Invariants the implementation must carry

1. **Content, not extension.** The declared filename is advisory only. The accepted type is
   decided by sniffing the leading bytes, and only JPEG and PNG are accepted — the protected
   renderer supports those two, so accepting a third would promise a thumbnail that cannot be
   produced.
2. **Bounds before storage.** A hard byte cap and a decoded-pixel cap, both enforced before
   the bytes reach a writable path. A decompression bomb must be refused, not written.
3. **Provenance.** The upload records the uploading account, the target library, the original
   filename, the content hash, the byte size and the time. This is the whole reason the
   capability can be wide: every addition is attributable.
4. **Library-scoped dedup.** A content hash that matches an asset already mapped into *this*
   library is returned idempotently and enqueues no work. A hash that matches an asset mapped
   only into *another* library must **not** return that asset's id — that would confirm the
   file exists elsewhere. It is stored as a separate asset instead. Duplicating bytes is the
   price of not leaking cross-library existence.
5. **Quarantine, not originals.** The service writes only under its configured upload root.
   Promotion into the originals tree stays an operator action, so a member upload cannot land
   beside real photos, and the media routes never serve a file that has not been promoted.
6. **Audit.** One `access_audit` row per accepted upload. A refused upload writes nothing.
7. **Idempotence under retry.** The same bytes, the same library and the same account must not
   produce two assets; a retry after a lost response returns the first result.

## Required schema change

Provenance needs somewhere to live. `access_audit` records an action and an actor but has no
payload column, so a new table is required (`access_uploads`: asset id, library, account,
original filename, sha256, bytes, state, created_at). That is a **migration**, and migrations
are inside the pinned contract closure — so unlike the date/media filter slice, **this slice
does drift the pin and needs a reissue**.

## Explicitly out of scope

- Multipart upload and the `/ingest/scan` directory scan — the first is an encoding, the
  second is a filesystem capability the protected service should not have.
- Replacing, deleting or versioning an existing asset. Deletion stays `EXCLUDED`.
- Promotion tooling and the operator review step (separate, and operator-side).
- Publication to the TV surface.
- Any client adoption. This is a source contract; enabling it for a member is a later
  reviewed step, and the `library.upload` grant must remain off in the deployed profile until
  the promotion path exists — otherwise uploaded bytes accumulate in quarantine with no
  reviewed way into the library.

## Open items for the owner

1. **Byte cap and quota numbers.** Proposed: 25 MiB per file, and a per-account cap on
   bytes awaiting promotion rather than a per-day count, so a stuck quarantine blocks further
   uploads instead of silently growing.
2. **Whether `face` should run on quarantined bytes at all.** The owner chose all five tasks,
   but face detection is biometric processing, and running it before promotion means the
   system derives biometric data from files an operator has not yet accepted. The alternative
   is to enqueue the four non-biometric tasks at upload and let promotion enqueue `face`.
3. **Whether the grant is per-account or per-library.** "Any approved member" is decided; what
   is not is whether one member can be allowed to upload to library A but not library B.
