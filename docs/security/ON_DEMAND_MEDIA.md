# On-demand photo and original-video delivery

Source candidate, 13 September 2026. No Windows activation or physical-device
acceptance is implied. The existing v2 publication and all originals are preserved.

## Behavior and contract

A catalog entry no longer needs a converted photo to open. The explicitly selected
catalog is joined offline to original paths in a private, immutable source index.
Indexing JPEG/PNG reads headers, not decoded pixels, and never re-encodes photos.
Missing, unsupported and unselected sources do not acquire URLs. Index files contain
private paths and must stay off Git and outside any media share.

TV v3 is a separate, opt-in protocol. `/home/v3/catalog` retains the v2 pagination,
revision and asset fields and adds `original` (null or `{mime,bytes,width,height,url}`).
Photo previews are either the existing ready/unavailable forms or
`{state:"on_demand",url}`. On-demand URLs return bounded normalized JPEG bytes;
clients validate the actual dimensions and byte budget, rather than trusting a
fictional precomputed hash. Prepared responses retain the existing hash checks.
`originals_allowed` is true only when the item advertises raw photo or direct-video
access. Exact same-origin paths and current revisions are mandatory.

`/home/v3/assets/{id}/original?revision=N` returns selected JPEG/PNG bytes unchanged,
including embedded metadata. GET/HEAD and single byte ranges are supported. Raw
access is off unless the launcher explicitly receives `--allow-originals`. This
is the owner's anonymous home policy, not phone authorization or a public URL.
Original-photo admission is limited to 64 MiB, 256 million source pixels and a
32,768-pixel dimension. Android decodes at bounded resolution (TV 8,847,360 pixels;
phone 4 million); original-file delivery is not unlimited-resolution/tiled zoom.

Grid requests generate a 512-edge JPEG only; display requests generate a 4,096-edge,
8,847,360-pixel JPEG only. EXIF orientation and supported color profiles are normalized.
JPEG quality is 86, matching existing display preparation. Compatible prepared
images are reused first. Animated, damaged or over-budget sources can still fail;
a listed original is not a successful decoder result. A first miss may take time.

The private server cache has a 512 MiB default budget and evicts least-recently-used
owned JPEG entries before adding a new one. It refuses non-owned/nonempty folders.
One decoder per cache instance, no pending queue, 15-second worker deadline,
4 GiB available-RAM floor, 1 GiB sampled process RSS ceiling and 2 GiB disk reserve.
The memory guard is sampled, not an OS hard quota. Use separate protected cache
folders for phone and TV and one service writer per folder. A requested source is
copied from its checked descriptor into a temporary private worker directory;
this temporary snapshot is removed after rendering. Originals are never overwritten.
Android retains bytes in memory only; no persistent Android media cache is added.

## Video policy

Prepared v2 H.264/AAC MP4 remains the first choice when present. Optional offline
`--ffprobe` indexing also admits original MP4 with one H.264 Baseline/Main/High
stream, level <=4.1, yuv420p SDR, <=1080p pixel area, <=30 fps, no rotation side data,
and at most one AAC-LC mono/stereo audio stream. Those items use `state:"direct"`
in v3 video metadata, without a fabricated whole-file hash. Each Range request
and streaming chunk checks the selected source identity and current publication.
No complete-file download is needed before playback.

HEVC, 4K, HDR, rotated, unsupported audio and uncertain profiles continue through
the existing guarded preparation pipeline; this change does not claim universal
hardware decoding or start bulk conversion. Phone already streams permitted
original MP4/WebM through its authenticated range reader. Protected prepared-video
access for a phone viewer without original permission remains a separate contract.
No fallback silently grants original access. The JMGO playback failure still needs
physical v10-or-newer diagnostic evidence; delivery changes alone do not prove a fix.

## Protected phone and web

With an explicit PhotoCache runtime, missing `/assets/{id}/thumbnail?library=...`
requests generate a grid. New `/assets/{id}/display?library=...` GET/HEAD produces
an optimized display JPEG using `library.read`, with current session, membership
and asset checks both before source access and after rendering. The default
runtime has no cache and does not decode. Existing `/media` original-byte policy
is unchanged. The phone opt-in build opens optimized photos first and exposes an
explicit Original quality action only when original access is permitted.
The protected web thumbnail route benefits from the same optional server behavior.

## Operator staging sequence (not executed)

1. Select the exact current catalog/control and original root, preserving the live
   v2 publication. Run `build_home_source_index.py --database ... --catalog ...
   --source-root ... --output NEW_PRIVATE_INDEX` with the reviewed CPU environment.
   Omit `--ffprobe` for a photo-first index; add an explicit binary for video probes.
   Record the returned checksum and coverage. A new index never overwrites an old one.
2. Run `home_originals_app.py --config EXISTING_REVIEWED_TLS_CONFIG --sources INDEX
   --sources-sha256 SHA --source-root ROOT --cache NEW_PRIVATE_CACHE --allow-originals
   --check`. This validates metadata without opening a listener or decoding images.
   LAN peers, hostname and TLS settings remain explicit. Cache/index must not overlap
   originals, configuration, certificates, database or old publications. Windows
   ACLs must restrict them to the service identity and administrators.
3. Separately stage the v3 service with `--serve`; first test catalog pagination,
   a large/rotated photo, cache miss/hit, original equality, video ranges and disable.
   The TV APK must explicitly select catalog version 3; v2 APKs keep their old path.
4. For protected phone staging, `staging_app.py --photo-cache NEW_PRIVATE_CACHE`
   opts into the same bounded preview service; preserve the existing TLS/database/
   authentication configuration. Enable `photohousePhonePhotoDeliveryEnabled=true`
   only for that matched phone/backend candidate. No original grant is changed.
5. Review the exact configured APKs and device behavior before replacing a family
   install. Roll back by restoring the prior launcher/artifact; original source
   and existing prepared copies were not modified. No automatic cache/index refresh,
   service restart, scheduled task, public ingress, push or merge is included.
