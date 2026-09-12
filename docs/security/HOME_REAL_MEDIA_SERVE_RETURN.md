# PH-HOME-REAL-MEDIA-SERVE-01 — bounded real-media service

Verified on 2026-09-12: the separate home-LAN catalog v2 service is running with
**15 real photos and one real video ready**, all on page 1 at page size 50.
The complete visible catalog snapshot contains **27,842 entries**: 23,599 photos
and 4,243 videos. **27,826 entries remain unavailable.** This is partial media
coverage; no whole-library transcode or physical TV acceptance is claimed.

## Source, environment and review

Branch: `codex/backend-home-tv-feed`, owned worktree
`_worktrees/backend-home-tv-feed` in the PhotoHouse workspace. Started from
`738863d3a87708b4dbf14d7ef779c08e6ce3c364`. The only implementation change is the
native test-harness correction at **`7795133091c412ea7b1cfd9de8ac2271285bf7f0`**.
The subsequent evidence commit is identifiable with
`git log -1 --format=%H -- docs/security/HOME_REAL_MEDIA_SERVE_RETURN.md`.

All production preparer, serving, launcher, authorization and contract blobs are
unchanged. The native deployment verified **318 committed source-file hashes**.
[Relevant source pins](evidence/home-real-media-serve/source-inputs.json) include
the unchanged preparer and catalog v2 contract, the exact test delta and locks.

The new private Windows release uses a separate Python 3.12.10 CPU environment,
hash-locked access/test dependencies and Pillow 12.3.0. Existing native FFmpeg and
ffprobe 7.1.1 executables were pinned by SHA-256. No serving/caption environment,
model installation or existing credentials changed.

Native testing initially exposed fixture resource leaks and Windows test-harness
assumptions. Fixtures now explicitly close SQLite connections after transaction
completion. The test-only socketpair exception accepts only the exact stdlib
asyncio self-pipe callers; application bind/connect methods remain blocked.
Three new tests verify this boundary. Windows asyncio uses a temporary internal
loopback wakeup listener, closed before the pair returns; no application service
listener is started by these tests. Native tests use explicit UTF-8 and a private
local Git index for inventory discovery. No tests were suppressed or skipped.

## Verification and measured scope

- **84 native Windows tests passed**, zero failures/errors/skips, in 35.728 seconds:
  20 preparer, 24 v2, 18 v1, 19 inventory and three native guard tests.
- The same **84 tests passed on Mac** in 6.805 seconds. The route inventory remains
  complete at **162 method/path entries**; no new route was added.
- The native synthetic benchmark passed a rotated 12MP photo and six-second 1080p
  video, full decode, metadata/orientation checks, integrity, verified resume and
  ASGI Range crossing the 4 MiB boundary. Preparation took 12.485 seconds.
- The real rotated photo and short video passed original-hash checks, output
  geometry/metadata validation, full video decode and ASGI preview/HEAD/Range/hash
  checks. The successful video canary took 5.766 seconds, with 0.937-second resume.
- The 14-photo follow-up batch took 20.156 seconds; verified resume took 1.235
  seconds. The first served publication occupies 22,887,878 bytes including its
  complete catalog. Every ready item has verified grid/display derivatives.
- The observed maximum owned-process peak working set was 366,481,408 bytes for
  the successful video canary and 201,478,144 bytes for the photo batch. Available
  RAM remained above 50.9 billion bytes in these samples. Sampling uses one-second
  sleeps plus polling overhead; CPU deltas are lower bounds, not complete child
  accounting or a hard OS memory quota.

The first H.264 MOV canary remained full-range `yuvj420p` after native conversion.
The existing normalized-output check correctly refused it. Its retained journal
entry remains `preparation_failed`; validation was not relaxed. A short 1080p,
eight-bit SDR HEVC source within the existing profile produced valid H.264/AAC
output. Newer candidates outside the bounded selection were left unprepared.

All source media stayed on Windows. Selected original hashes, selected asset metadata and
database schema remained unchanged. Database reads used read-only/query-only
connections. A fresh export of the complete visible catalog matched the base
immediately before enable. Caption writes continued, so no unchanged whole-live-
database hash is claimed. Human visual review on Windows/TV is still outstanding;
orientation geometry, pixel format, metadata and decode checks are automated.

## Live service, isolation and rollback

The service uses the existing certified hostname on a distinct private-interface
port, the existing two TV/operator peers and new v2-only allow/complement-block
rules. The new task runs as the existing limited interactive user, has no startup
trigger and has distinct logs/configuration. Exact origin, mapped address, IDs,
paths, process identities and reproduction receipts are in the private operator
handoff, directory `photohouse-real-media-20260912`.

Initial limited-task startup could not read the new publication because Windows
mode-0700 directory creation assigned Administrators ownership. Only that new
derivative publication received explicit task-user read/traverse access. No
original, database, certificate, credential or existing-service ACL changed.

Live evidence includes:

- Trusted HTTPS catalog 200; prepared photo/video HEAD 200 and Range 206.
- Server peer and spoofed forwarded-peer requests denied with 403. Wrong Host and
  accidental personal credentials also receive 403. Eleven legacy, account,
  voice, operational and disabled-discovery paths remain closed.
- Disabling the new publication makes both catalog and video HEAD return 403.
- Stopping only the v2 task removes its listener. Removing only its two firewall
  rules leaves v1 available over trusted HTTPS. Restoring those same scoped rules
  and restarting v2 returns the exact first-served page at revision 1.
- The existing v1, API and caption process identities/start times were retained.
  Caption rows advanced from 41,762 to 41,810 across the operation; API non-model
  response probes succeeded. Captioning was neither paused nor restarted. DNS and
  protected staging task states were preserved.

Android independently reported that its production `HttpsCatalogApi` adapter
passed normal-trust mapped HTTPS, all four canary JPEG previews, the complete
383,496-byte video through bounded Range reads, full SHA-256, EOF, backward seek
and stable repeated page 1. Its final feed recheck after rollback/restoration also
passed. Media stayed in memory for that adapter check; no media files were saved
on Mac. Backend checks retrieved catalog metadata, headers and a discarded one-byte
Range response. No real media or database file was copied to Mac.

All coverage changes happened before the first revision-1 serve. The failed MOV
and unprepared entries remain visible honestly; descending-ID ordering is intact.
Any future changed catalog or coverage publication needs a higher revision with
coherent control/catalog hashes and renewed current-scope validation.

## Receipts and next step

[Verification](evidence/home-real-media-serve/verification.json),
[native tests](evidence/home-real-media-serve/native-tests.log),
[Mac tests](evidence/home-real-media-serve/mac-tests.log),
[native synthetic benchmark](evidence/home-real-media-serve/native-synthetic-benchmark.json),
and [source pins](evidence/home-real-media-serve/source-inputs.json) are sanitized
repository evidence. Private receipts retain unsuccessful attempts, native logs,
resource samples, source selections and service configuration for review.

Next: Android owns configured APK delivery and physical TV photo/video/D-pad
acceptance. Then review another bounded coverage batch, including an explicit
full-range video normalization fix and measured larger-source handling where
needed. Snapshot hide/import freshness is not automatic. Discovery remains
disabled, and this work adds no protected-phone discovery transport. Reboot/logon
persistence is not established by the manual interactive task.

This bounded run is complete. No further conversion, push, merge, public ingress,
legacy service exposure or Android source edit was performed by this backend task.
