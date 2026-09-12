# PH-HOME-MEDIA-PROFILE-01 — bounded large-photo and long-video source slice

2026-09-12. This slice adds the `library-sdr-v1` preparation profile, supervised
media hashing, JPEG decoder subsampling and reviewed qualification cases inside
the full-library checkpoint. It does not prepare more real media or activate a
publication. Android's frozen catalog/video wire contract is unchanged.

## Exact source and integration boundary

- Branch: `codex/home-media-profile-coverage`.
- Worktree: `_worktrees/home-media-profile-coverage` in the PhotoHouse workspace.
- Base: merged GitHub master `6d0bf84f85ece5b906e71e1418c45514ccfbbb0c`.
- Profile/worker implementation: `3edf0916bcc04e845d34bdc4d8adbd337ebbf02b`.
- Qualification implementation and final candidate:
  `ee5c06faea3d6f62ec356a9f7bb086d3569aea59`.

The earlier integration worktree/history was preserved. These two new source
commits and their evidence remain unpublished to GitHub; no new push or merge
was authorized. Private source staging was used for native synthetic tests.
PR #5's earlier GitGuardian finding remains a failing hosted check for its fixed
synthetic test passphrase, reviewed in that PR. It is not a green hosted result
for this new source. Source integration, synthetic Windows tests, real preparation,
service activation and physical TV acceptance are separate evidence.

Changed implementation files are
[`prepare_home_catalog.py`](../../scripts/prepare_home_catalog.py),
[`prepare_home_library.py`](../../scripts/prepare_home_library.py), and new
[`home_media_worker.py`](../../scripts/home_media_worker.py). Tests are in
[`test_home_media_profiles.py`](../../tests/security/test_home_media_profiles.py)
and the updated [library tests](../../tests/security/test_home_library.py).

## Preparation profile and limits

The default remains the pilot profile. The new profile is explicit at job creation:
`prepare_home_library.py create ... --profile library-sdr-v1`. A budget JSON file
and a named profile are mutually exclusive. All resolved fields and worker source
are fingerprinted; changes require a fresh job with explicitly pinned carry.

| Limit | Pilot | Candidate library-sdr-v1 |
| --- | ---: | ---: |
| Original bytes | 512 MiB | 8 GiB |
| Normalized video bytes | 64 MiB | 4 GiB |
| Media duration | 60 s | 900 s |
| JPEG header pixels | 40 MP | 256 MP |
| Decoded image pixels | 40 MP | 16 MP |
| Video/ordinary non-JPEG source pixels | 40 MP | 40 MP |
| Hash deadline per supervised pass | 60 s | 900 s |
| Probe/header deadline | 20 s | 30 s |
| Full-decode deadline | 120 s | 1,800 s |
| Encoding child deadline | 120 s | 5,400 s |
| `prepare_one` total deadline | 180 s | 7,200 s |

The candidate covers the *observed input envelope* of 7.63 GiB video, 816.67-second
duration and about 199.8 MP image headers. It is not proof that the largest real
files decode within these budgets. Additional coordinator carry/resume/publication
hashes have their own supervised deadlines; the `prepare_one` limit is not a
deadline for an entire job or all its publication copies.

The production resource guard remains sequential: one owned child, single-thread
FFmpeg settings, below-normal Windows priority, 4 GiB available-RAM floor, 1 GiB
observed per-process working-set ceiling and 2 GiB disk reserve. These are sampled
limits, not hard OS quotas. Sampling can miss brief peaks. Publication copies still
check between synchronous chunks; an OS-stalled copy/fsync or metadata operation
can delay a stop. This slice supervises hashing and decoder execution, not every
possible filesystem syscall. Retained attempts and publication copies still need
the capacity allowance from the earlier full-coverage plan.

## What changed

All original/derivative hashes run in a lightweight owned process. The coordinator
can kill and wait for that process on timeout, operator stop or resource pressure;
it no longer blocks inside the old fixed 60-second media-read loop. Full-file and
chunk hashes can be computed in one pass. File identity, size and modification
time are checked around the read, and the parent verifies the worker result.
The configured hash deadline propagates through preparation, resume, carry,
publication verification and existing-copy verification.

JPEG headers and decoding also run in owned children. Baseline JPEGs use the
decoder's 1/2, 1/4 or 1/8 reduction before `load()` when needed. Actual decoder
dimensions must fit the decoded-pixel budget before and after load; there is no
full-size fallback. Orientation, ICC-to-sRGB conversion, alpha flattening and
metadata stripping remain enforced. An unservable ICC profile fails rather than
being silently ignored. The JPEG output keeps the existing grid/display bounds
and never upscales a reduced decode. Thus some images may have less than the
maximum display resolution under the chosen memory budget.

Large progressive JPEGs requiring subsampling remain explicitly deferred as
`progressive_jpeg_profile`: reduced output dimensions alone do not establish a
bounded intermediate decoder allocation. PNG has no equivalent draft path here;
an image exceeding its decoded-pixel budget remains deferred. The earlier audit
did not record progressive flags, so its 27,821 potential-header-candidate estimate
must not be promoted to an achieved or exact new-profile coverage count.

SDR encoding still produces bounded H.264/yuv420p, limited sample range and optional
AAC-LC under the frozen v2 contract. Source decoding uses strict error handling,
then the complete normalized video is decoded for verification. Probe and decode
deadlines are independent of the longer encode allowance. Long-video duration
tolerance is capped at one second instead of growing to many seconds. FFmpeg's
`-fs` option was removed because it can finish successfully after stopping a
stream early; the supervisor checks output limits while running and after exit.
Oversized/failed attempts are never accepted as ready.

Detailed private checkpoint errors distinguish `source_empty`, `hash_timeout`,
`process_timeout` and `probe_metadata_invalid`. Published unavailable states stay
within the unchanged wire reasons. No HDR tone mapping, MPO frame selection,
visibility change or original-byte access was added.

JPEG draft semantics are documented by
[Pillow](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.draft);
FFmpeg's strict error option is documented in its
[command reference](https://ffmpeg.org/ffmpeg.html). Actual compatibility claims
below come from this slice's tests, not merely those option descriptions.

## Qualification without duplicate preparation

`run --qualification-plan <canonical-json>` visits 1–16 reviewed IDs within the
same pinned **full** snapshot. The JSON must contain exactly `revision`,
`base_sha256` and unique `asset_ids`; wrong revisions, hashes, unknown IDs, extra
fields and oversized lists are refused before attempts begin. Its hash and IDs
are retained in the private checkpoint. This is an initial qualification mode,
not a requirement for repeated manual batches.

A completed subset reports `qualification_complete`; it does not claim a verified
full run, even if the subset happened to include every item. Continue with ordinary
`run --workspace ...` to verify previous results and automatically process every
remaining item. Qualifying outputs and pinned older derivatives are reused only
after source/visibility/receipt/hash checks. This avoids a separate disposable
qualification cache or rewriting an old checkpoint's fingerprint.

## The remaining 21 audited cases

Read-only analysis used the existing private audit database, not the real database
or original media. No fresh real-media header/decode operation was performed.
These mutually exclusive groups account for all 21 previously unresolved cases:

| Retained audit evidence | Count | Required disposition |
| --- | ---: | --- |
| Empty video files, zero bytes | 5 | Recover valid originals or explicitly resolve their library status later |
| 4 KiB image files, unidentified headers | 4 | Inspect/recover source; do not invent a thumbnail |
| 4 KiB video files, failed probes | 3 | Inspect/recover source |
| Image files 564–757 bytes, header errors | 4 | Investigate invalid/truncated data; exact cause is not yet established |
| Missing photo originals | 2 | Recover source or obtain a separate library-status decision |
| Eight-frame MPO with `.png` extension | 1 | Explicit representative-frame policy still required |
| About 16 MB video, probe JSON decoding error | 1 | Repeat a bounded metadata probe; corruption is not established |
| About 5 MB H.264 video, pixel format not reported | 1 | Probe/decode qualification; do not assume the missing format |

Tiny files are not automatically proven placeholders, and this review did not
delete, rename, restore, hide or rewrite any entry. The two medium-sized videos
may be probe limitations; leave them unresolved until qualification supplies
evidence. [Aggregate accounting](evidence/home-media-profile/unresolved-audit.json)
contains no original paths or asset IDs. Per-ID provenance stays in the private
Windows audit.

## Representative Windows qualification plan — not executed

Use the final pinned source in the separate existing CPU preparation environment.
Recheck source/tool/interpreter identities, current visibility, available resources,
the old seed journal and highest allocated revision. Keep active revision 1 and
disabled revision 2 unchanged. Create a fresh full-snapshot job at revision 3 or
higher with `library-sdr-v1` and the explicitly pinned 17-item legacy carry seed.
The private operator return contains exact paths and hashes; public commands use
portable operator variables.

Before any real conversion, derive and retain one qualification plan from the
existing audit intersected with the fresh job's visible IDs. Deduplicate and cap
at 16. Select by recorded properties, not another manually supplied list:

1. Largest photo by pixel count, first just over 40 MP, largest portrait, and
   widest aspect ratio. Progressive/ICC/orientation details are currently unknown
   for these real files and must be recorded during qualification.
2. Longest SDR video, largest original video, first above 60 seconds, first above
   512 MiB, highest pixel count, plus full-range and HEVC examples where distinct.
3. One previously verified photo and video to prove carry, and the two medium-size
   unresolved probe cases as explicitly diagnostic cases if slots remain. The
   known empty/tiny/missing files and MPO need recovery/policy, not blind retries.

A metadata-only proposal has been retained on Windows: **12 distinct cases**
(four photos, eight videos, including two diagnostic cases). Deduplication combines
15 selection roles. It includes the audit's 199,756,800-pixel photo,
8,193,114,694-byte video and 816.667433-second video. Actual IDs remain only on
Windows; the [aggregate proposal](evidence/home-media-profile/qualification-proposal.json)
contains no IDs or original paths. This proposal uses the old audit, so fresh
visibility intersection and review are still required.

Write the reviewed IDs only to a private execution plan, bound to `job.json`'s
revision and base SHA. Review the exact plan and resource budget before running it.
No real job or snapshot-bound execution plan has been created, and no selected
original has been opened or converted by this source slice.

```powershell
$Coordinator = Join-Path $PrepSource 'scripts\prepare_home_library.py'
& $PrepPython $Coordinator create --database $Database --source-root $Originals `
  --workspace $Work --ffmpeg $Ffmpeg --ffprobe $Ffprobe `
  --previous-publication $PreviousPublication --revision $Revision `
  --profile library-sdr-v1 --carry-workspace $CarryWork `
  --carry-kind legacy --carry-sha256 $CarryHash
if ($LASTEXITCODE -ne 0) { throw 'Create refused; preserve and inspect.' }

# Generate/review the private, snapshot-bound $QualificationPlan as above.
& $PrepPython $Coordinator run --workspace $Work --qualification-plan $QualificationPlan
if ($LASTEXITCODE -notin @(0,3)) { throw 'Qualification refused.' }
& $PrepPython $Coordinator status --workspace $Work

# After measured qualification and authorization for bulk continuation:
& $PrepPython $Coordinator run --workspace $Work
& $PrepPython $Coordinator status --workspace $Work
# Default full publication refuses any non-ready item. --allow-partial is explicit
# and must never be described as full-library completion. Publication stays disabled.
& $PrepPython $Coordinator publish --workspace $Work --output $Publication
```

Qualification acceptance must record every case's outcome, source/metadata hashes,
decoded image dimensions, output metadata/full-decode/chunk hashes, wall time,
sampled RSS/available RAM, disk growth and caption/service observations. Stop and
resume at least one owned hash/encode operation; ensure no interrupted attempt is
adopted and verified cases are not encoded again. Test beginning, end, cross-chunk
Range and EOF rejection against a synthetic/in-process catalog first. Human
orientation/color and TV playback/seek checks remain distinct from hash validation.

Do not turn the 125-second low-resolution synthetic timing into an ETA for 8K,
13-minute or 7.63-GiB originals. Replace the earlier weak throughput/storage
extrapolation with measured representative results before an uncapped run. Do not
pause captions, change threads or reduce production guards to make a case pass.
Failed qualification remains a recorded limit needing review.

## Validation and handoff

The Mac suite passed 125 focused tests in 89.931 seconds, followed by the three
qualification tests in 5.324 seconds. The first Windows source candidate passed
125 tests in 243.510 seconds with all 323 staged blobs verified before and after.
Final Windows candidate `ee5c06f` passed **128 tests in 263.112 seconds**, with
zero failures/errors/skips and all 323 staged source blobs verified before/after.
The 162 route inventory entries remain complete; existing retired/standalone
security gaps are not erased by that count.

On Windows, the 48 MP synthetic JPEG took 1.390 seconds with about 258 MB observed
working set and at least 16.97 GB available RAM under the unchanged 4 GiB floor.
The 125-second 320x180 synthetic video took 20.344 seconds and produced 41,652,760
bytes across ten chunks; full decode, resume and Range checks passed. These are
qualification fixtures, not a real-library throughput estimate.

At 14:36 +08, the live revision-1 control, disabled revision-2 control, live config
and old seed journal hashes matched the retained baseline. The API, caption, v1
and v2 processes retained their PID/start identities. No caption-progress query or
model endpoint was invoked in this source slice.

The synthetic cases include a 48 MP baseline JPEG decoded at 12 MP, all eight EXIF
orientations with independent color-quadrant expectations, ICC handling, progressive
JPEG/PNG/MPO deferrals, a synthetic 200 MP **header-only** planning case, a file
larger than 512 MiB, owned hash cancellation/deadline/memory stops, decode timeout,
125-second video with multiple chunks, verified resume/carry and beginning/end/
cross-chunk Range responses. A 200 MP header is not a valid full-decode benchmark.

On the shared Mac, the initial 48 MP test correctly stopped below the production
4 GiB available-RAM floor. Its subsequent decode test used a **test-only 256 MiB
floor**, keeping the 1 GiB per-process ceiling; observed working set was about
296 MB. The Windows test uses the unchanged 4 GiB floor. Resource sampling is not
proof of the absolute peak. Earlier failure receipts are retained privately.

No real bulk conversion, original/live-database write, new listener, model load,
service restart/activation, caption pause or Android-source change was performed.
Android should retain its frozen pins until a contract/import review warrants a
change. It owns native long-media seek, revision replacement and physical JMGO
acceptance. The next operational action is the reviewed representative
qualification above, not immediate activation or a claim of complete coverage.

Evidence: [verification receipt](evidence/home-media-profile/verification.json),
[unresolved accounting](evidence/home-media-profile/unresolved-audit.json),
[Mac focused tests](evidence/home-media-profile/mac-focused.log),
[Mac qualification tests](evidence/home-media-profile/mac-qualification.log), and
[Windows final tests](evidence/home-media-profile/native-tests.log).
Find the evidence commit with
`git log -1 --format=%H -- docs/security/HOME_MEDIA_PROFILE_RETURN.md`.
