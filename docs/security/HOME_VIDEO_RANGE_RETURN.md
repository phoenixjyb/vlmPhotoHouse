# PH-HOME-VIDEO-RANGE-01 — source correction and next preparation plan

## Result and boundary

Source commit: **`50391b6db8a7c41dc276f6ec36c28dfc0b0a934d`**, on
`codex/backend-home-tv-feed`, worktree `_worktrees/backend-home-tv-feed` in the
PhotoHouse workspace. Parent: `6b9c24c7ad978c7f3f73e826fd9527ad25a4ce98`.
Only the offline preparer and its synthetic tests changed in that commit.
This return, normalization documentation and evidence are a subsequent commit.

The full-range MOV failure is reproduced synthetically and corrected locally.
**No Windows access, native staging, real-media conversion, publication change,
service action, caption action, credential change, push or merge occurred in
this slice.** The Android repository and frozen v1/v2 contracts are unchanged.

The last recorded live baseline is [the prior operational return](HOME_REAL_MEDIA_SERVE_RETURN.md):
revision 1, 27,842 catalog entries, 15 photos and one video ready, 27,826 unavailable.
Those are retained observations, not a fresh live check. This fix prepares no
additional real media and does not resolve the broad missing-thumbnail problem.

## Failure and correction

The retained native H.264 MOV output had two clean H.264/AAC tracks and acceptable
duration/geometry, but remained `yuvj420p`. The validator correctly refused it.
The existing `format=yuv420p` filter alone did not normalize range signaling.

The scale filter now detects the input range and converts samples to limited
range, with matching `-color_range tv` for encoding. The validator additionally
rejects explicit full-range output metadata even when the pixel format reports
`yuv420p`. Missing/unknown range remains accepted for ordinary limited-range
H.264 without explicit VUI metadata. Validation was tightened, not bypassed.
The [FFmpeg scale documentation](https://ffmpeg.org/ffmpeg-filters.html#scale-1)
describes the numeric full/limited sample-range conversion used here.

No codec/profile, HDR, resolution, duration, input/output size, decoder protocol,
metadata, process-priority or thread limit was expanded. Original hashes, full
decode, faststart, previews and chunk integrity checks remain in the path.

## Verification

Mac CPU environment: Python 3.12.12, Pillow 12.3.0, FFmpeg/ffprobe 9.0.1.

- Before the source fix: the full-range synthetic MOV became unavailable;
  the explicit-full-range validator regression failed; limited-range pixels passed.
- After: those three focused tests passed. The new fixtures are lossless synthetic
  BT.709 YUV bars, independently checked before preparation. Output is checked
  after normal production CRF-23 encoding and decoding: expected luma
  16/71/126/181/235 and both chroma planes, tolerance at most three code values.
  The limited-range fixture guards against applying the conversion twice.
- Combined preparer, home catalog, home feed, native guard and inventory suite:
  **86 passed, zero failed/errors/skipped**, 30.634 seconds.
- `git diff --check` passed. Markdown was rendered to local HTML and its headings
  and local links checked; no visual browser inspection is claimed.

Evidence: [before](evidence/home-video-range/before.log),
[focused after](evidence/home-video-range/after.log),
[combined suite](evidence/home-video-range/mac-tests.log),
[versions, hashes and gates](evidence/home-video-range/verification.json).
Logs replace the absolute checkout prefix with `<repo>`; no real media is included.

Reproduce in the separate CPU test environment, with preparation dependencies
available, both native FFmpeg tools on PATH and no live data:

```python
import sys, unittest
sys.path.insert(0, 'tests/security')
names = ['test_native_home_guards', 'test_home_preparer', 'test_home_catalog',
         'test_home_feed', 'test_inventory']
suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in names)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful() or bool(result.skipped))
```

Windows FFmpeg 7.1.1, the retained real MOV, Android playback of corrected media,
physical TV color/playback, and ongoing caption coexistence **were not tested
in this slice**. Previous native results cannot certify this new source commit.

## Proposed operational step — approval still needed

Recommend a first candidate containing the existing 16 ready items plus the
previously failed MOV: **17 ready items only if every check passes**. Exact IDs,
host paths and current runtime identities belong in the private operator receipt.
No unrestricted retry or bulk conversion is proposed.

1. Read current revision, task/PID/start times, caption completion/error counts,
   source eligibility, available RAM and disk without invoking model-loading
   endpoints. Verify the 16 old ready IDs and failed MOV against the retained
   private receipt. If scope or identity changed, reconcile before writing.
2. Stage the pinned new source in a fresh offline preparation directory, separate
   from serving/caption environments. Reuse verified native CPU tools; verify
   transferred source hashes. Run the 86 synthetic tests on Windows with zero
   skips before a real-source attempt. Stop on native differences.
3. Export a new disabled metadata base with a revision greater than the currently
   served revision (expected 2). Create a fresh preparation workspace on Drive E.
   Run the one failed MOV first with the same bounded profile. Confirm limited
   output range, metadata/geometry/duration, full decode, previews, chunk hashes,
   original immutability and operator visual quality before continuing.
4. Reprepare the existing 16 ready items in a second explicit invocation in that
   same new workspace. This is deliberate bounded duplicate CPU work; there is
   currently no reviewed way to import their checkpoints across script changes.
   If any formerly ready item fails, do not release a silently degraded candidate.
   A newly hidden item must be excluded even if it was previously served.
5. Resume both explicit sets to recheck source and derivative hashes without
   re-encoding. Re-export current visible metadata at the same proposed revision
   and compare it to the base. Stop and rebuild/review if visibility or metadata
   changed. Publish to a **new disabled directory**, verify copied bytes and
   catalog/control hashes. Test disabled rejection and enabled behavior with
   an isolated ASGI test configuration, including legacy-route denial, HEAD,
   Range, stale revision, complete video hash and preview decode.
6. Present the native receipt and disabled candidate before activation. A stopped
   v2 release switch is required: the app pins catalog identity for its lifetime.
   Do not edit catalog bytes under a running app. Under activation approval,
   change only the v2 release target, retain the two-peer LAN boundary, verify
   limited-task read access to the new derivatives, and test Android against the
   new revision. Retain revision-1 publication/configuration and v1 rollback;
   restore the previous target/start configuration if validation fails.

This approval would cover new offline staging/derivative writes and the bounded
17-item preparation. Activation/restart remains a separate review of that concrete
candidate. No caption pause, database mutation, public exposure, firewall widening,
tool installation or credential operation is included.

## Resources, resume and further coverage

Use one CPU preparation child at a time, one requested codec/filter thread,
below-normal Windows priority, no hardware/model execution. Keep existing limits:
512 MiB input, 40 million pixels, 60-second video, 64 MiB output, 120-second child
timeout, 180-second asset stage deadline, and at least 2 GiB disk reserve plus
candidate/workspace copies. Preflight at least 8 GiB available RAM and 4 GiB free
disk, increased if the calculated copies require more. Observe at roughly one
second plus polling overhead; stop only the owned preparer on an observed owned
process above 1 GiB working set, RAM below 4 GiB, insufficient disk, or a five-minute
operator deadline per invocation. These are monitored thresholds, not hard OS
RSS guarantees; synchronous hashing and polling add time beyond child deadlines.

Observe caption progress/error counts and unchanged service identities before,
during and after each invocation. Do not use a model-loading health probe or
pause captions speculatively. If contention or caption failures appear, stop
owned preparation and investigate; leave caption/service state untouched.

Checkpoints pin script, tools, Pillow, budgets and base bytes. A revision bump
changes those base bytes. **Do not rewrite a fingerprint, edit a journal, reuse
revision 1 for changed content, or pass a ready publication as an unprepared
base.** Within an unpublished workspace, additional explicit sets of at most
16 IDs can accumulate; completed items resume only after verification. Failed
items require explicit retry, and interrupted attempt directories are retained.

After the 17-item canary, prioritize a reviewed list of missing first-page photos
in batches of at most 16, measured before increasing scope. Once a revision has
been served, further coverage needs another revision. Sustainable repeated
publication therefore needs a separate reviewed carry-forward source slice:
validate old provenance, current source/visibility and every derivative hash;
copy verified outputs into a fresh workspace/base revision; retain immutable
releases and refuse changed/hidden inputs. That migration helper is **not
implemented here**. Current tools support the small reprepare plan above, not an
efficient whole-library incremental publisher.

## Android handoff

No new APK endpoint or wire-contract change is needed for this source fix. Android
should keep explicit unavailable states and revision-refresh behavior, and retain
the existing prepared-photo/video evidence separately from physical TV acceptance.
Only after an approved candidate is activated should it test the corrected MOV,
preserved old items, refreshed thumbnails, HEAD/Range/seek, stale revision refresh,
remote focus/Back and actual projector display. Broad catalog visibility remains
different from prepared-media coverage.
