# Protected WebUI parity inventory

## Scope and evidence

This is a source-level comparison of the legacy page (`backend/app/ui/index.html`,
`backend/app/ui/app.js`) with the protected page
(`backend/app/ui/access/index.html`, `backend/app/ui/access/app.js`) and its
library/access routes under `backend/app/access/`. A control in the legacy page
is evidence that the old UI attempted to offer a feature, not proof that the
feature was operational, authorized, or ready for family use. Likewise, this
inventory does not claim deployment, Windows/runtime readiness, or device
acceptance.

The current branch already has local protected-viewer control work and the last
turn reported 35 browser passes. Those checks were not rerun for this audit and
were not deployed. Family Stories and people/albums protected flows already
exist in source. The current owner slice is implementing previous/next and
slideshow over the loaded gallery-page/album order, with privacy cleanup still
pending.

## Feature inventory

### Family browsing and finding memories

| Legacy capability | Protected current status | Contract/dependency and parity slice |
| --- | --- | --- |
| Home dashboard: featured/recent items, people, story highlights, quick search and “view all” navigation | Missing. The protected page opens directly to the selected library gallery. | Build only on protected library-scoped reads; do not copy dashboard calls to unscoped legacy endpoints. |
| Gallery browsing and pagination | Present: `GET /assets?library=…&page=…&page_size=…`, detail and captions routes; thumbnails/media are protected. | `library.read`; verify page boundaries and stale-library/session handling. |
| Search by path, caption, smart query, person name, media filter, tags | Partial: protected `/library/search` searches family stories and AI/legacy descriptions; no protected path/smart/person/tag search in the UI. | `library.read`; define a protected search contract/index before exposing additional modes. Existing discovery routes (`/libraries/{id}/discovery/v1/*`) are separate and not a drop-in replacement. |
| Tags catalog and tag-to-assets browsing | Missing. Legacy UI called `/tags…` and asset tag mutation routes; no corresponding protected routes/UI. | Requires an explicit library-scoped read/write policy, not reuse of global tag endpoints. |
| Map/geolocation browsing | Missing. Legacy UI used `/assets/geo`; protected page has no map. | Requires a privacy-reviewed coarse-location contract and `library.read`; do not expose raw location by copying legacy behavior. |
| Similarity reduction and hidden/restore groups | Missing. Legacy UI offered preview/apply/restore and `/duplicates/reduction/*`. | Requires a library-scoped, revision/idempotency-aware mutation contract; global duplicate suppression cannot be assumed safe. |
| Asset viewer: preview, captions, fullscreen, fit/width/height/actual, zoom and pan | Present in protected source for authorized photo/media and captions, with original download shown only when allowed. Previous/next/slideshow is in the current owner slice and is not yet complete. | Thumbnail/display use `library.read`; original uses `media.original.read` (`member.originals`). Keep viewer navigation bounded to the loaded gallery page/album order until cross-page ordering is specified. |

### Family contributions

| Legacy capability | Protected current status | Contract/dependency and parity slice |
| --- | --- | --- |
| Upload/multipart upload and ingest scan | Missing. Legacy UI exposed upload/`/ingest/scan`; protected UI has no intake control or protected intake route. | Requires an explicit contribution/upload contract, storage/quota policy, provenance, malware/content handling, and role permission. Do not wire the legacy write routes into the protected page. |
| Family Stories attached to an asset | Present and materially richer in protected source: list/create/edit/delete, conflict-safe revisions/history, search, and draft handling. | Read requires `library.read`; create/edit requires `story.write` (owner/contributor, with non-owner edits limited to the author); preserve revision and mutation handling. “Shared with this library” is not automatic TV publication. |
| AI descriptions / earlier caption edits | Present as a bounded read-only caption section (first 20, explicit truncation state). | `GET /assets/{id}/captions` with `library.read`; no protected caption regeneration. |

### People and albums

| Legacy capability | Protected current status | Contract/dependency and parity slice |
| --- | --- | --- |
| People list, named/unnamed filters, person assets and face crops | Partial: owner-only people review, search, pagination, person face review, asset face review and crops exist. | `library.people.manage`; all reads are library-scoped and active-asset filtered. Viewer/contributor visibility is intentionally not equivalent to legacy global `/persons`. |
| Create person, rename and face assignment/unassignment | Partial: protected owner-only rename and explicit face assignment/new-person/unassign with revision checks exist. | `library.people.manage`; exclusivity and face/person revisions must be honored. No automatic propagation is promised. |
| Merge/delete people, delete faces, recluster | Missing. Legacy UI exposed these/global recluster controls; protected routes do not. | Requires a separately designed library-scoped mutation and review policy; do not expose global `/persons/merge`, `/persons/{id}/delete`, or recluster. |
| Story albums / album drafts / composer | Partial-to-present: protected library albums list, owner create/edit composer, bounded asset selection and ordering, cover and bilingual title/description. | Reads require `library.read`; create/edit is owner-only (`library.albums.manage`). No protected album delete, publish-to-TV, or legacy draft endpoint is present. |
| Album ordering and viewer navigation | Partial: album asset strips open authorized assets; current previous/next/slideshow slice is scoped to the loaded album order. | Keep album membership/order revision-bound and avoid leaking assets across libraries. Acceptance must include empty/small/large albums and session/library changes. |

### Owner and operational controls

| Legacy capability | Protected current status | Contract/dependency and parity slice |
| --- | --- | --- |
| Voice command/chat/transcription/TTS and voice history | Missing from protected UI and access routes. | If later required, design a protected, local-runtime-only contract with typed actions and authorization; do not reuse legacy voice routes by button parity. |
| Health, metrics, system usage, task queue, vector rebuild, ingest and recluster actions | Missing. These remain legacy/admin operational controls. | Keep operational/admin surfaces separate from family library access; require explicit operator authorization and runtime evidence. |
| Asset delete, photo delete, caption regenerate, tag writes | Missing from protected UI/routes. | Requires separately approved destructive, library-scoped contracts with confirmation, audit, revision/idempotency and recovery semantics. |
| Invitations, switching libraries, member list and revoke | Present: protected auth/session/logout, invitation accept/create/cancel, library selector, owner member review and revision-bound revoke. | Membership/session policy is enforced by `AccessService`; owner-only management. Revocation stops future requests but cannot recall already downloaded files. |

## Prioritized implementation slices

1. Finish and locally verify the current viewer navigation slice: previous/next
   and slideshow over the loaded gallery page and album order, with no
   cross-library or stale-viewer leakage; complete privacy cleanup before
   expanding the order scope.
2. Add protected discovery parity: decide which legacy search, people, tags,
   date/place and media filters are family-safe, then add typed library-scoped
   API contracts and UI states. Treat the existing protected story/description
   search as a distinct capability.
3. Complete album lifecycle parity only after defining delete/archive,
   membership visibility, ordering revisions, and whether/when an album can be
   published to the anonymous TV surface. Keep TV publication separate from
   authenticated library albums.
4. Define contributions/intake separately (upload, provenance, quota,
   processing status and review) before adding any upload or ingest control.
5. Consider owner/admin mutations (tags, asset deletion, caption regeneration,
   similarity, people merge/delete/recluster) one contract at a time with
   explicit permission, audit, conflict and recovery behavior. Voice and
   operational controls should remain separate until their protected/local
   runtime boundary is specified.

## Acceptance gates

For each slice, require source tests plus protected route authorization and
negative tests for wrong library, viewer/contributor/owner role, revoked
membership, stale revision, and missing original permission as applicable.
Then separately re-run browser checks, deploy/runtime checks, and real family
device/TV acceptance. A green local browser run, HTTP 200, or visible button is
not evidence of those later gates.
