# Home TV full-catalog contract v2

Status: **source and synthetic integration slice; not deployed**. The user expanded
TV scope to all existing photos and videos on the home LAN, without personal
sign-in or device approval. This replaces selected/latest-N content as the final
product goal. It does not authorize public ingress or private-library exposure
through the legacy API. Android owns the gallery, fit/zoom, fullscreen and player;
this worktree owns catalog export, prepared media and server/network changes.

The exact wire definition is [contract v2](home-catalog-contract-v2.json), including
a Draft 2020-12 response schema, limits, errors and lifecycle. The
[response fixture](home-catalog-response-v2.example.json) is checked against actual
ASGI output. Each future incompatible wire change needs a new version.

## What this slice implements

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/home/v2/catalog` | All published visible IDs, descending; pages of 1–100, default 50 |
| GET / HEAD | `/home/v2/assets/{asset_id}/preview` | Revision-bound prepared grid/display JPEG |
| GET / HEAD | `/home/v2/assets/{asset_id}/video` | Revision-bound prepared MP4; single byte Range for GET |

Start at page 1 without a revision. Later pages must include the returned revision
and the same page size. All requests reject unknown or duplicate query keys. On
409, clear old catalog/media and refetch page 1. A running process refuses a changed
publication with 503 until a controlled release restart; it never mixes snapshots.
This is a snapshot catalog, not an automatic live mirror of new imports/hides.
A removed/hidden item must be removed by a new publication; disable the current
publication immediately if access must stop before that switch.

Each item has `id`, `kind` (`photo`, `video`, `unsupported`), a literal `label`,
nullable original dimensions, `previews.grid`, `previews.display`, `video`, and
`originals_allowed: false`. A ready derivative has exact dimensions, length, hash
and a same-origin relative revision-bound URL. An unavailable derivative has only
`state: unavailable` and `reason`; **no URL**. Reasons are `not_prepared`,
`source_missing`, `unsupported`, or `preparation_failed`. Non-video items have
`video: null`. Labels exported by this slice are generic asset labels, not paths,
filenames, generated captions, location or person information. No search/date/album
endpoint is introduced in this bounded slice.

Grid/display JPEG rules retain v1's normalized baseline/JFIF framing and size
limits. Fit/fill/zoom operates on the prepared display derivative; original-byte
or unbounded-resolution zoom is not available. A larger source dimension in item
metadata is not permission to fetch that original.

Prepared video profile: faststart MP4, one H.264 8-bit yuv420p video stream up to
1920 edge / 1920×1080 pixels, at most 30 fps, baseline/main/high up to level 4.1;
zero or one AAC-LC audio stream. Remove source metadata, subtitles, data tracks,
chapters and attached pictures during offline preparation. Container structure
and ordinary codec configuration remain necessary. This profile is an **offline
publication obligation**: the serving module verifies declared bounds and byte
integrity, not codec conformance or metadata removal by decoding/probing media.
The synthetic fixture was independently probed and decoded. A real preparation
validator is a remaining gate before any real item can be marked ready.

Range GET supports `bytes=start-end`, `bytes=start-`, and `bytes=-suffix` with 206,
exact Content-Length and Content-Range. End is inclusive and clamped to file size.
Invalid, multiple or unsatisfiable ranges return 416 with `bytes */N`, without
media; duplicate Range headers and If-Range return 400. No Range returns 200.
HEAD ignores Range, reports the full length and has no body, following
[RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#section-14.2).
A client may request small chunks (Android's 256 KiB bound works); the server
verifies each containing 4 MiB chunk before sending it. It never buffers a whole
video. Keep at most one playing stream per client. A later integrity/revocation
failure truncates the connection before further bytes; clients must treat that
as a playback failure rather than accepting a partial file as complete.

## Publication and operation

`backend/app/home_catalog.py` is a separate app factory. It imports the frozen v1
configuration/boundary and JPEG utilities but does not mount v1 or the protected
phone app. Neither existing app mounts v2. No existing listener or launcher was
changed. Deploying v2 alongside v1 needs a separately reviewed origin/listener or
composition plan; **do not point the current v3 APK at v2 or replace v1 silently**.

A new private publication contains:

```
publication/
  control.json
  catalog.json
  prepared/
    grid/<id>.jpg
    display/<id>.jpg
    video/<id>.mp4
    video/<id>.chunks.json
```

Control keys are exactly `version: 2`, `enabled`, `revision`, and
`catalog_sha256`. The catalog's fixed sibling name is `catalog.json`; its exact
keys are `version`, `revision`, `library_id`, `title`, and `assets`. Published
assets use the response item shape without URLs or `originals_allowed`; ready
video metadata additionally includes `chunks_sha256`. The sidecar is a JSON
array of SHA-256 hashes for consecutive 4 MiB chunks, including the short last
chunk. No manifest-supplied filesystem path is accepted.

`build_home_catalog.py --database <explicit-local-db> --output <new-directory>
--revision <N>` opens SQLite with `mode=ro` and `query_only`, reads all active or
legacy NULL-status rows, excludes hidden rows, fails rather than truncating above
100,000 assets, and writes a **disabled** metadata-only publication. It has a
60-second query progress budget and never reads originals, derives media, imports
app settings or creates jobs. This exporter was tested with synthetic SQLite;
it has not been run to publish the real catalog.

`build_home_catalog_fixture.py --output <new-absolute-directory>` creates an
**enabled synthetic** publication with the committed 8×8 JPEG and half-second
color-pattern/tone H.264/AAC MP4. It does not listen. Preserve it as an integration
fixture; do not interpret its repeated-pattern transport stress cases as valid
playable videos.

`home_catalog_app.py --config <private-config> --check-publication` validates
launcher syntax and enabled publication metadata only. `--serve` starts the
separate factory with the same explicit TLS/private bind/no-forwarded-trust
options as v1. Config format remains launcher version 1; its `manifest` points to
v2 control. Catalog and control must be outside prepared media. Check mode does
not verify every media byte or certificate and opens no listener.

Prepare immutable bytes and metadata in a fresh publication. Verify them offline,
then stop only the owned v2 service, switch its private configuration, and restart.
Keep the prior release/publication/config for rollback. Do not update JPEG/MP4 or
catalog bytes under a running process. The one allowed in-place control action is
atomic `enabled: false/true` with the same revision/hash. Four admissions include
active streams; overload is 429 / Retry-After 2. A disable is checked before every
request and between stream chunks; already admitted/sent bytes cannot be recalled.

No new runtime dependencies are required. The MP4 fixture was made locally with
FFmpeg's synthetic `testsrc2` and `sine` sources, H.264 constrained baseline level
3.1, AAC-LC, 320×180 at 24 fps, duration 0.5 s. No real media or model was used.

## Catalog evidence and limits

[Read-only inventory](evidence/home-catalog-v2/catalog-inventory.json) found 27,842
visible rows: 23,599 photos and 4,243 videos; 364 hidden rows excluded. The count
matches the existing localhost `/assets` count, and all visible paths lie under
the configured originals root. The canonical SQLite file was read directly;
no database or source-media bytes were copied to the Mac. Live launcher environment
was not re-derived, so count agreement is corroboration rather than proof of the
active process's complete configuration.

Formats: 23,591 JPEG photos, eight PNGs, 4,211 MP4 and 32 MOV videos. Registered
sizes total approximately 82 GB for photos and 564 GB for videos; these are DB
metadata sums, not a complete file-availability scan. The latest 200-ID stat-only
sample found 200 originals, 169 existing 256 previews, no 512 previews, and frame
directories for all 52 sampled videos. Four bounded ffprobe samples found two
8K HEVC MP4s and two H.264 MOVs with extra data tracks. This proves that copying
all MP4 originals is not a sufficient compatibility or privacy strategy; it is
not a population-wide codec census. No source image/video was decoded in this
remote inspection, and no jobs/models were invoked.

The first metadata query hit its 15-second progress deadline; one bounded retry
completed in 4.719 seconds. Source paths and detailed per-file probe results remain
private. Caption/API process identities and start times matched the earlier pilot,
and both owned v1/DNS tasks remained running. Process continuity does not establish
caption progress or full service health; `/health` was deliberately not called.

The user reported that v3 connected on the physical JMGO and rendered the striped
synthetic picture. Record that as user-observed connection/rendering only. Remote
controls, slideshow, sleep/wake and real photo/video playback remain separate gates.

## Security gaps and next implementation

This inventory does not fix existing legacy authorization failures. The legacy
loopback web media route still reads original paths without a principal/membership
check, and its thumbnail route can generate files on demand. They are not exposed
by either TV factory and must never be forwarded/remounted as a shortcut. Protected
phone pin `87a60b475b37b1d6873cd977bcb6e7254472da7e`, v1 source and v1 contract remain
unchanged. Real hidden-state changes do not automatically revoke an offline snapshot.

LAN peer checks rely on network isolation: proxies/SNAT could hide an outside
client behind an allowed address. There is no account/device revocation, global
abuse-rate control, or ability to recall downloaded content. Windows junction,
firewall, guest/WAN, TLS streaming and actual device playback need deployment
checks; synthetic ASGI is not evidence of those outcomes. Slow clients can occupy
the four stream slots; native server concurrency/keepalive bounds are not a complete
slow-client defense.

Next backend slice: implement and synthetically test a resumable offline preparer
with explicit source-root validation, EXIF orientation, normalized JPEG export,
MP4 probe/normalization verification, output hashes/chunks, disk/CPU/time budgets
and honest per-item failures. Use Drive E for real derivatives. Then perform an
owned bounded canary (one photo and one representative video), measure CPU/storage
and caption continuity, and choose a compatible v1+v2 deployment plan. Do not bulk
transcode the 564 GB video collection while captioning is active. Whole-library
metadata, prepared-media coverage, deployment and physical playback are distinct
completion gates. Android may wire/test this frozen contract against synthetic
fixtures immediately; real-v2 origin/publication is still pending.
