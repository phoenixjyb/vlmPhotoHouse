# Protected native profile 2.0.0-candidate.7

Backend source: `a8b1d74a6e953f9567beee4f237a8985e0c4412e`.
Database migration head: `f2a6d8b4c915`. This is a backend-owned candidate
handoff, not an adopted replacement for the mobile repository's frozen
`contracts/v1` (`1.0.0-fixture.1`, backend `87a60b475b37b1d6873cd977bcb6e7254472da7e`).
The later merged backend `a42147c63cf6a9628899735aa64b18cff1ec619d` also predates
this source. The manifest pins source bytes and all pack payloads independently
of later documentation/test commits. Hashes detect drift; they are not signatures.

## Reissue — 2.0.0-candidate.7

`2.0.0-candidate.6` pinned source `0ea0075`. This reissue carries the member-upload slice, and
it is a **wire** change rather than a hash drift: two existing responses move and one route is
added.

- **`POST /auth/register` now requires `name`.** A display name is required because the family
  has to recognise a member by something other than a phone number, and the name is the source of
  that member's incoming upload folder label. An invalid name is refused the same
  non-enumerating way as a bad phone or a bad code, so registration still reveals nothing about
  which invitations exist. Four cases move: `registration_requires_invitation`,
  `registration_password_7`, `registration_password_129`, `invited_registration_8`.
- **`GET /auth/session` now returns `display_name`.** Three cases move:
  `invited_viewer_session`, `accepted_second_library_session`,
  `revoked_session_still_authenticated`.
- **`POST /uploads` is mounted in the default application.** It answers `503` until a deployment
  opts in with an explicit incoming root, so no existing deployment gains a write surface by
  accident. It is deliberately **not** library-scoped: an accepted photo is written into the
  uploader's own incoming folder and into **no** library, so it is invisible to every member
  until an operator promotes and assigns it. One case is added: `upload_requires_opt_in`.
- **The migration head moves `d8e5b2f7a904` → `f2a6d8b4c915`**, adding a nullable
  `access_accounts.display_name` and the `access_uploads` provenance table. This is the first
  reissue in this pack that a deployment **cannot** adopt without a database migration, and the
  worker gates (`scoped_face_worker`, `run_face_worker`, `run_caption_worker`,
  `apply_access_schema`) move with the head. The agreed order is **migrate first, then deploy**.

Case count moves **60 → 61**.

## Reissue — 2.0.0-candidate.6

`2.0.0-candidate.5` pinned source `2ced43e`. Mounting the already-reviewed protected
discovery transport in the **default** application adds the offline artifact loader,
`backend/app/access/discovery_index.py`, so the pinned `backend/app/**` closure count
moves **100 → 101 files**. Three existing source hashes moved —
`backend/app/access/boundary.py` for the two allowlist entries, `backend/app/main.py`
for the router registration, and `backend/app/access/runtime.py` for the explicit
opt-in — and one was added. This is a closure change, not merely a hash change.

Like candidates.3–.5 and unlike candidate.2, this slice adds routes, and they are
again **outside the wire surface this pack documents**. The 60 captured ASGI
exchanges cover 28 paths and none of them is under `/libraries/*/discovery/`.
Re-capturing all 60 exchanges against the new source reproduced `cases.json` byte for
byte except for the version string, which is the measurement, not an assumption. A
client already tested against candidate.5 needs no rework.

What changed is the default application's **composition**, not its authorization. The
two routes were already reviewed as a candidate capsule and were reachable only
through the standalone `create_candidate()` factory; the default app now registers the
same `discovery_transport` router, and the closed boundary admits exactly those two
method/path pairs bound to endpoint identity as every other entry is. This is the one
deliberate departure from the capsule's original statement that `create_app()` and its
boundary "remain byte-identical" — that sentence is superseded here, and the default
app's live route count moves **46 → 48**.

Mounting a route is not enabling it. `DiscoveryRuntime` is supplied only through an
explicit opt-in: `RuntimeConfiguration.discovery_indexes` defaults to empty, so every
existing deployment keeps its current behaviour, and with no runtime the routes refuse
`503 discovery_unavailable` after the same authorization-first check every other
protected route performs — an unauthenticated caller is refused `401` before the
runtime is even consulted. No index is derived, globbed or inferred from configuration:
the operator-produced artifact is the only source, it is read read-only, and it is
re-validated against the service's own `validate` and index budget before a runtime
exists. Supplying paths is a deliberate operator act, and a missing or malformed
artifact refuses at startup rather than silently degrading to 503, so a
misconfiguration cannot masquerade as "not configured".

The capability is unchanged: both routes are gated on `library.read`, so every
approved role may read them and no new grant is introduced. Responses remain bounded
and no-store, and neither route exposes a face crop, caption, coordinate, path or
anonymous home URL. The pack's `client_profile_defaults` remain off. This reissue does
**not** adopt anything for Android: the two routes are for a later reviewed client
slice, and a native client must not treat them as part of this profile. Candidate.5
was never adopted; this reissue supersedes it as the reviewed candidate and still
requires explicit coordinator adoption.

## Reissue — 2.0.0-candidate.5

`2.0.0-candidate.4` pinned source `99078f1`. Opening the read-only tag catalog to
ordinary library members adds two member-scoped read routes, `GET /tags` and
`GET /tags/{tag_id}/assets`. That slice is the first since candidate.1 to change the
**closure itself**: it adds a new application module, `backend/app/access/tags.py`, so
the pinned `backend/app/**` closure count moves **99 → 100 files**. Two existing
source hashes moved (`backend/app/access/boundary.py` for the two allowlist entries,
`backend/app/main.py` for the router registration) and one was added. This is a
closure change, not merely a hash change — a coordinator comparing file lists will
see a new name, not only different digests.

Like candidates.3 and .4, and unlike candidate.2, this slice adds routes, and they are
again **outside the wire surface this pack documents**. The 60 captured ASGI exchanges
cover 28 paths — accounts, gallery, asset detail, captions, stories, search, members,
invitations, upload and voice — and none of them is `/tags`. Re-capturing all 60
exchanges against the new source reproduced `cases.json` byte for byte except for the
version string. A client already tested against candidate.4 needs no rework.

The two routes are narrower than the retired legacy tag surface they partially
answer, which is worth stating because "read-only" alone would not say so. Both are
gated on `library.read`, so every approved role may read them. The catalog returns
only tags linked to an asset that is active (or status-less) **and** mapped into the
selected library, and each count counts that library's own visible assets — so
another library's tag is neither listed nor countable, and no global total is
revealed. Neither a tag's `type` nor a link's `source` (`cap` / `img` / `cap+img` /
`manual` / `rule`) is returned; legacy `/tags` returned both. A tag with no visible
asset in the library is refused as access denied rather than answered empty, so tag
existence is never confirmed to a non-member. The photo list reuses the gallery's
library-scoped predicate and its asset row, so it introduces no second asset or media
surface. Nothing in either route is writable, and the module contains no POST, PUT or
DELETE at all. The pack's `client_profile_defaults` remain off. Candidate.4 was never
adopted; this reissue supersedes it as the reviewed candidate and still requires
explicit coordinator adoption.

## Reissue — 2.0.0-candidate.4

`2.0.0-candidate.3` pinned source `3797948`. Opening the people directory to
ordinary library members adds one member-scoped read route, `GET /people`, so
`backend/app/access/people.py` (route and service) and
`backend/app/access/boundary.py` (the closed-boundary allowlist entry) both changed
again. The pinned `backend/app/**` closure count is unchanged at 99 files; two
source hashes moved and none were added or removed.

Like candidate.3 and unlike candidate.2, this slice adds a route, and the route is
again **outside the wire surface this pack documents**. The 60 captured ASGI
exchanges cover 28 paths — accounts, gallery, asset detail, captions, stories,
search, members, invitations, upload and voice — and none of them is `/people`,
`/admin/*` or `/faces/*`. Member-visible people browsing is a protected-WebUI
capability, not part of the native client profile. Re-capturing all 60 exchanges
against the new source reproduced `cases.json` byte for byte except for the version
string. A client already tested against candidate.3 needs no rework.

The new route is narrower than the owner one it sits beside, which is worth stating
because "member-visible" would otherwise read as "the owner view, loosened". It is
gated on `library.read`, so every approved role may read it. It returns **only named
persons**, so an unnamed clustering artifact is never exposed; a person with no
active face in the selected library is omitted, so a person owned by another library
cannot surface even when it holds faces in this one; and each row carries a name, a
count and one thumbnail URL pointing at the already member-scoped crop route — no
revision, no rename affordance, no vector, bbox or embedding field. Nothing about
it is writable. The pack's `client_profile_defaults` remain off. Candidate.3 was
never adopted; this reissue supersedes it as the reviewed candidate and still
requires explicit coordinator adoption.

## Reissue — 2.0.0-candidate.3

`2.0.0-candidate.2` pinned source `3d8cc8f`. Closing the two owner-only people
gaps in the protected WebUI adds one protected route, `GET /admin/faces`, so
`backend/app/access/people.py` (route and service) and
`backend/app/access/boundary.py` (the closed-boundary allowlist entry that lets
the route through at all) both changed. The pinned `backend/app/**` closure count
is unchanged at 99 files; two source hashes moved and none were added or removed.

This reissue differs from the candidate.2 one in a way worth stating plainly: the
previous slice added no route, this one does. That route is nevertheless **outside
the wire surface this pack documents**. The 60 captured ASGI exchanges cover 28
distinct paths and none of them is under `/admin/`; operator and owner management
routes were never part of the native client profile. Re-capturing all 60 exchanges
against the new source reproduced `cases.json` byte for byte except for the version
string, which is the measurement, not an assumption. A client already tested
against candidate.2 therefore needs no rework.

The added route is owner-only and default-denied for every other account: it is
reachable only through the closed boundary and requires the existing
`library.people.manage` capability. It grants no new capability to any account that
did not already hold one, and the pack's `client_profile_defaults` remain off.
Candidate.2 was never adopted; this reissue supersedes it as the reviewed candidate
and still requires explicit coordinator adoption.

## Reissue — 2.0.0-candidate.2

`2.0.0-candidate.1` pinned source `4022a57`. The offline suppressed-person
ownership repair adds `backend/app/access/ownership_repair.py` and registers the
new operation in the existing operator planner and apply paths, so the pinned
`backend/app/**` closure moved from 98 to 99 files and two source hashes changed.

That repair is operator tooling only: it adds no route, no migration and no
server response field. Re-capturing all 60 ASGI exchanges against the new source
reproduced `cases.json` byte for byte except for the version string. The wire
contract is therefore unchanged, and a client already tested against candidate.1
needs no rework. Candidate.1 was never adopted; this reissue supersedes it as the
reviewed candidate and still requires explicit coordinator adoption.

## Adoption and evidence

- Default `protected_native_v2`, `protected_photo_display` and
  `protected_story_read` to **false**. These are proposed client build/profile
  flags, not server response fields or authorization grants.
- The coordinator explicitly adopts this exact pack and a reviewed configured
  HTTPS origin. Enable only the implemented client features. There is no server
  version/capability-negotiation endpoint; do not infer compatibility from HTTP 200.
- Keep existing fixture-v1 and anonymous Home/TV clients separate. Never fall
  back to a Home feed, unprotected original URL or legacy route on denial.
- `cases.json` contains 60 real ASGI exchanges against freshly migrated temporary
  synthetic SQLite data. Opaque credentials/accounts and UUIDs are normalized.
  They are example wire cases, not a standalone sequential replay recipe: the
  probe provisions additional synthetic state between requests.
- JPEG bytes are a synthetic fixture. The on-demand renderer is stubbed; routing,
  authorization, file access and original Range handling are exercised. This
  does not prove image decoding, Windows ACLs, native playback or phone acceptance.
- Normalized case headers omit time-dependent cookie expiry and file ETag values.
  Successful native login/register are asserted not to set a cookie. A denied
  session can send a cookie-clearing header; native clients must ignore cookies.
- No live service, database, media, credentials, models or network listener was
  used. The integration owner's separate browser acceptance does not qualify an APK.

Verify pack/source hashes with `python3 scripts/verify_protected_native_contract.py`.
Replay with an existing test environment:
`python -m unittest discover -s tests/security -p test_protected_native_contract.py`.
The verifier has no runtime dependencies, network access or automatic rewrite mode.
See [VALIDATION.md](VALIDATION.md) for the exact test receipt and limitations.

## Account transport

Use the exact configured HTTPS origin and normal certificate/hostname validation.
Native login and registration use `transport: "native"`, no Origin, cookies or
Authorization. Subsequent calls send exactly one `Authorization: Bearer <token>`
and no Origin or session cookie. Never put credentials in URLs. Do not redirect
credentials to a different origin. Account endpoints do not allow query strings.
JSON objects require exactly the named fields, all values strings, UTF-8 without
surrogates or duplicate keys. Account bodies are limited to 2,048 bytes.

| Method/path | Body | Success |
| --- | --- | --- |
| POST `/auth/register` | phone, password, code, transport | 201 token |
| POST `/auth/login` | phone, password, transport | 200 token |
| GET `/auth/session` | none | 200 profile |
| POST `/auth/logout` | none | 200 `{ok:true}`; idempotent |
| POST `/auth/invitations/accept` | code | 200 `{ok:true}` |
| POST `/libraries/{library}/invitations` | phone | owner; 201 code, expires_in |
| POST `/libraries/{library}/invitations/cancel` | code | owner; 200 `{ok:true}` |
| GET `/libraries/{library}/members?page=1&page_size=50` | none | owner; paged members |
| POST `/libraries/{library}/members/{account}/revoke` | revision | owner; 200 `{ok:true}` |

Token response: `access_token` (opaque 43-character value), `token_type:"Bearer"`,
`expires_in:86400`. No JWT decoding, refresh token or refresh endpoint.
Creation passwords: **8–128 Unicode code points**; login accepts **1–128** for
existing credentials. Do not trim/normalize passwords. Count Unicode code points,
not UTF-16 units. Phone is a login label, not proof of phone possession: canonical
explicit `+` country code and 8–15 ASCII digits. The web UI's +86 default is not
an implicit backend country code.

Registration requires a valid unexpired invitation bound to that phone and
library. Failed registration creates no account. Success creates a viewer in
the invited library with no original-media grant. An existing account accepts
another invitation through `/auth/invitations/accept` rather than registering again.
There is no public approval, role promotion or original-grant mutation endpoint.

Profile: `{account_id,phone_login,memberships}`. Each membership has `library_id`,
`status`, `role`, numeric `revision`, nullable epoch-second `expires_at`, integer
`originals` (0/1), and boolean `available`. Use `available`, not merely approved
status. Revoked library membership can coexist with a valid account session.
Owner member-list revisions are **strings**, unlike session revisions; the revoke
request uses a string revision and returns 409 on stale state. Do not infer access
from a cached role. Recheck authorization on every request and discard stale
client state on logout, account/library change and denial.

## Library reads

`library` is required, nonempty, at most **128 characters**. Query bytes are
limited to 1,024. Duplicate/unrecognized parameters are rejected. Asset IDs are
positive signed-64-bit decimal strings; keep them as strings in JSON models.

| GET path | Pagination/result |
| --- | --- |
| `/assets?library=…&page=1&page_size=50` | page 1–100000, size 1–100; library_id, page, page_size, total, originals_allowed, items |
| `/assets/detail/{id}?library=…` | library_id, originals_allowed, asset |
| `/assets/{id}/captions?library=…` | library_id, asset_id, has_more, items |

Asset: `{id,kind,width,height,duration_sec,taken_at,thumbnail_url}`; kind is
image/video/other, dimensions/duration/date may be null. Treat `taken_at` as the
returned string without inventing timezone information. Thumbnail URLs are
relative and remain bound to the configured origin. Gallery/detail/caption
serialization is unchanged from the frozen v1 backend.

Captions: at most 20 ordered rows, at most 8,192 characters per text and
512 KiB for the serialized response. Preserve `truncated` and `has_more`;
there is no caption continuation endpoint. Gallery uses offset pagination with
no snapshot guarantee; deduplicate IDs and refresh after relevant changes.

## Media

| GET/HEAD path | Required access and behavior |
| --- | --- |
| `/assets/{id}/thumbnail?library=…&size=256` | library.read; size 64–1024; cached or configured on-demand JPEG |
| `/faces/{id}/crop?library=…` | library.read and scoped parent; cached crop |
| `/assets/{id}/display?library=…` | library.read; optional protected JPEG display, no original grant needed |
| `/assets/{id}/media?library=…&download=false` | separate originals grant, including videos; full or single Range |

Display requires an explicitly configured PhotoCache; absent/unavailable provider
returns 503. This source's on-demand input support is JPEG/PNG, not arbitrary
phone formats. Treat display as a whole-image response, not a resumable stream.
Keep native image dimensions/decoded-memory limits in addition to wire byte limits.

Original media: 200 full, 206 single range, 400 malformed/multiple range, 416
unsatisfiable range with `Content-Range: bytes */N`. Any If-Range causes a full
200 response. A client requesting a range must handle that without appending
the full file at a partial offset. A weak ETag is not a content-integrity hash.
HEAD does not return a body. Original/media readiness is not implied by listing.
Protected prepared-video playback without an original grant is not implemented.

Authorization and file identity are rechecked before opening media. Revocation
denies subsequent requests; already-delivered bytes cannot be recalled. Missing
authorized files can return 404, storage/provider failure 503, changing photo
source 409. A cached successful response must not override a later denial.

## Family Stories

First Android adoption is **read-only list in asset detail**, not editor/history
or search. Additional routes below are documented for later reviewed adoption.
All use the same Bearer transport and required `?library=…` scope.

| Method/path | Fields/result |
| --- | --- |
| GET `/assets/{asset}/stories[&page=1]` | asset_id, library_id, page, has_more, can_create, items; 5 per page |
| POST `/assets/{asset}/stories` | title, text, language, byline, mutation_id; 201 story |
| PUT `/stories/{uuid}` | same fields plus revision; 200 story |
| DELETE `/stories/{uuid}` | revision, mutation_id; 200 tombstone |
| GET `/stories/{uuid}/history[&page=1]` | story, page, has_more, items; 5 revisions plus current story |
| POST `/library/search` | text, source, media, page; library_id, page, page_size:24, total, items |

Story: `id` (canonical UUID), `asset_id` (decimal string), title, text, language,
byline, author_id, numeric revision/created_at/updated_at, boolean deleted,
can_edit, can_view_history, and `source:"family"`. Times are epoch seconds.
History revision rows instead carry editor_id/occurred_at and integer deleted
(0/1). Respect returned permissions and preserve Family Stories separately from
AI captions; the response is plain text, not trusted HTML.

Viewer: read/list/search only. Contributor: create and edit/history of own stories.
Owner: create/edit/history across the scoped library. Parent asset authorization
applies to every route. The first client can ignore edit capabilities and stay
read-only; it must not infer a write grant from visible buttons or local flags.

Text is nonblank, <=64 KiB UTF-8; title <=512 bytes; byline <=256 bytes. Language
is en/zh/mixed/und. NUL and malformed Unicode are rejected. Create/update request
limit 512 KiB, delete/search body limit 2,048 bytes, serialized story response
limit **3 MiB** (also search/history). Do not reuse the smaller caption parser
budget. Lists contain complete records; no per-text truncation is implied.

Mutation UUID identifies one logical operation. Preserve it and the exact body
on retry. `revision` request is a positive integer **string**. Stale version or
changed-body reuse returns 409; refresh and let the user resolve it. Exact retry
can return the *current*, later story revision, not necessarily the original
response. Delete is a retained tombstone, not erasure. Offset pagination can
shift; deduplicate and refresh. Logout/library switch/hidden app state must not
restore or expose private story data or drafts from an earlier session.

Search is literal SQLite matching, including short Chinese text; it is not
semantic search. Text: 1–160 characters; source all/family/ai; media all/image/video;
page is a string. Items include the asset plus match `{source,id,excerpt}` where
source is family/legacy_family/ai. Deleted stories are excluded. A 2-second SQL
budget can return 503. Stories are not automatically exported to anonymous TV.

## Errors, gaps and implementation order

Use status and operation context, not English error-string matching. Typical
errors: 400 malformed request, 401 missing/expired/revoked or object-scope denial,
403 forbidden transport/closed route, 404 missing authorized media, 409 conflict,
413 request too large, 422 invalid story content, 429 admission limit with
Retry-After, 503 unavailable service/storage. All responses are no-store.
Login and registration share durable admission limits; the captured 429 returns
Retry-After:600. Do not automatically retry passwords or a conflicting mutation.

The pack describes implemented source and exposes limitations; it does not add
authorization, deploy code or certify all routes. Important remaining gaps:

1. Frozen v1 has a 15-character creation policy and no display/Stories adoption.
   Native clients need explicit profile selection, 8–128 creation / 1–128 login,
   128-character library IDs and dedicated bounded Stories parsing. Android's
   current feature branch is addressing these; this pack does not certify it.
2. No refresh/password reset/account deletion/upload/STT/voice native API in this
   profile. Legacy upload and voice stay closed. Owner management routes in this
   source are outside this bounded mobile adoption.
3. Invited viewers do not receive originals or write rights. No normal client
   flow grants contributor/original permissions. Prepared video without an
   original grant requires a separately reviewed contract.
4. Real-device HTTPS/login/photo/story behavior, Windows service-account cache
   permissions and physical video decoding remain separate acceptance gates.
5. Version compatibility is manually configured; mismatched deployment/client
   profile has no automatic negotiation. Reject malformed/oversized responses.

Next: coordinator adopts exact pack; Android tests its fixture/parser against
cases, builds the opt-in profile, then performs a separately authorized user-led
configured-origin journey. Keep private endpoint/account entry outside tracked
fixtures. See [UPLOAD_NEXT.md](UPLOAD_NEXT.md) for the proposed next backend slice.
