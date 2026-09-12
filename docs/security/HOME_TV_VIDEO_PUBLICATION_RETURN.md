# TV video publication and v9 installation handoff

2026-09-12, 21:19 +08. Windows JIAFAMILY now serves **revision 2 with 15 photos
and two short videos ready** from the existing private TV v2 listener. The catalog
contains 27,842 entries; 27,825 remain unavailable in this publication. This is
partial prepared-media coverage. The two playable clips last 1.514 and 1.856 seconds;
the longer qualification outputs are not yet published.

Backend worktree: `/Users/yanbo/Projects/vlm-photo-engine/_worktrees/home-tv-video-publication`.
Branch: `codex/home-tv-video-publication`, based on
`ccd4de33b09b169a34661f946a1c3799cc48d8af`. This slice changes documentation/evidence
only in Git; the authorized Windows operation changed the v2 publication pointer
and restarted only the existing v2 task. No source deployment, push or merge ran.

## Publication and runtime

The reviewed disabled revision-2 candidate was copied into the independent
Windows directory `E:\VLM_DATA\derived\home-tv-live-revision2-20260912`.
Its selected original hashes and metadata were rechecked read-only, all clone
files matched the candidate, and all 16 previously ready asset records and media
hashes were preserved exactly. Thirty-four prepared JPEGs decoded successfully.
Only the clone was enabled. The original disabled candidate, pinned by the
qualification job, remains unchanged; the revision-1 live directory is retained.

The existing v2 config changed only `manifest` and `media_root`. Task definition,
firewall, TLS configuration, allowed networks, source and serving options were
not changed. The existing task `PhotoHouse-HomeCatalog-V2-Canary` now owns native
pythonw PID 8580, redirector 6864, on `192.168.0.108:8445`. Console window is zero;
ancestry contains no Terminal/console host. The launcher receipt says `starting`;
separate listener and TLS probes establish the live-server evidence.

| Artifact | SHA-256 |
| --- | --- |
| Catalog revision 2 | `7fd30c43a677236e6bfe8ac62221514c1842d796370428701af9966ee1903eb4` |
| Enabled clone control | `65480031086cb92d4435ae77edc825013d03e4b158731a7bf4d81e0cee9b40c2` |
| Active config | `fcb0701d894bbe321a7276e1b2c2625d808307fb223752e49f2834f5d442d21c` |
| Previous config | `e2721c645a49e9e63e2efbfe958972ea56c225e959232bc248e335c125a1c63c` |
| Original candidate disabled control | `43bcc997650e2ce5c4f6848829702292b29af6ae70987638332d4e18c87ed211` |

V1 PID 16020, caption PID 10460 and API PID 23284 retained their original start
identities. No model was loaded, no original or metadata database was written,
and no caption work was stopped or retried. Available RAM after activation was
54,090,301,440 bytes (about 50.4 GiB).

## Verification and limits

- Candidate media checks: 17 selected original hashes/metadata rechecked before
  and after; 34 JPEG previews decoded with dimensions, RGB and EXIF checks;
  both MP4 and chunk hashes matched; previous 16 ready entries exactly preserved.
- Direct bounded ASGI checks used the actual serving source/dependencies and
  prepared candidate media, with a synthetic approved peer. Disabled control
  returned 403. Enabled review control returned catalog 200, stale revision 409,
  34 preview HEAD 200 responses and both video HEAD 200 responses. All video bytes
  were fetched through 57 Range 206 requests and rehashed; EOF returned 416 and
  stale video revision returned 409. Closed routes and spoofed peers returned 403.
  The temporary review control was removed; no listener was opened by this test.
- After activation, nine native live requests passed trusted hostname TLS 1.3
  and returned expected 403 for the unapproved server peer, including spoofed
  headers and video Range. Certificate verification remained enabled.
- Existing task definition and firewall snapshots matched, and unaffected runtime
  process/start identities matched. No live rollback was rehearsed.

Successful real requests from an approved LAN device and physical projector video,
seek, audio, focus and Back behavior still require device acceptance. The Mac is
off the home LAN. Approved peers remain `192.168.0.102/32` and
`192.168.0.109/32`; the audience was not widened for testing. Source/ASGI, live TLS,
and physical playback are separate evidence.

## Qualification completed separately

The resumed 12-case `library-sdr-v1` qualification finished at 21:09:21 +08 with
12 ready, no working entries, and 27,830 pending. It did not start bulk preparation
or publish its output. Cases included 199.8 MP JPEG input with bounded subsampled
decode, 8K HEVC, a 13m36.7s largest/longest video, an 11m4.1s full-range video,
carry-over verification and both earlier diagnostic cases. All twelve are ready.
The full-range case required a second attempt after the earlier memory stop.

The resumed pass observed a 406,441,984-byte peak RSS and minimum available RAM
52,786,204,672 bytes. These are sampled coordinator/immediate-child observations,
not an OS-enforced process-tree quota. Historical checkpoint resource totals still
include the earlier memory-pressure stop; the final current runner receipt is
used for resumed-run observations. Free disk was about 5.24 TB. All-video worst-case
output caps exceed that capacity, so do not infer that full-library bulk preparation
is capacity-qualified or that it has started.

The next backend step is to review a publication that preserves the 17 currently
ready assets and adds the completed qualification outputs, then validate full
Range/decode behavior and publish through the existing controlled workflow.
Publishing freezes the job; further preparation requires an appropriate new
revision/carry plan. Do not casually change the prior-publication pin or present
these 12 cases as full-library completion.

## Rollback

Private Windows stage `%LOCALAPPDATA%\PhotoHouseAccess\tv-publication-20260912`
contains the exact `config-revision1.json` backup, staged new config, task/firewall
snapshots, preflight/switch scripts and receipts. To roll back this publication,
first verify the current v2 task, config hash and process/start identity; stop
only that task and wait for its owned processes/listener to exit; restore the
exact revision-1 config atomically; then start the same task and repeat listener,
TLS and approved-client checks. The revision-1 publication was not modified.
Do not use the older background-launcher rollback for a publication-only rollback.

[Aggregate verification receipt](evidence/home-tv-video-publication/verification.json)
contains media, ASGI, runtime and completed qualification evidence without original
media paths or asset identifiers. Earlier runtime history is in the
[background recovery return](HOME_FEED_BACKGROUND_RECOVERY_RETURN.md).

## TV APK ready to install

The Android owner completed TV v9 on clean branch `codex/android-tv-v9-install`
in `/Users/yanbo/Projects/mobileAppForPhotoHouse-android-tv-v9`.
Source commit: `0a4291ec2b02ec0668e823eb7d2d660484e63327`.
Evidence HEAD: `db7d8344d922409b6b3db5b8e9511c1c02748685`.
Its return is `docs/evidence/android/tv-v9-install/RETURN.md` in that repository.

Install file:
`/Users/yanbo/Downloads/PhotoHouse-TV-v9-20260912/PhotoHouse-TV-v9.apk`.
Size: 10,411,068 bytes. SHA-256:
`6535fa69e852671443f943be85bef1f54bb1b494f993a3299b84befa55df6c82`.
This backend task independently verified the local size and checksum against the
Android receipt. Package `dev.photohouse.tv`, versionCode 9, minimum Android API 26;
the development signer matches v8. Update v8 in place without uninstalling.
The folder includes bilingual installation instructions, checksum and artifact receipt.

The Android owner reports 87 JVM tests, all 25 synthetic UI tests at each of font
scales 1.0 and 2.0, build/lint with zero errors (three existing warnings), and
configured-APK install/cold-start on its owned API 36 landscape phone emulator
with networking disabled. Rendered gallery, Chinese page dialog and video controls
were inspected. This does not establish physical TV or TV-launcher acceptance.

The APK includes the existing private HTTPS origin on 8445 and app-only LAN
mapping to 192.168.0.108; catalog v2 is selected and search/discovery is disabled.
No test media is packaged. At 21:20:51 the Android owner independently confirmed
live enabled revision 2, matching config/control/catalog hashes, PID 8580, trusted
TLS with expected unapproved-peer 403 and preserved v1/API/caption identities.

The `forTV` USB volume was not mounted, so the APK is in Downloads. Copy it to the
USB drive, open it in the projector file manager, choose Install/Update, and open
PhotoHouse on the home LAN. Then test both ready clips for Play/Pause, seek,
fullscreen, Back and sound. No physical installation was performed.
