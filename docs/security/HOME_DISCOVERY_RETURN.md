# Home discovery v1 — source return

Implementation commit: `54f68427058c45f6bcc5a863cc6d708f5b325e45`.
Branch: `codex/backend-home-tv-feed`. Owned worktree:
`_worktrees/backend-home-tv-feed` in the PhotoHouse workspace. Started from clean
`8c194dc07c845032afb69e46055963ec9f7d8291`. The later evidence commit only adds
this return and verification receipts; the implementation pin remains unchanged.

Android has been sent the exact source, contract, schema, examples and replay
hashes and may implement source-only transport against this pin. The
[interface guide](HOME_DISCOVERY_V1.md), [contract](home-discovery-contract-v1.json),
[schema](home-discovery-schema-v1.json), [examples](home-discovery-examples-v1.json),
[19-file source manifest](evidence/home-discovery-v1/source-inputs.json),
[verification receipt](evidence/home-discovery-v1/verification.json), and
[pinned replay](evidence/home-discovery-v1/pinned-replay.json) define the handoff.

Implemented two explicitly composed discovery routes over reviewed, hash-bound
metadata: paged people/tag/region facets with ordered bilingual shortcuts, and
combined people/date/location/media/tag/caption search. Both responses bind the
v2 library and catalog revision. Frozen v2 media handlers and contract are byte
unchanged. There is no real metadata exporter, configured origin or deployment.

Verified locally:

- 16 discovery tests passed in 5.751 seconds.
- 78 combined home tests passed in 114.586 seconds, zero skips (18 v1, 24 v2,
  20 preparer, 16 discovery).
- 19 inventory tests passed in 7.627 seconds; inventory complete at 162 entries.
- Draft 2020-12 schema and five actual ASGI examples passed format validation.
- All 19 manifest files matched their implementation-commit Git blobs. An isolated
  extraction replay passed 11 guarded ASGI checks without any network listener.
- Private aliases were excluded from the new public runtime/fixture/contracts/tests.
  Diff whitespace checks passed. Guide and return Markdown were rendered to HTML
  and checked for structure and local-link targets.

An early clock-mocking test stalled TestClient and was interrupted. The test was
fixed to patch the discovery-local clock and the complete final suites passed.
That failed attempt is retained in the receipt. TestClient emitted a dependency
deprecation warning; this slice did not change serving dependencies.

Security and delivery gaps remain explicit. Reviewed-person provenance requires
actual review; aliases have no resolved public IDs. Missing metadata is unknown,
not proof of absence. Themes/topics have no reviewed taxonomy. Index row coverage
is not model/caption/tag completeness. Legacy authorization failures outside this
isolated application remain inventoried. Memory and slow-client limits, native
performance, publication freshness, real-data export review, Windows deployment
and physical-TV acceptance remain open. No live health claim is made.

No Windows access, real database/media read, indexing, models, service changes,
port exposure, mobile/shared-contract edits, push or merge occurred in this slice.

Next: Android should finish strict parsing, stale-generation handling, paging,
remote focus and large-font tests against the synthetic contract. The next backend
proposal is a synthetic-tested read-only export/review workflow that preserves
caption/tag provenance and accepts only reviewed private identity/region mappings,
writing a new disabled snapshot. Real-data operation and deployment remain
separate reviewed steps; this return is not permission to perform them.

Changed implementation files:

- `backend/app/home_discovery.py`
- `scripts/build_home_discovery_fixture.py`
- `scripts/security_inventory.py`
- `tests/security/test_home_discovery.py`
- `tests/security/test_inventory.py`
- `docs/security/route_capabilities.json`
- `docs/security/home-discovery-contract-v1.json`
- `docs/security/home-discovery-schema-v1.json`
- `docs/security/home-discovery-examples-v1.json`
- `docs/security/HOME_DISCOVERY_V1.md`
- `docs/security/evidence/home-discovery-v1/replay.py`

Evidence files: this return, `source-inputs.json`, `verification.json` and
`pinned-replay.json` in the discovery evidence directory above.

2026-09-12 follow-up: [Android integration review receipt](evidence/home-discovery-v1/android-v6-review.json)
and [next export/publication readiness plan](HOME_DISCOVERY_PUBLICATION_PLAN.md).
The plan records unmeasured real coverage and unresolved private identity review;
it does not authorize real export or deployment.
