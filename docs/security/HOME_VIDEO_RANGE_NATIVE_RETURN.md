# PH-HOME-VIDEO-RANGE-NATIVE-01 — Windows verification and prepared candidate

Verified 2026-09-12, 12:30 +08:00. The range fix passes Windows synthetic tests
and the previously failing real MOV. A new **disabled revision-2 candidate**
contains **15 photos and two videos ready**, preserving all 16 previously ready
items and adding that MOV. It has 27,842 catalog entries; **27,825 remain
unavailable**. This is the bounded 17-item step, not whole-library preparation.

The live TV feed remains **revision 1 with 16 ready items**. Nothing was activated
or restarted. Captions continued; no model invocation, original/database mutation,
firewall change, credential change, push or merge was performed by this task.

## Source and native checks

- Branch: `codex/backend-home-tv-feed`, worktree `_worktrees/backend-home-tv-feed`
  in the PhotoHouse workspace.
- Range-fix source: `50391b6db8a7c41dc276f6ec36c28dfc0b0a934d`.
- Staged source/documentation revision: `6469cfc991325a82e4f70e3eab36d843fe05b5cb`.
  All 318 selected committed source/fixture blobs were hash-verified on Windows
  before tests and again after preparation. No further production code changed.
- Fresh offline source directory and Python interpreter; existing reviewed CPU
  dependencies reused without installation. Serving/caption environments were
  not reconfigured. Python 3.12.10, Pillow 12.3.0, FFmpeg/ffprobe 7.1.1.
- **86 tests passed, zero failures/errors/skips**, 39.744 seconds. This includes
  full/limited-range decoded luma/chroma regressions, preparer, feed, catalog,
  native guard and inventory tests. Inventory: 162 method/path entries complete;
  inventory completion does not close the recorded standalone/legacy gaps.

The real MOV now produces H.264 High, `yuv420p`, explicit `tv` sample range,
1308x980, AAC-LC, 1.856 seconds, 3,295,006 bytes. The normal metadata, geometry,
duration, faststart, full-decode, poster and chunk-hash checks passed. It took
8.516 seconds. The old `yuvj420p` failure was not accepted or relabeled as ready.
Human visual quality and physical TV playback are still unverified for this item.

## Candidate verification

The existing 16 ready sources were rechecked against their retained original
hashes, then reprepared in the same new workspace in 26.188 seconds. A new base
with revision 2 was used; the old journal/fingerprint was neither edited nor
adopted. Verified resume of both explicit sets took 1.875 seconds, with conversion
disabled by an assertion to prove ready results were reused only after checks.

The candidate occupies 26,589,028 bytes including catalog and derivatives. Its
catalog SHA256 is
`7fd30c43a677236e6bfe8ac62221514c1842d796370428701af9966ee1903eb4`.
The production candidate control remains `enabled: false`.

Windows-only in-process ASGI checks passed:

- Disabled candidate rejects catalog and video HEAD access.
- All 34 grid/display JPEG previews decode with expected dimensions, RGB mode,
  stripped EXIF and matching hashes.
- Both videos pass HEAD, full-content hashes, bounded beginning/end byte ranges,
  and EOF rejection. These files fit within one 4 MiB chunk; this real sample
  does not add a cross-chunk playback claim beyond the synthetic suite.
- Stale catalog/video revisions return 409; invalid Host, denied peer and forged
  forwarded-peer requests return 403.
- Eleven sampled legacy/account/voice/operational/discovery paths remain closed.

The enabled ASGI test control was separate from the disabled candidate control
and removed afterward. No test listener exposed this candidate. Original media
and prepared media stayed on Windows; only metadata, logs and resource receipts
were copied to the Mac.

All 17 selected original hashes, selected asset metadata and database schema
remained unchanged. Database connections were read-only/query-only. Fresh visible
metadata exports matched the pinned base before and after publication. This is
snapshot verification; subsequent hide/import changes still require revalidation.

## Resource and caption observations

Single owned preparation child at a time, below-normal priority and existing
thread/time/size/disk limits. Peak observed owned working set was 367,140,864 bytes
(about 350 MiB); sampled available RAM stayed above 28.2 billion bytes during
preparation/validation. No configured resource threshold fired. Samples use
one-second sleeps plus polling overhead, not a hard OS memory/CPU guarantee.

Caption rows increased from **42,318 to 42,340** across the operation. The observed
437 failed and four dead caption tasks remained unchanged during preparation;
those pre-existing failures were not retried. Progress and preserved identities
show coexistence, not proof of zero performance impact.

The API, v1 TV feed, v2 TV feed and caption process retained their PID/start-time
identities. Listener addresses/ports, task states, live config/control/catalog
hashes and old preparer source remained unchanged. The API's non-model probe
continued returning the expected 404. No caption pause or service restart occurred.

## Handoff and activation boundary

Exact Windows paths, IDs, host route and process receipts are in the private
operator return under `photohouse-range-native-20260912`. The current source-only
[range return](HOME_VIDEO_RANGE_RETURN.md) remains the implementation rationale;
this document records the subsequently authorized Windows work.

**Next action requiring approval:** activate this verified revision-2 candidate
with a brief restart of only the v2 TV feed. Before switching, refresh current
scope/original and live identity checks, save the old target configuration, and
grant the existing limited task user read/traverse access only to the new
derivative publication if needed. Keep the current LAN peer boundary, port,
certificate, v1 service and caption process. Retain the exact revision-1 rollback
target; the running app cannot adopt changed catalog bytes in place.

After activation, Android v8 should refresh the catalog revision and verify both
videos, preserved photos, zoom, seek, page navigation and Back. Physical JMGO
acceptance remains pending. The candidate has not been tested through Android
or a live HTTPS listener, and the current APK will not see the additional video
until activation.

Further thumbnail coverage needs additional explicitly selected batches and,
for efficient repeated releases, the reviewed carry-forward helper proposed in
the source return. Neither bulk preparation nor that helper was implemented here.

Evidence: [native test log](evidence/home-video-range-native/native-tests.log)
and [verification receipt](evidence/home-video-range-native/verification.json).
This operational evidence commit is discoverable with
`git log -1 --format=%H -- docs/security/HOME_VIDEO_RANGE_NATIVE_RETURN.md`.
