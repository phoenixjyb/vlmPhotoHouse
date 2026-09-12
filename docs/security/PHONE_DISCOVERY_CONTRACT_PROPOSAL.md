# PH-PHONE-DISCOVERY-CONTRACT-PLAN-01 — integration proposal

Status: proposal for Android/coordinator review, **not a frozen schema or an
implemented endpoint**. Backend base: `3080c9cae90efab373fc0c0a218211c615020e92`,
branch `codex/backend-home-tv-feed`. Current protected phone contract remains
`87a60b475b37b1d6873cd977bcb6e7254472da7e`. All ten pinned backend input files
were compared with that Git commit and the mobile manifest; hashes match.
[Source review receipt](evidence/phone-discovery-plan/source-review.json).

## Current protected behavior

`access/transport.py` authenticates native bearer requests and browser session
cookies through the same `AccessService`. HTTPS/Host and same-origin browser
signals are checked; mixed cookie/bearer credentials fail. Browser POSTs require
CSRF. Registration is invitation-bound, and phone numbers are login labels, not
identity proof. A successful session is not a library grant.

`AccessService._require(..., 'library.read')` checks current session/account,
approved and unexpired membership, and active library. `LibraryReads` performs
that check and the scoped asset query in one SQLite transaction. Its source join
is `access_asset_libraries` plus active/legacy-null asset status. An asset has one
explicit library mapping in this schema. Parent checks also guard captions and
media; global person/tag tables are not a substitute for this scope.

The native contract has scoped gallery, detail, captions, cached thumbnail and
original/media reads. Gallery is ordered by capture time then asset ID and has no
discovery generation token. It does not offer people/tag/place search or a scoped
shortcut roster. `ClosedBoundary` keeps search/albums and unknown handlers closed.
The same path/method must also match its reviewed handler identity.

`/assets/{id}/media` is the **original** path, requiring `media.original.read`,
including video Range access. Viewer membership alone does not grant it. Existing
thumbnails do not establish high-resolution prepared-photo/video support. Phone
UI parity must respect those capabilities rather than adding original grants or
routing through anonymous TV endpoints.

## Recommended protected discovery model

Add a new, explicitly enabled protected discovery service under the existing
account/library policy. Use a separately reviewed, library-bound metadata index
and an authorization check on **every** facets/search request. LAN reachability,
TV publication status, cached credentials, an index digest, or a pagination token
must never act as authorization. Do not mount `create_home_discovery` inside the
protected app or let phone clients fall back to `/home/*`.

Proposed routes for later contract review:

| Proposed operation | Intended behavior |
| --- | --- |
| `GET /libraries/{library_id}/discovery/v1/facets` | Initial capabilities/binding, ordered shortcuts, one bounded page of people/tags/regions |
| `POST /libraries/{library_id}/discovery/v1/search` | Explicit filter body plus expected binding and bounded page selection |

These are suggested names only. Do not add routes, OpenAPI, shared fixtures or
client transport yet. Keep existing phone responses unchanged. Path encoding and
exact field/error names need joint review before freezing. A browser consumer
uses the same protected routes and cookie/CSRF rules, not a second weaker service.

Proposed semantic contents of replies:

- Explicit protected library ID and optional reviewed display title; the current
  `access_libraries` table has no title. Never infer a title from TV configuration.
- A server-issued opaque discovery binding, with capabilities and honest coverage.
  The client treats it as opaque. Server comparison binds current library,
  principal/session context, membership revision, reviewed index revision/hash,
  scoped visibility set and policy revision. It is a consistency token only.
- Ordered `pinned_person_ids` and complete matching records independent of paged
  facets, with server-defined bilingual labels/aliases. No compiled household names,
  order-based identity inference, phone-number labels or face crops. Only explicitly
  approved library roster records may be exposed, including intentionally pinned
  zero-result people. Never expose foreign-library names or global person counts.
- Bounded facet pages, counts scoped to the reviewed library snapshot, and a stable
  result count/page/has-more description. Search results should reuse the protected
  phone asset summary semantics: string decimal IDs, image/video/other kinds and
  authenticated library-qualified thumbnail URLs. No `/home` URL, filesystem path,
  raw GPS, embedding, raw caption dump or automatic original permission.

Use lossless canonical decimal strings for asset/person/tag/region identifiers,
consistent with native asset IDs and the protected positive SQLite 64-bit range.
The TV contract's 31-bit numeric IDs and photo/video/unsupported names are not
wire-compatible. Do not silently coerce large IDs through floating-point JSON.
Exact bounds and type mappings require schema review; no current pin is widened.

## Filter semantics to reuse

Reuse the reviewed meaning of the TV model, with an explicit protected adapter:
AND across categories; people and tags have Any/All; media and regions allow Any;
recorded capture dates have inclusive nullable bounds; caption search is NFKC plus
casefold literal phrase matching. No regex, semantic/vector model, automatic
translation, geocoding or generated query syntax. Proposed limits remain at most
20 IDs/category, 512 UTF-8 bytes of caption query, page size at most 100 (default
50), 16 KiB body and 512 KiB encoded reply. Reject excess, duplicate fields,
unknown filters/IDs and unsupported capabilities rather than dropping filters.

People match only approved current asset/person assignments, never caption
mentions or person-kind tags. Alias-to-person review and asset-assignment review
remain separate. Captions use a reviewed current-variant selection rule; ambiguous,
missing and oversized values stay explicit. Tags honor blocks and retain manual,
caption, image, combined, rule and unknown provenance. Regions are reviewed coarse
IDs/labels; missing locations stay unavailable. Themes/topics remain disabled
until a reviewed taxonomy exists. Named albums are a separate feature/contract.

Facet counts describe the bound library snapshot, not search-conditioned counts.
Date min/max do not imply year/month bucket counts. Zero/partial index coverage
and values missing from metadata must not be described as absence of people or
completion of caption/tag jobs. An unindexed asset may appear in an empty or
media-only search but cannot match an active missing-metadata filter.

## Authorization, freshness and pagination

Recommended first implementation favors predictable refusal over serving a stale
snapshot. The trusted index provider must explicitly bind an access-library ID,
reviewed roster/assignment scope, and the complete visible mapped asset-ID set for
that snapshot; metadata rows may cover a subset. An anonymous export's library
label or approved audience cannot automatically populate this protected mapping.
No global index, filesystem auto-discovery or fallback to a different library.

Within one short bounded read transaction:

1. Authenticate current session and call shared `library.read` policy for the
   requested library **before metadata, counts, roster or index availability is
   disclosed**. Unauthorized/missing/closed libraries retain non-enumerating
   protected-resource denial, currently 401. Do not return 409 or differing
   capability errors first to reveal a library's existence.
2. Compare the trusted index's exact library mapping and visibility-ID set with
   currently mapped active assets in that same SQLite snapshot. If an asset was
   hidden, removed, remapped or added, refuse stale discovery until a new matching
   reviewed index is available. This intentionally costs availability; no stale
   index row/count may escape. Refreshing the index must not silently approve new
   person assignments or metadata disclosure. Also compare approved assignment
   evidence and a scoped source digest for selected captions/tags/blocks/dates
   against the current read snapshot; a changed association or blocked tag must
   not persist until an arbitrary index refresh. There is no existing universal
   metadata generation counter to assume. The first bounded service should
   compute/compare that digest from explicit scoped metadata; a later optimized
   revision mechanism needs separate review. External reviewed regions/aliases
   are bound by the trusted provider's approved revision/hash.
3. Compare the client's expected binding after authorization. A still-authorized
   stale query gets a distinct proposed 409 refresh-required result without old
   counts/items; revoked/expired access stays denial. All facet pages after the
   first and every search require the binding. Compute counts, filters and result
   metadata from the same authorized snapshot. No per-item queries outside scope.
4. Proposed result order is asset ID descending for deterministic discovery;
   existing gallery ordering remains untouched. Bind the normalized filters and
   both scope/index revisions in a result fingerprint. Changing filters or page
   size resets page 1; no mixed-generation append. For the first bounded version,
   page numbers are acceptable with immutable binding; do not silently retry an
   old query against a new generation.

Membership changes that remain approved still change the binding. Re-login/session
replacement and library switching create a new client generation. Counts or
choices from one account/session must not be reused by another even if library IDs
match. No query or authorization state persists by default. On logout, background,
disconnect, 401/403, invalid response or TLS failure, cancel requests/player reads,
clear query/results/facets/media and ignore late completions. On 409, clear the
old search, reload facets and require explicit Apply rather than auto-replaying.
429 uses bounded Retry-After and 503 is unavailable; neither permits unfiltered
fallback. No tokens/search text in URLs, analytics, debug logs or durable caches.

As with current protected reads, an already-authorized in-flight request may finish
from its transaction snapshot. Downloaded bytes cannot be recalled. Every later
request, including thumbnail/original/Range, reauthorizes through its protected
media path. This proposal adds no signed public links or absolute zero-latency
revocation claim. Response/cache privacy headers and same-origin web checks remain.

## Reuse and separately required work

| Reuse | New work that cannot be assumed |
| --- | --- |
| Existing session/membership/library policy and transport privacy rules | Protected discovery service, reviewed handler registration and inventory entries |
| Filter meanings, provenance/exclusion rules, alias order, coverage vocabulary | Protected index envelope and mapping review; 64-bit string IDs and native asset shape |
| Offline deterministic review/export concepts and synthetic adversarial fixtures | Safe protected index ingestion, freshness/revision source and rebuild policy |
| UI editor, Apply/Cancel, result/media lifecycle patterns | Native authenticated gateway, CSRF-aware web gateway and lossless adapters |
| Current authenticated thumbnail/original authorization | Prepared display/video routes for viewers without originals; separate capability and Range design |

Do not refactor the frozen home runtime just to share code. Initially implement
small pure normalization/matching helpers or an explicitly reviewed adapter in new
protected code, tested for semantic parity. The account `_body` helper is capped
at 2 KiB and accepts only string fields; it cannot simply parse nested discovery
filters. A new bounded parser belongs in a later HTTP slice. Search admission,
initial index load, memory and slow-body/response deadlines also need explicit
bounds; TV's action semaphore alone is insufficient for authenticated load.

## Smallest next capsule — PH-PHONE-DISCOVERY-SERVICE-01

Proposed next work, not authorized by this document: add a service-level protected
`DiscoveryReads` plus a trusted synthetic index-provider interface and focused
in-memory/temporary-SQLite tests. No new HTTP routes, DB migration, wire freeze,
mobile edits, live snapshot, model or listener. Existing constructor/runtime and
all frozen source files remain unchanged; a new service may use the shared policy
object in one transaction without opening nested transactions.

Implement scoped facets/shortcut records and all six filter categories against a
small synthetic index. Require live synthetic session/account/membership/library
policy and complete scoped visibility binding on every call. Return internal
Python results suitable for later schema review. Set explicit row/byte/time and
concurrency budgets with honest cooperative vs hard limits. No arbitrary global
person/tag enumeration or database writes during queries. Acceptance is positive
semantic parity plus these negative cases:

- No/malformed/expired/revoked token; disabled account; requested/rejected/revoked/
  expired membership; closed/missing/foreign library; ordinary operator or owner
  of another library. Prove denial before reading the index or counts.
- Forged library/index binding; foreign-only roster/tag/place/asset IDs; hidden,
  deleted, remapped or newly added asset; changed person assignment, caption or
  tag block; stale index and stale membership revision.
  Test counts and zero-result shortcuts, not just result IDs, for cross-library leaks.
- Two authorized accounts or sessions exchanging bindings; late responses after
  logout/library switch; concurrent revoke/hide/remap between requests. State
  precisely the already-admitted transaction behavior and deny the next request.
- Caption-only person mentions, DNN-only assignments, blocked/duplicate tags,
  ambiguous captions, missing dates/regions, unindexed rows, unknown capability,
  Any/All and cross-category AND. Test Unicode literal matching and malformed IDs,
  dates, booleans, duplicate selections, oversized text and 64-bit boundaries.
- Zero/partial/full coverage; inconsistent page totals/revisions/fingerprints,
  page-size changes, replay of a stale page, budget/cancellation failure. Assert
  no unfiltered/anonymous fallback, originals grant, SQL write, model or file read.

Follow-up after integration review: a separate HTTP/schema capsule adds exactly
reviewed routes with native bearer and browser cookie/CSRF negative tests,
shadow-handler/unknown-route denial, exact JSON parsing, response budgets and
request cancellation. Only then freeze a new opt-in protected discovery contract,
repin the relevant clients and add actual producer/client ASGI replay. Prepared
photo/video parity for non-original viewers remains a separate protected-media
capsule; current phone UI work can proceed locally behind existing capabilities.

## Is TV ready to test against real albums?

Saved evidence supports synthetic TV feature tests and a previously configured
v1 selected-feed pilot. It does **not** establish full real-album discovery. The
v6 home-profile APK is still v1 with discovery disabled; the v2/discovery APK has
no configured origin. Existing v6 APKs predate the provenance-label correction.
The Android exporter bridge at `838d392861a474ad8b9e2faf0994f35f26b085cd` reports
82 JVM tests and six actual-ASGI responses parsed by Kotlin; it is test-only and
adds no deployed service or APK configuration.

Remaining blockers are concrete: no approved coherent real metadata snapshot;
seven unresolved reviewed person IDs/assignment scope; no measured actual
caption/tag/date/place coverage; no reviewed real discovery publication; incomplete
and unmeasured prepared photo/video coverage; no approved deployed same-origin
v2+discovery service/profile; no configured discovery APK installation or physical
remote/playback/revocation acceptance. Named albums themselves are not implemented
by the discovery contract. Do not claim that all album UI exists because a
catalog/search result can be displayed.

The current live v1 service/DNS health was not queried. Keep that path and its
rollback artifacts intact; testing an existing v1 APK is a narrower test than
real-library discovery and still requires current connectivity and installation
authority. No Windows, real data/media, private mapping resolution, credentials,
ports, deployment, restart or device action occurred for this proposal.

Integration decisions still open: proposed route/field/error names, protected ID
encoding and title source, exact trusted-index storage/revision mechanism, maximum
library size and stale-index availability policy, media derivative capability and
contract, safe real snapshot/rebuild cadence, and actual deployment/device evidence.
