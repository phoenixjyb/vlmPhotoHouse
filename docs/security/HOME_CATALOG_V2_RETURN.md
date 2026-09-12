# PH-BACKEND-HOME-CATALOG-V2-01 — verified source return

The separate full-catalog v2 API is frozen for Android synthetic integration.
**No live v2 origin or real-media publication exists yet.** The running v1 feed and
mapped v3 APK remain the working pilot. Android has received the exact pin,
contract, examples, media fixture and remaining server gates.

Worktree: `_worktrees/backend-home-tv-feed` within the PhotoHouse workspace.
Branch: `codex/backend-home-tv-feed`. Starting HEAD:
`af8f219efa84162ee3f32f57dddc7914c5678a79` (clean).
Implementation pin: `a5d0f595d7cd26379ed2845a944ec1d58d7885cc`.

Implementation commits:

- `3637857`: independent paged catalog, prepared JPEG/MP4 Range API, exporter,
  fixture builder, standalone launcher, exact contract/schema, tests and inventory.
- `a5d0f59`: materialize the 24,336-byte generated MP4 as a normal Git blob.
  The first packaging check caught an LFS pointer despite the new file-specific
  attribute; explicit renormalization fixed it. All 16 pinned input hashes then
  matched committed bytes, and replay ran only those extracted inputs.

The final evidence-only commit containing this return does not change the runtime
pin above. No push, merge, main-branch update or other worktree edits occurred.
The preserved original checkout was observed clean on
`codex/infant-care-caption-policy` at `9ebcec3ef30ba887c3582420725b81aead80b9fb`;
it was not switched or changed.

| Artifact | SHA-256 |
| --- | --- |
| [Contract/schema v2](home-catalog-contract-v2.json) | `13cf10892dc4e91631ad71b5ee4bed21baa44697f1e779851c19026dbe606120` |
| [Response example](home-catalog-response-v2.example.json) | `2cde48dd6de163e9fb0f78baf6de14e4da5bcdf12ce9d3830681d91dc4f109f9` |
| `backend/app/home_catalog.py` | `467b7fc9bcd04e07ff0578a4f4fe80a453d949fc850372986444c36c0592ab40` |
| Generated synthetic MP4 | `5ab7d5d27cc6b3f557068ce21cc07e332939ae92f8240233b5eb087c1012afe8` |

The [guide](HOME_CATALOG_V2.md) describes exact operations, preparation obligations,
lifecycle and failure behavior. [Source hashes](evidence/home-catalog-v2/source-inputs.json)
and [verification receipt](evidence/home-catalog-v2/verification.json) retain the
checks and their boundaries.

Validation:

- Full security suite: **318 passed** in 39.928 seconds before final resource
  cleanup and three extra focused tests. Final catalog/export/launcher suite:
  **24 passed** in 0.519 seconds. These are separate runs, not 342 distinct tests.
- Independent pinned-blob [ASGI replay](evidence/home-catalog-v2/pinned-replay.json):
  **12 passed**; real sockets, subprocesses and SQLite prohibited. Exact response,
  JPEG/MP4, Range/HEAD, stale revision, disable and peer rejection checked.
- Route inventory: **160 method/path entries**, complete. Five v2 operations have
  a separate capability restricted to the v2 factory; protected/v1 exceptions
  cannot inherit it. Inventory does not implement or prove authorization alone.
- Draft 2020-12 schema and example validated using temporary jsonschema 4.26.0
  tooling. The synthetic video passed independent ffprobe and complete decode to
  null. No runtime dependency was added; Markdown HTML structure and local links
  checked. A Starlette TestClient deprecation warning remains, with no test failure.
- Frozen v1 implementation, launcher and contract are byte-identical. Protected
  phone pin remains `87a60b475b37b1d6873cd977bcb6e7254472da7e`.

Read-only Windows findings: **27,842 visible assets** (23,599 photos / 4,243 videos),
364 hidden excluded, zero saved draft albums. Registered sizes are approximately
82 GB photos and 564 GB videos. Latest-200 stat sampling and four header probes
are bounded samples; 8K HEVC and MOV data tracks require preparation. Caption/API
process identity and start times matched the prior pilot; v1/DNS tasks remained
running. No caption-progress, GPU or complete service-health claim is made.

Remaining gaps: real preparation validator and coverage; live v2 origin and a
v1-compatible deployment plan; Windows media-path/stream checks; guest/WAN
isolation; physical real-photo/video playback. Offline snapshots do not follow
live hide/import changes automatically. Legacy web original routes still lack
principal/membership checks and must remain outside the TV/protected boundary.
No account/device revocation is provided for the anonymous LAN feed; proxy/SNAT,
slow clients and already downloaded content remain limitations. The user-reported
JMGO connection/striped-image render is a separate bounded physical observation.

Next: implement a resumable, resource-bounded offline preparer with synthetic
coverage; validate one real photo and one representative video in a new owned
publication, measure CPU/disk/caption continuity, then review the compatible
serving arrangement before expanding preparation. Android may now wire the exact
v2 catalog and Range adapter while retaining v1. No blanket transcode/copy of the
real library is part of this completed slice.

Changed files (relative to the worktree):

- `.gitattributes`
- `backend/app/home_catalog.py`
- `docs/security/HOME_CATALOG_V2.md`
- `docs/security/HOME_CATALOG_V2_RETURN.md`
- `docs/security/HOME_TV_BACKEND_READINESS.md`
- `docs/security/evidence/home-catalog-v2/catalog-inventory.json`
- `docs/security/evidence/home-catalog-v2/pinned-replay.json`
- `docs/security/evidence/home-catalog-v2/replay.py`
- `docs/security/evidence/home-catalog-v2/source-inputs.json`
- `docs/security/evidence/home-catalog-v2/verification.json`
- `docs/security/evidence/home-catalog-v2/video-sample.json`
- `docs/security/home-catalog-contract-v2.json`
- `docs/security/home-catalog-response-v2.example.json`
- `docs/security/route_capabilities.json`
- `scripts/build_home_catalog.py`
- `scripts/build_home_catalog_fixture.py`
- `scripts/home_catalog_app.py`
- `scripts/security_inventory.py`
- `tests/security/fixtures/home-video.mp4`
- `tests/security/test_home_catalog.py`
- `tests/security/test_inventory.py`
