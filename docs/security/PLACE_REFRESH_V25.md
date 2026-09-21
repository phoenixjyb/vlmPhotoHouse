# Current-library place refresh — explicit opt-in

The v24 static artifact remains supported. The optional
`--refresh-current-library` switch on `prepare_access_places.py` produces a
`RefreshingPlaceIndex` with `refresh_policy: current-library-regions-v1` and
`region_rules`. No existing artifact changes policy implicitly.

This policy authorizes the specified, immutable geographic rectangles/labels to
be applied to future active assets assigned to this **protected** library. It
must not be used as anonymous Home/TV publication approval. The reviewed rules
are loaded once from the explicitly configured index; there is no file watching,
background job, cache, automatic approval, account write or database write.

For every request, current membership is checked before provider access. Within
the same transaction and shared budget, the service reads current scoped metadata,
recomputes deterministic region membership, and binds the response to that source
digest plus the approved rules. An old search/pagination binding returns 409;
a fresh facets request succeeds with current counts. Clients then explicitly
reapply their search. A newly approved upload needs a valid recorded coordinate
to match a place; missing GPS is not inferred from captions or filenames.

`revision` identifies the approved rule artifact, while `binding` identifies the
current authorized source snapshot. Altering labels/bounds still requires a new
reviewed artifact and explicit reload. Only date/locations/media are supported by
this refresh policy; reviewed people/face assignments are not automatically
carried forward. Partial indexed subsets are refused: opting in explicitly selects
the current active mapped library scope, not a frozen subset of old asset IDs.

## Bounds and resource behavior

Rules are unique place IDs, each present in the place roster, with finite numeric
bounds and nonzero area. Up to128 rules are accepted. West greater than east means
antimeridian crossing. West180/east-180 is rejected as a zero-width region. Both
offline preparation and serving use the same rectangle-membership function.

Current source rows/bytes, materialized region-pair count, effective index size,
response bytes, execution time, cancellation and concurrent operations retain the
existing limits. Exceeding a limit refuses the request instead of returning stale
results. Region bounds are present in the private operator artifact; individual
asset coordinates and rule bounds are not returned by discovery wire responses.

## Operation

```text
python scripts/prepare_access_places.py --database <absolute-db> --library <library> --regions <absolute-reviewed-regions> --revision <new-revision> --refresh-current-library --out <new-absolute-artifact>
```

Use `--audit` separately for aggregate GPS coverage, with no artifact output.
Keep real rule files and artifacts outside the public repository. Qualify the
specific rule count and real library before activation; synthetic timings do not
prove runtime performance. Default deployment configuration and client feature
flags remain unchanged.

Local tests cover newly mapped assets, unassigned/pending/foreign/hidden rows,
GPS/date/scope changes, old bindings, revoked access, strict loading, invalid rules,
legacy identity and growth beyond budgets. Windows qualification is recorded in a
private handoff, separately from source test evidence. No activation is implied
by preparing this source.
