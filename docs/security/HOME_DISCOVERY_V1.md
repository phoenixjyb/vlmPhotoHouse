# Home discovery v1 — synthetic source contract

This optional component searches an explicitly reviewed, immutable metadata file
paired with a visible v2 catalog. It does not export the real database, identify
family members, generate tags, or deploy a listener. Only the synthetic fixture is
available in this slice. Existing phone authentication and v1/v2 applications are
unchanged; this is a separate selected-publication home-LAN surface.

The [contract](home-discovery-contract-v1.json),
[JSON Schema](home-discovery-schema-v1.json), and
[actual ASGI examples](home-discovery-examples-v1.json) are the Android interface.
Use `create_home_discovery(config, index_path, index_sha256)` from
`backend/app/home_discovery.py` for in-process replay. Its dispatcher composes the
two discovery routes with the frozen v2 catalog/media child. Each child enforces
its own reviewed method/handler and direct-peer HTTPS boundary. No discovery
launcher, public route, account bypass, or automatic addition to existing apps is
supplied.

## Client binding and pagination

GET `/home/discovery/v1/facets` accepts `facet=people|tags|locations`, `page`,
`page_size`, and `revision`. Page 1 can obtain the current revision; later pages
must send it. Facets are globally counted over this snapshot, ordered by numeric
ID. The complete `pinned_people` records appear in exact `pinned_person_ids` order
on every facet page, separately from paged items. Pinning does not change a person
filter's semantics. Labels/aliases are server strings; do not compile private
family aliases or guessed IDs into APKs or fixtures.

POST `/home/discovery/v1/search` requires exact JSON with `revision`, `page`,
`page_size`, and `filters`. Categories combine with AND. People and tags each
require explicit `any` or `all`; regions and media match any selected value.
Dates use inclusive capture-calendar bounds, not ingest time. Caption matching is
NFKC plus casefold literal phrase matching, with outer query whitespace removed.
A caption naming somebody never supplies their person assignment. Unknown or
disabled filters fail rather than silently broadening results.

Both replies carry library ID/title and both revisions. Search items have the
unchanged v2 shape, including unavailable media and revision-bound relative media
URLs. Clear stale result/media generations on denial or revision mismatch. Reset
pagination when filters or page size change. Compare both revisions and the
filter fingerprint before appending pages; the fingerprint excludes pagination.
Facet counts are not query-conditioned. Date min/max are observed bounds only;
there are no year/month-count endpoints. Themes/topics explicitly report
`no_reviewed_taxonomy` and must remain unavailable in the UI.

## Metadata review boundary

The file format is enforced by `validate_index`; the synthetic builder shows every
field. The index must bind the exact catalog hash and revision. All indexed asset
IDs belong to that catalog, and all references belong to explicit rosters.
Publication disable revokes discovery and v2 together. Changing index bytes after
admission fails closed; update by a stopped release switch with a new pin.

`reviewed_assignments` and `reviewed_region` are operator assertions requiring
external review. A JSON label cannot prove review. Source inspection found:

- `Asset.taken_at` and GPS may be absent. Ingest `created_at` is not capture time.
- Person display names exist, but there is no canonical bilingual alias schema.
  Face rows and assignment events distinguish manual, automated and system work;
  legacy manual flags alone do not establish a currently reviewed family mapping.
- Captions have model, edit and superseded information. A future exporter must
  define current-caption selection and report missing/oversized captions honestly.
  The index accepts at most 4096 UTF-8 bytes per caption and never truncates it.
- Tags have kinds and association sources. A future exporter must retain
  provenance and honor tag blocks. Person-kind tags never become identities.
- No reviewed theme/topic taxonomy or coarse-location mapping is supplied.
  Raw GPS and caption-inferred places are not exposed by discovery.

Do not import the face audit helper into a read-only exporter: it can create audit
tables. Do not use live operational routes to fill unknowns. Current private family
shortcut requests remain unresolved until explicit IDs/assignments are reviewed;
no actual aliases or live metadata are in this contract.

`index_complete` means row coverage of the paired catalog only. Counts of rows
with values do not prove caption/tag/detection completeness. Missing values may
mean unknown, unpublished, or unindexed. An unindexed asset remains in an empty or
media-only search but cannot match a metadata filter. Real coverage is unverified.

## Bounds and unresolved security limits

The component rejects credentials, unapproved actual peers, wrong Host/Origin,
unknown routes, originals and other legacy surfaces through the existing v2
boundary. This does not repair legacy authorization failures elsewhere; the route
inventory retains those gaps. Anonymous metadata itself discloses names/tags in
the selected publication and therefore requires explicit publication review.
This surface must not be exposed to the public Internet.

Requests are bounded to 16 KiB and replies to 512 KiB. Search actions have two
slots, and the matching loop checks its two-second budget every 512 catalog rows.
Metadata is capped at 128 MiB, with at most 100,000 catalog assets and 5,000 entries
per roster. There is no hard process memory quota. Initial JSON parsing/validation,
facet computation, request-body arrival and response sending are outside the
matching deadline. The action semaphore does not bound slow request-body readers;
it is separate from v2 media concurrency. Native load, slow-client/proxy timeouts,
shutdown draining, and network isolation need operational validation before any
listener is approved. No full-library performance claim is made.

## Reproduce without listeners or real data

Use the isolated CPU access-test environment, not a live application environment:

```sh
python -m unittest discover -s tests/security -p 'test_home_discovery.py' -v
python scripts/security_inventory.py
python docs/security/evidence/home-discovery-v1/replay.py --source-root "$PWD"
```

The replay uses an in-process TestClient and guards socket bind/connect, process
launch and SQLite access. It checks exact captured responses, combined filters,
identity separation, stale revision, library binding, v2 JPEG/MP4 Range, legacy
original denial and shared disable. The schema is Draft 2020-12; validate examples
against the specific `$defs` response/request with format checking. Byte and
cross-field bounds also require the runtime validator.

## Next reviewed implementation

Android can implement and replay this source contract now. The next backend slice
should build a synthetic-tested read-only exporter/review-plan workflow: select a
reviewed visible publication, current captions and unblocked tags; join only
approved person assignments and private alias IDs; use reviewed coarse regions;
report all missing/ambiguous metadata; write a new disabled, hash-bound index.
Do not turn unresolved aliases into assignments. Real-data review, native resource
canary, deployment and physical-TV acceptance remain separate subsequent gates.
