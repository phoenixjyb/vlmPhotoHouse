# PH-HOME-FULL-COVERAGE-01 — automatic preparation and coverage audit

Verified 2026-09-12. The new coordinator traverses the entire visible metadata
snapshot, checkpoints each item, resumes interrupted work and carries verified
derivatives into a newer immutable revision. Operators no longer select batches
of 16 IDs. **This source/audit slice did not start a real bulk conversion.**
Live revision 1 still has 16 ready items; the disabled revision-2 candidate has 17.

Source: `0872cf8ae799b366eb80da7b6d77ff9ad79d56b7`, branch
`codex/backend-home-tv-feed`, worktree `_worktrees/backend-home-tv-feed` in the
PhotoHouse workspace. Original checkout and Android source were preserved.
The frozen v2 wire contract, serving code, visibility and access boundaries did
not change. No push, merge, activation, service restart or caption pause occurred.

## What the coordinator verifies

[`prepare_home_library.py`](../../scripts/prepare_home_library.py) creates a fresh
active/NULL-status asset snapshot using the existing catalog exporter. It pins
the source implementation, tools, Pillow version, budgets, base catalog, database
and originals provenance, previous publication and explicitly reviewed carry
checkpoint. The revision must exceed both previous publication and carry seed.

The job owns a derived SQLite checkpoint, never the live database. One writer
visits every snapshot ID in descending order. Each item records pending, working,
ready, deferred, error or excluded state with a reason and attempt history.
Deferred profile/budget limits are not falsely classified as corrupt media.
`queue_drained` does not mean `verified_complete`; a run exits 3 when incomplete.
`status` reports checkpoint observations, not a fresh verification of originals.

Before reusing ready output, a run checks current source visibility and metadata,
original bytes, the committed receipt and derivative hashes. A receipt committed
before the ready transaction recovers an interruption without duplicate encoding.
Unverified interrupted attempts remain on disk and are not adopted. An explicitly
pinned legacy journal or earlier library checkpoint can seed a new job; source,
provenance, kind and derivative checks still apply. The reviewed checkpoint hash
is the trust anchor, not an assertion that arbitrary imported files are trusted.
The seed must stay unchanged and available throughout the job.

Publication rechecks the full visible snapshot and every ready source/receipt,
copies only prepared derivatives, verifies copies, rechecks scope and writes
disabled control last. Interrupted publication resumes verified copies without
conversion. It preserves externally changed control/catalog files. A started or
finished publication freezes its job; further work needs a fresh job/revision and
pinned carry. New imports or visibility changes require a fresh snapshot rather
than publishing stale scope. This is an immutable snapshot workflow, not a live
library mirror.

The existing worker stays sequential with bounded native children and one-thread
FFmpeg commands. Default limits remain 512 MiB input, 64 MiB normalized video,
40 MP input, 60 seconds media, 120 seconds child and 180 seconds asset time.
The new guard stops on an operator `stop.flag`, optional run duration, disk
reserve, available RAM below 4 GiB or observed per-process working set above
1 GiB. A stop terminates only the owned child and preserves resumable state.
It samples each newly spawned child and then about once per second. These are
observed limits, not hard OS quotas; synchronous hashes or stalled filesystem
operations can delay a stop. The original hash helper still has a fixed 60-second
deadline, independent of budget JSON.

## Read-only Windows inventory

The audit covered **27,842 visible entries: 23,599 photos and 4,243 videos**.
It used read-only/query-only SQLite, file stats, image headers and sequential
bounded ffprobe metadata calls. It did not decode/convert real media, load models,
write originals or copy media to the Mac. Aggregate evidence contains no asset
IDs or original paths. The private per-item audit remains on Windows.

| Scope | Photos | Videos | Total |
| --- | ---: | ---: | ---: |
| Visible snapshot | 23,599 | 4,243 | 27,842 |
| Current-profile header candidates | 23,331 | 3,616 | 26,947 (96.8%) |
| Potential after reviewed large-JPEG and larger SDR budgets | 23,588 | 4,233 | 27,821 (99.925%) |
| Still requiring investigation after that work | 11 | 10 | 21 |

**Header candidates are not ready media.** Decode, geometry, duration, resource,
output-size and hash validation can reveal additional failures. The potential
row includes preparation-profile work that has not been implemented or measured.

Observed originals total about 646 GB: 82.08 GB photos and 563.97 GB videos.
Known video duration totals 39.24 hours. The largest video is 8,193,114,694 bytes
(7.63 GiB); longest is 816.67 seconds (13m37s). Largest image is about 199.8 MP.

The main gaps overlap:

- 598 videos exceed 60 seconds: 574 are at most five minutes, 24 exceed five
  minutes. 185 videos exceed the 512 MiB input budget.
- 257 images exceed 40 MP, including 26 hitting the large-header guard.
- Remaining photo issues: one MPO/multiframe image, two missing originals and
  eight unresolved image headers. Do not silently choose an MPO frame or remove
  missing entries from the catalog.
- Ten videos need probe/pixel-format investigation; nine have unresolved probes.

Containers were 4,211 MP4 and 32 MOV. Successfully reported video codecs were
1,242 H.264 and 2,992 HEVC. Reported pixel formats were 4,061 `yuv420p`, 172
`yuvj420p` and one unknown. No PQ/HLG transfer or 10-bit format was observed in
successfully probed videos; unresolved files remain unknown. This does not add
HDR support. Photos predominantly report JPEG, with four confirmed PNG headers
and one MPO; unresolved/large headers retain extension-based labels in evidence.

The audit resumed automatically after its first 15-minute pass and finished in
about 20.9 minutes across two passes. Visible source metadata remained unchanged.
Caption rows progressed 42,406 to 42,455 during the audit and reached 42,503 in the
final observation; 443 failed/dead caption tasks remained unchanged during these
checks. No retries or caption controls were invoked. Audit sampling observed up
to 343 MB RSS and at least 22.87 GB available RAM; its earlier helper could miss
short-lived child peaks. This is coexistence evidence, not zero-impact proof.
At 13:43 +08, all four existing service PID/start identities and live/candidate
controls matched the baseline. Final observed free space was 5.245 TB.

## Runnable current-profile bulk plan — not executed

Use the pinned source and reviewed CPU preparation interpreter/tool binaries.
Exact Windows paths and the legacy journal hash are in the private operator
return. The following PowerShell variables are operator inputs, not new secrets.
Resolve them to canonical absolute paths before executing. Choose a new workspace
and sibling output outside originals, database, old publications and carry seed.
Refresh the highest allocated/active revision first; revision 3 is the next
candidate as of this return. Do not create it from stale assumptions later.

```powershell
# Inputs: $PrepPython, $PrepSource, $Database, $Originals, $Work, $Publication,
# $Ffmpeg, $Ffprobe, $PreviousPublication, $CarryWork, $CarryHash, $Revision.
$Coordinator = Join-Path $PrepSource 'scripts\prepare_home_library.py'
& $PrepPython $Coordinator create --database $Database --source-root $Originals `
  --workspace $Work --ffmpeg $Ffmpeg --ffprobe $Ffprobe `
  --previous-publication $PreviousPublication --revision $Revision `
  --carry-workspace $CarryWork --carry-kind legacy --carry-sha256 $CarryHash
if ($LASTEXITCODE -ne 0) { throw 'Create refused; retain its files and inspect.' }

# Optional initial qualification of automatically selected items; no manual IDs.
& $PrepPython $Coordinator run --workspace $Work --max-items 64
if ($LASTEXITCODE -notin @(0,3)) { throw 'Qualification refused.' }
& $PrepPython $Coordinator status --workspace $Work

# After the measured qualification review, one uncapped invocation visits all.
# Reuse exactly this command after interruption; it verifies completed work.
& $PrepPython $Coordinator run --workspace $Work
if ($LASTEXITCODE -notin @(0,3)) { throw 'Run refused; inspect private evidence.' }
& $PrepPython $Coordinator status --workspace $Work

# Only when all ready; default publication refuses incomplete coverage.
& $PrepPython $Coordinator publish --workspace $Work --output $Publication
# If deliberately releasing incomplete coverage, use --allow-partial explicitly.
# That freezes this job and produces a DISABLED partial snapshot, never success
# for full coverage. Activation is a separate reviewed operation.
```

The expected current-profile run defers the known gaps; do not repeatedly retry
them with unchanged budgets. `--retry-errors` revisits errors and deferrals after
an appropriate repair, while implementation/budget changes require a fresh job.
For a later library-to-library carry, pin the stopped prior `state.sqlite` and use
`--carry-kind library`; keep that checkpoint immutable. Create `stop.flag` inside
the owned workspace to request a stop, confirm exit, and remove that flag before
resuming. No scheduled task, startup hook or automatic reboot resume was installed.

Before a real bulk run: refresh provenance, visibility, live identities and disk;
qualify measured CPU/RAM, retained-byte growth, captions, hashes and resume; then
continue automatically through the remaining queue under the approved profile.
Keep the default one worker. Prepare a new disabled publication, validate all
ready assets and Range boundaries, and preserve revision 1 for rollback. A live
switch remains separate from preparation and physical Android/TV acceptance.

## Measured planning range and next profile work

The only conversion calibration is the earlier 15 small photos and two videos
lasting about 1.5 and 1.8 seconds. No long-video or giant-JPEG benchmark was run.
Applying those sampled rates gives **illustrative projections, not an ETA**:

| Scope | Worker hours, sampled low–high | Derivatives | Workspace + publication |
| --- | ---: | ---: | ---: |
| Current-profile candidates | 68–103 | 47–182 GB | 94–365 GB |
| Entire snapshot after profile work | 129–187 | 76–330 GB | 152–659 GB |

Short-clip setup cost distorts duration extrapolation; output complexity and
source hashing add uncertainty. A roughly 1 TB planning allowance accommodates
the upper copy estimate plus retained attempts/headroom, but is not a guaranteed
cap. The default 2 GiB emergency reserve is not this capacity plan. Long-clip
qualification must replace these projections before promising a completion date.

The next bounded source slice should implement and test:

1. Long/large SDR preparation with measured limits covering the observed 7.63 GiB
   and 13m37s inputs. A proposed envelope is 8 GiB source, 900 seconds media,
   4 GiB normalized output and 5,400/7,200 seconds child/asset deadlines. Review
   the fixed source-hash deadline and disk/stop behavior first. Budget JSON alone
   is not evidence that these limits work safely.
2. Bounded large-JPEG decoder subsampling before full decode, with decoded-pixel
   and RSS bounds, EXIF orientation, color and pixel regressions. Merely raising
   the 40 MP limit is insufficient. HDR and MPO frame policy remain explicit
   deferrals unless separately implemented and reviewed.
3. Investigation/accounting for the 21 remaining header/probe cases, followed by
   an approved measured real qualification and automatic full queue run. Every
   item must become verified ready or remain visibly unresolved; full coverage
   must never be inferred from queue completion.

Android v8 source `efadba4702c322f14d097640fad93fc6f07f46d0` was reported by its
owner to support the existing 100,000-entry, 24-hour/video, 32-GiB/video contract
and 2,000 pages of 50. The 60-second/64-MiB limits above are preparer defaults.
No wire ceiling increase is indicated by this audit. Android still needs actual
large-catalog navigation, long-video seek/Range, refresh and physical-projector
acceptance against the eventually activated publication.

## Validation and evidence

Windows: **108 synthetic tests passed, no failures/errors/skips, 137.300 seconds**.
All 321 staged source blobs matched the committed hashes before and after tests.
The 162 method/path inventory entries are complete; existing standalone/legacy
authorization gaps remain documented, and inventory is not authorization.
Mac: 105 combined tests passed, then two added publication tests and one native
memory smoke passed separately. This was not one 108-test Mac invocation.

Coverage includes automatic traversal beyond 16, verified resume without encoding,
receipt crash recovery, pinned carry across revisions, corrupt derivatives,
changed originals/visibility/imports, profile deferrals, revision/fingerprint
refusal, disk/RAM/operator stops, owned-child termination, interrupted publication,
mid-copy pressure and preservation of externally enabled control. Windows tests
use generated media only. A test-environment Starlette deprecation warning was
retained; dependencies were not changed as part of this task.

Evidence: [verification receipt](evidence/home-full-coverage/verification.json),
[aggregate audit](evidence/home-full-coverage/audit-summary.json),
[analysis and calibration](evidence/home-full-coverage/audit-analysis.json),
[Windows test log](evidence/home-full-coverage/native-tests.log),
[Mac combined log](evidence/home-full-coverage/mac-105-tests.log), and
[Mac publication log](evidence/home-full-coverage/mac-publication-tests.log).
The earlier [native Range return](HOME_VIDEO_RANGE_NATIVE_RETURN.md) remains the
evidence for the real MOV and disabled 17-item candidate. This task does not
claim more real ready media or physical TV playback.

Find the evidence commit with
`git log -1 --format=%H -- docs/security/HOME_FULL_COVERAGE_RETURN.md`.
