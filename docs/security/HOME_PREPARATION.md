# Offline TV media preparation — source slice

2026-09-12 follow-up: the separate full-library coordinator now provides automatic
snapshot traversal, verified carry-forward and resumable publication. Read
[the full-coverage return](HOME_FULL_COVERAGE_RETURN.md) for current commands,
audit counts and outstanding profiles. The 16-ID workflow below remains the
legacy preparer interface; it is no longer the only preparation workflow.

`prepare_home_catalog.py` adds resumable preparation for the frozen v2 contract.
It never starts a listener, changes a service, accesses an inference model, or
writes the live database/originals. It does not enable an existing publication.
The v1 and v2 wire contracts and serving code remain unchanged.

## Commands and ownership

Use a **separate preparation environment**, with the existing CPU access lock plus
[the preparation lock](../../backend/requirements-home-preparation.lock). It adds
Pillow 12.3.0 with reviewed CPython 3.12 Windows-amd64/macOS-arm64 wheel hashes.
Do not install into either serving environment or the caption environment.
FFmpeg and ffprobe are explicit canonical executable paths and are fingerprinted
in the checkpoint. They are native tools, not dependencies installed by this script.

```
python scripts/prepare_home_catalog.py prepare \
  --database <explicit-local-sqlite> \
  --source-root <canonical-originals-root> \
  --base-catalog <disabled-export-catalog.json> \
  --workspace <new-or-owned-preparation-workspace> \
  --asset-ids <one-to-sixteen-explicit-IDs> \
  --ffmpeg <canonical-executable> --ffprobe <canonical-executable>

python scripts/prepare_home_catalog.py publish \
  --workspace <owned-preparation-workspace> \
  --output <new-disabled-publication-directory>
```

First create the full metadata base with `build_home_catalog.py`. A base containing
ready derivatives is refused; the preparer must own all outputs it marks ready.
`prepare` checks each explicit ID against both the fixed base and a read-only
current `assets` query. Hidden/missing IDs cannot inherit a ready result. Source
paths must be regular direct local files under the configured root; aliases,
symlinks, root escape and overlapping workspaces are refused. No recursive
original-directory discovery, latest-N publication or whole-library conversion
command is provided. All base IDs remain in the final catalog; unrequested items
stay unavailable. This source slice does not finish derivative coverage.

The workspace holds a fixed `base.json`, `journal.json`, a process-released lock,
and unique per-attempt directories. The checkpoint pins base bytes, database path,
source root, this script, FFmpeg/ffprobe bytes, Pillow version and budgets. Changing
those inputs requires a fresh workspace. Completed items are skipped only after
rechecking the original hash and prepared JPEG/video/chunk hashes. Changed or
corrupt inputs are recorded unavailable; `--retry-failed` explicitly retries them.
An interrupted unverified attempt is retained and never adopted as complete.
Only one writer can hold a workspace lock; it releases on process exit, including
an interrupted child. No automatic cleanup of retained attempts occurs.

`publish` verifies completed artifacts and copies **prepared derivatives only**
into a new directory. It rechecks copied hashes, keeps all base catalog items,
and writes `enabled: false` control last. It refuses existing output directories
and paths under the originals root. A failed copy can leave an incomplete new
directory, with no valid enabled control. Neither command points a service at it.
The `_photo` command is an internal worker entrypoint; operators should use only
`prepare`/`publish`, whose ownership/path checks establish its output directory.

## Normalization and verification

Photos: JPEG or PNG, one frame, at most 40 million source pixels. Pillow fully
decodes within that dimension limit, applies EXIF orientation, converts embedded
ICC color to sRGB, flattens transparency on black, and saves fresh RGB baseline
JPEG pixels. No source EXIF/ICC/comments are copied. Grid/display dimensions,
byte limits, JPEG framing and hashes are checked against frozen v2. Invalid ICC,
unsupported/oversized or damaged input records an unavailable result. This is
bounded CPU image preparation, not caption/face/tag recomputation.

The implementation uses [Pillow EXIF transpose](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#PIL.ImageOps.exif_transpose)
and color management, followed by fresh pixel storage before encoding. Correct
orientation is tested by dimensions **and colored pixel positions**, not just by
checking that an EXIF tag disappeared.

Videos: local MP4/MOV only in this slice, one non-attached video stream, 8-bit
4:2:0 input, square/unspecified pixel aspect, at most 40 million pixels and 60
seconds. HDR PQ/HLG, 10-bit and longer sources remain unavailable instead of
receiving an unreviewed tone-map or partial clip. The conversion applies rotation,
limits output to 1080p pixels/1920 edge, 30 fps, H.264 High <=4.1 and AAC-LC. It maps
only the video and optional first audio track, drops source tags/chapters/subtitles/
data, replaces handler/language tags, and requests faststart.

The scale filter converts the detected input sample range to limited range, and
the H.264 encoder receives matching `tv` range signaling. Merely requesting
`format=yuv420p` previously left a full-range MOV output marked `yuvj420p`, which
the output validator correctly rejected. Explicit full-range output signaling
is also refused even if the pixel format reports `yuv420p`; absent/unknown range
remains accepted for ordinary limited-range H.264 without explicit VUI metadata.
[FFmpeg's scale range options](https://ffmpeg.org/ffmpeg-filters.html#scale-1)
perform the sample conversion. Synthetic lossless input bars check decoded
luma and chroma values after production encoding, including a limited-range
regression to catch an unwanted second range compression. These are sample
checks, not a general color-management or HDR acceptance claim.

FFmpeg/ffprobe are invoked without a shell. Input protocol is restricted to local
`file`, the MOV demuxer is forced, and external data references/absolute aliases
are disabled; untrusted local media cannot select a network/playlist demuxer.
[FFmpeg's mapping and metadata options](https://ffmpeg.org/ffmpeg.html#Main-options)
are followed by verification rather than treated as sufficient proof alone.

Every output is probed for codec/profile/pixel format/frame rate/duration/track and
tag rules, top-level MP4 boxes are checked for faststart, and the complete output
is decoded to null with errors fatal. A too-short/truncated output fails duration
validation. Poster previews come from the normalized video and use the same fresh
JPEG path. Finally, full-file and consecutive 4 MiB chunk hashes are written.
This detects preparation/integrity failures; it is not a general media-parser
security audit or physical TV codec acceptance.

## Resource limits and practical limits

| Control | Default |
| --- | --- |
| IDs per explicit invocation | 1–16; canary uses exactly 2 |
| Original size | 512 MiB each |
| Original photo/video dimensions | 40 million pixels |
| Video duration | 60 seconds; no silent clipping |
| Prepared MP4 | 64 MiB; over-limit/truncated output rejected |
| Child process timeout | 120 seconds |
| Asset deadline for new child stages | 180 seconds |
| Encoding/decoding/filter workers | One codec/filter thread requested, no hardware acceleration |
| Priority | Below-normal Windows child priority; POSIX CLI nice +10 |
| Free disk reserve | 2 GiB plus next output budget before each attempt |
| Child logs | 2 MiB stdout, 64 KiB stderr; monitored without echoing private paths |

There is one child at a time. Timeout/output/log/disk failure kills and waits only
for that owned child. The asset deadline is checked between stages and bounds the
next child timeout; synchronous file reads can add up to their separate 60-second
hash budget. This is **not** a hard OS wall-clock/RSS quota. Disk/log monitors have
a polling interval and can overshoot their threshold briefly. Image dimensions
bound allocations, but no Windows Job Object memory cap is implemented. Canaries
must observe working set and use an external operator stop threshold. Repeated
failed attempts consume retained disk space; no unattended bulk loop is supplied.

For the range-fix rollout and the checkpoint/revision migration limits, see
[the source return and incremental plan](HOME_VIDEO_RANGE_RETURN.md). That plan
requires separate operational approval; this source fix changes no publication.

A publication is an offline snapshot. Live hide/import changes do not automatically
update it, and `publish` does not re-query the live database. Before enabling any
real candidate, revalidate the candidate's intended scope and current hidden state;
regenerate it if those changed. Prepared copies cannot be recalled after download.
Unknown/external/local privileged writers and races remain outside the single-owner
workspace assumption; deployment must keep the workspace private and non-serving.

## Evidence and next gate

[Focused tests and source receipt](evidence/home-preparation/verification.json)
cover resume, interruption, source immutability, output corruption, orientation,
ICC/alpha, rotated video, subtitle/private-tag removal, duration/output/time/disk
limits, and a new disabled full-catalog publication. They use synthetic files only.
The first tooling attempt skipped because a system-Python wheel was incompatible
with the isolated Python 3.12 test environment; it is not counted as test evidence.
After installing the matching temporary CPython 3.12 wheel, all preparer tests ran.
The video rotation fixture initially used a metadata flag that did not generate a
display matrix with the local FFmpeg; the corrected fixture proves that it has a
matrix before testing normalization. Neither failed attempt was hidden as success.

[Measured synthetic canary](evidence/home-preparation/benchmark.json) uses a
12MP EXIF-rotated noise photo and a six-second 1080p synthetic pattern/tone video.
It verifies unchanged original/database hashes, both prepared items, resume, a
new disabled publication, and actual ASGI Range across a 4 MiB chunk boundary.
Measurements are from macOS arm64 / Python 3.12 / Pillow 12.3 / FFmpeg 9.0.1.
They are not Windows throughput, caption-impact, real-format coverage or device
acceptance. The resource receipt states the CPU/RSS accounting limits explicitly.

Next is the [Windows canary and deployment plan](HOME_PREPARATION_CANARY_PLAN.md).
No Windows connection, environment install, real conversion, service change,
network exposure, push or merge was performed by this source slice. Android can
continue its already-frozen v2 fixture work; the real v2 origin remains pending.
