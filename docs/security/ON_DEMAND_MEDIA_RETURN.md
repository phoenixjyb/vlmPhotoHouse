# On-demand delivery implementation return

13 September 2026 — local source and synthetic validation only.

Branch: `codex/media-on-demand-pipeline`, isolated from
`11c8aa8d9cf54175918d8959aa2f9cb5317cb2e8`. All earlier worktrees were preserved.
Implementation commits: `ebd4c0d058f2b8af3ae9b185cb6268303cddb93f` and
`f131c3edfb55092df6ce8a85e7a520fb5515c011` (final producer source pin).
Matched Android application source: `e9ce77b2ed068bd734b1098366043c543ab1cf46`,
branch `codex/android-on-demand-media`, TV v11 and phone v5.

## Result

- Selected JPEG/PNG originals can be indexed without re-encoding and advertised
  before previews exist. Original byte equality, Range/HEAD, changed-source and
  publication-disable behavior are covered by synthetic HTTP tests.
- Grid/display JPEGs are generated only when requested, with a bounded, explicitly
  owned private cache and one guarded worker. Corrupt cache entries regenerate;
  foreign directories are refused. Originals are preserved.
- Conservatively probed original H.264/AAC MP4 can stream without a new encode;
  compatible prepared v2 media remains preferred. No extension-only video claim.
- Protected phone/web thumbnails can be generated on misses. New protected display
  images use library membership without granting originals; admission is repeated
  after rendering, including revocation during the worker interval.
- Explicit TV and protected-phone launcher switches, route inventory and staging
  package closure are included. Existing protocols/default runtimes stay separate.

## Verification

- Full security suite: **480 tests, zero failures/errors**, 132.346 seconds, at
  `ebd4c0d058f2b8af3ae9b185cb6268303cddb93f`.
- Final producer follow-up: **15 on-demand + 5 protected photo tests**, all passing,
  after the descriptor-stat snapshot refinement in `f131c3e`.
- Source inventory: **171 method/path entries**, 25 in the protected application.
  New original delivery is a separate explicit capability and application.
- Python syntax validation; deterministic staging package tests included in the
  full suite. Tests used the existing disposable Mac Python 3.14 environment,
  FastAPI 0.135.2 and Pillow 12.1.1; this is not Windows runtime validation.
- Android independently checked all 16 producer source blobs and the exact v3
  synthetic response, and replayed the unchanged v1 contract's 38 synthetic cases.
- No live database/media reads, Windows writes, service restart, caption controls,
  real credentials, physical installation, push or merge occurred in this slice.

Earlier validation attempts found an outdated route-count assertion and inventory
entries; both were corrected. An initial system-Python full run lacked Alembic;
the final full run used the existing complete test environment. Existing test
ResourceWarnings are not a claim of a new runtime leak.

## Remaining gates

See [implemented policy and staging sequence](ON_DEMAND_MEDIA.md). The current
Windows v2 feed was not replaced, so this source work does not increase its live
ready count. A matched v3 rollout needs a freshly reviewed private source index,
cache paths/ACLs, CPU dependency environment and exact configured APKs.

HEVC/4K/HDR/rotated or unsupported video profiles still need preparation; no bulk
queue was launched. Protected prepared-video access for phone viewers without
original permission remains absent. TV discovery remains a separate v2 candidate
and is disabled in the v3 build; its v3 source-reference integration is outstanding.
Original delivery does not add tiled full-resolution zoom or permanent Android
caching. Actual JMGO video playback, real-library coverage and measured Windows
cache-miss latency/resource behavior remain unverified.
