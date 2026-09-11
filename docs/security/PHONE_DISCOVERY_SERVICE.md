# PH-PHONE-DISCOVERY-SERVICE-01 — internal protected service

This implements the service-only step from the
[phone discovery proposal](PHONE_DISCOVERY_CONTRACT_PROPOSAL.md). New modules are
`app.access.discovery` and `app.access.discovery_provider`. Neither is imported
by the application entry point or mounted at an HTTP path. These internal Python
types/results are **not a frozen wire schema**. Existing phone, TV, media,
constructor/runtime and migration source files remain unchanged.

## Authorization and trusted review inputs

Construct `DiscoveryReads(access, provider, shared_budget)` with the existing
`AccessService`, an explicitly supplied provider and one shared `ReadBudget`.
Use a dedicated SQLite connection for each service invocation; the budget owns
its progress callback during the operation and removes it on exit. Do not share
one connection across concurrent calls. The implementation never opens a database
or loads an index/media file, and has no live/default path or configuration source.

Every call enters the existing service-owned read transaction and checks current
`library.read` policy **before provider lookup or scoped metadata reads**. Current
session/account/membership/library denial remains `AccessDenied`. Being an owner
of another library or a global operator does not bypass membership. No session,
index, consistency binding, LAN route or media preview implies an original grant.

`MemoryIndexProvider` holds explicitly supplied immutable dataclasses. No producer,
loader, API for accepting review records, database bootstrap or automatic approval
is provided. `ReviewedIndex` binds one protected library, a revision, the full
visible mapped asset-ID set, a metadata-row subset, a scoped source digest, reviewed
people/aliases/pin order, explicit manual face evidence and coarse regions. IDs
are canonical positive decimal strings through `2^63-1`. Native asset summaries
retain image/video/other kinds and library-qualified authenticated thumbnail URLs.

Every roster/place record declares its library. Face evidence must match the
current scoped face ID, asset ID, person ID and manual source exactly. A manual
marker alone is not enough: it also needs explicit trusted assignment approval.
DNN rows and caption mentions never become reviewed people. A person with no
approved matching assignment is refused unless `allow_zero=True` explicitly
approves that record for this library's zero-result roster. Pin order is independent
of paged facet order. All records and counts are library-scoped; no global person
roster is queried. Reviewed provider assertions require external operator review;
frozen dataclasses do not prove consent or prevent a malicious trusted provider.

The enabled tuple is an explicit reviewed capability selection. To publish no
region capability, supply no regions/places and omit `locations`. A zero count for
an enabled filter does not imply complete metadata or a confirmed negative.

## Freshness and results

Fixed read queries join every asset/child table through current
`access_asset_libraries` and active/legacy-null status. In one transaction the
service materializes a bounded source projection and compares it with the trusted
index's scope and digest. Changes to visible membership of the asset set, eligible
caption contents/flags, tag definitions/associations/blocks, face assignments or
recorded date material invalidate discovery before counts or results return.

The source digest is over that **bounded semantic projection**, not every byte in
the database. SQL uses BLOB byte lengths to select complete text values only when
they fit the relevant cap; it never uses a truncated text prefix as valid metadata.
Full captions up to 4096 UTF-8 bytes, tag names up to 256 bytes and recorded dates
up to 64 bytes include embedded NULs in their materialized value, so validation
rejects them rather than hiding suffixes. Oversized values become unavailable,
with source lengths retained where relevant. Valid dates are returned exactly;
invalid/oversized native timestamps become null. Oversized caption candidates
remain conservative ambiguity evidence, never silently dropped to select a fallback.
Changes within eligible values invalidate the digest; byte changes within excluded
oversized values of equal length need not, because they cannot introduce displayed
or searchable metadata. Raw GPS, paths, model fields and unrelated library rows
are not projected. Real index preparation/freshness remains a separate task.

A binding includes policy version, library, current session digest, account,
membership revision/original flag and the full reviewed index. It is a consistency
check, never authorization. Account/session/index or approved-membership revision
changes invalidate old queries. Every search and later facet page requires the
binding. Results sort by numeric asset ID descending; ordinary gallery ordering
is untouched. Facets sort by numeric ID ascending, returning all ordered pinned
people separately. Counts are snapshot-wide, not conditioned on a search.

People/date/caption/tags/coarse locations/media filters use AND across categories.
People and tags require Any/All; regions and media accept Any. Dates use inclusive
nullable calendar bounds and never infer from ingest time. Caption matching is
NFKC/casefold literal phrase matching. A sole eligible edited caption takes
precedence; otherwise only a sole eligible caption is selected. Ambiguous,
superseded, blank, invalid or oversized captions are excluded. Blocked/duplicate tag
associations are excluded; known sources and unknown provenance remain distinct.
Person-kind tags remain tags. Themes/topics are explicitly unavailable.

Missing metadata does not match that active filter. Empty or media-only searches
can include unindexed visible assets. Coverage distinguishes catalog/index rows
and each enabled field's values/missing values. Metadata and tag-generation
completeness remain unknown. Date bounds are observed min/max, not year facets.
No response contains face crops, captions, coordinates, file paths or anonymous
home URLs. `originals_allowed` reflects current membership only; there is no grant.

The internal fingerprint binds normalized filters, context **and page size**.
Later result pages require it; altered filters/page size or stale context refuse
instead of silently appending another generation. HTTP field names, status/error
mapping, media capability expansion and client lifecycle integration are not
implemented or frozen here.

## Limits and cancellation

Default shared budget: two concurrent calls; two seconds cooperative wall time;
100,000 source rows in total; 16 MiB serialized source projection; 4 MiB reviewed
index; 512 KiB encoded internal response. Queries use 128-row fetch batches and a
SQLite progress callback. Facet/result loops poll deadline/cancellation; busy,
invalid, stale, unavailable and cancelled calls raise distinct internal exceptions
with fixed messages. No partial result or unfiltered fallback is returned. Slots,
progress callbacks and transactions are released on failure.

At most 5000 people/places, 32 pins, 8 aliases/person, 256 UTF-8 label bytes and
128 alias bytes; at most 20 selected IDs/category, 512 UTF-8 caption-query bytes,
100 items/page and a 16 KiB encoded filter object. Exact final HTTP body handling
is deferred. The trusted provider must be memory-only/nonblocking in this slice.
There is no hard process RSS quota or preemptive timeout on provider/SQLite lock
wait/driver allocation/JSON serialization. Dedicated connections should have
reviewed busy timeouts; native resource/large-library acceptance remains open.
Admission is shared only when the future owner supplies the same budget across
instances; no hidden global runtime or multi-process limiter is introduced.

## Revocation evidence and its limit

Synthetic two-connection WAL tests commit revoke, hide and remap changes after the
reader's authorization snapshot is established. That already-admitted read may
finish against its authorized snapshot, matching current policy semantics. The
next request refuses: access denial for revocation, stale discovery for hide/remap.
The service does not claim recall of returned bytes or instant cancellation of a
previously admitted request. Cooperative cancellation is a separate caller signal.

Transport and clients must still cancel work and clear private data on logout,
background, library/session changes and denial; drop late completions; clear stale
searches and require explicit Apply after refreshed metadata. This service provides
binding/refusal and cancellation primitives, not those HTTP/UI behaviors. Each
later thumbnail/original/Range request must use its existing protected policy.
Prepared viewer video/display routes still need a separate authorization design.

## Synthetic verification

Run with the existing isolated CPU access-test Python:

```sh
python -m unittest discover -s tests/security -p 'test_phone_discovery.py' -v
python docs/security/evidence/phone-discovery-service/replay.py --source-root "$PWD"
```

The fixture lives under tests only, builds fresh synthetic accounts/memberships
and two libraries, then constructs an explicit reviewed in-memory index. Tests
cover authorization-before-provider, all six filters, Any/All and Unicode, full
64-bit identifiers, counts/alias scope, missing/blocked/ambiguous data, binding
replay, budget/cancellation, unchanged DB bytes and the WAL interleavings. Guards
block network/process/file access during memory-service tests. The separate WAL
test intentionally uses a temporary synthetic SQLite file; no real input is read.
The replay returns hashes of internal results with `wire_contract_frozen=false`.
Do not distribute those internal JSON results as a new Android contract.

Next: independent source review, then a separately reviewed HTTP/schema capsule
with exact route/handler inventory, native bearer and browser cookie/CSRF handling,
bounded JSON/error mapping and producer/client replay. All frozen runtime pins
remain valid; no endpoint exists for Android to call yet. No original permission
is added to simulate TV media parity. Real data/provider loading, Windows access,
credentials, network exposure, deployment and installation remain outside scope.
