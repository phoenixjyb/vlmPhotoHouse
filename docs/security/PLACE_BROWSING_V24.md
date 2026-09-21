# Browse by place — first source slice

This slice adds named-place discovery, not map/radius search. Secured WebUI and
Android reuse their existing `locations` facets and combined search contract.
A named place can be combined with date and photo/video filters. Counts include
photos and videos; no named place does **not** mean no GPS (coordinates may fall
outside the chosen regions or outside the indexed subset).

## Protected source and scale

An opt-in `ProjectedIndex` artifact carries `projection: enabled-v2`. Its source
projection reads assets and only enabled dependencies: captions for caption,
face assignments for people, tag relations for tags, valid recorded coordinate
pairs for locations. Every request retains current authorization, scope/status,
source digest, revision, binding and pagination-fingerprint checks, under the same
2-second, 100,000-row, 16-MiB source, 4-MiB index and 512-KiB response budgets.

Legacy artifacts remain the original dataclass and projection; their serialization,
binding and wire cases are unchanged. They are not silently upgraded. The old
producer can opt in with `--projection enabled-v2`. Existing all-facet artifacts
still depend on captions/faces/tags; this change does not claim their scale problem
is resolved. No global cache, background refresh, model call or budget increase.

## Read-only coverage and region preparation

Run on the Windows runtime that owns the database, with reviewed local paths:

```text
python scripts/prepare_access_places.py --database <absolute-db> --library <library> --audit
python scripts/prepare_access_places.py --database <absolute-db> --library <library> --regions <absolute-regions-json> --revision <new-positive-revision> --out <new-absolute-index-json>
```

The audit reports aggregate in-scope GPS coverage and writes nothing. Preparation
opens the same direct database read-only, uses a single transaction and does not
read media files. It reports GPS missing/invalid separately from valid GPS outside
named regions. It writes a new artifact exclusively, never overwriting a file or
changing runtime configuration. Errors exclude database rows, paths and coordinates.

Example **synthetic** region input:

```json
{"version":1,"places":[{"id":"601","label":"Example coast / 示例海岸","south":-1,"west":-1,"north":1,"east":1}]}
```

Up to 128 uniquely identified rectangles are accepted. Coordinates are decimal
latitude/longitude in the source GPS reference system; no datum conversion occurs.
Bounds are inclusive; west > east crosses the antimeridian. Overlapping regions
can both match. Missing, nonnumeric, out-of-range and nonfinite pairs remain
unknown. Zero is valid. Region labels and boundaries are explicit operator inputs,
not inferred cities or reverse-geocoded names. Never use caption text as GPS.
Artifacts contain reviewed place IDs/labels and asset associations, not coordinates.
Keep real region definitions/artifacts outside the public repository.

## Freshness and activation

For location/date/media-only v2 artifacts, ongoing captioning, face labeling and
tagging no longer invalidate discovery. Asset membership/status/date/media or GPS
changes still invalidate the artifact: fail closed with 409, refresh the source
artifact at a new revision, and explicitly replace the runtime's configured index.
There is no implicit publisher or recurring task. An approved upload therefore
requires an index refresh before it becomes searchable through these snapshots;
the ordinary gallery remains independent.

Before live activation: run the aggregate audit on the owning host, establish the
intended region names/bounds, prepare and load a fresh artifact, measure actual
full-library facet/search latency and budgets, then explicitly activate the new
package/configuration. Verify signed-in searches, paging, revocation and upload
refresh against that runtime. Local synthetic timings are not Windows evidence.

## TV and home-mode phone

Their anonymous Home contract is unchanged. They use only the selected Home
catalog and its separately reviewed `region_review` in `export_home_discovery.py`.
A protected index is **not** a TV export and must never grant anonymous access.
Populate/approve the existing Home region review against the selected catalog,
then publish through its existing workflow before calling TV places live-ready.
Shared UI improvements do not publish private metadata or media.

## Next slices

A scalable refresh mechanism for source changes, reviewed Home geographic
preparation, and map/area/radius browsing remain separate work. Map rendering must
respect the local-only preference; no third-party tile/geocoding service is wired
in by this slice. People/tag/caption combination remains supported where the
corresponding separately qualified facets are enabled.
