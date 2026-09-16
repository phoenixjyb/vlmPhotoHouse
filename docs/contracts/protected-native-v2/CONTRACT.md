# Protected native profile 2.0.0-candidate.2

Backend source: `3d8cc8f9f5563c3d3c72f20869e4a8cdf4d38642`.
Database migration head: `d8e5b2f7a904`. This is a backend-owned candidate
handoff, not an adopted replacement for the mobile repository's frozen
`contracts/v1` (`1.0.0-fixture.1`, backend `87a60b475b37b1d6873cd977bcb6e7254472da7e`).
The later merged backend `a42147c63cf6a9628899735aa64b18cff1ec619d` also predates
this source. The manifest pins source bytes and all pack payloads independently
of later documentation/test commits. Hashes detect drift; they are not signatures.

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
