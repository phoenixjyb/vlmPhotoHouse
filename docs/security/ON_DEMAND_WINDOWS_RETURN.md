# Windows on-demand TV rollout — 13 September 2026

The opt-in v3 service is running on a separate LAN-only TLS port. Existing v1/v2
services, selected catalog/control, originals, database and captioning were preserved.
The configured TV v11 installer is published to the owner's existing read-only SMB
APK folder. Physical projector installation and playback remain unverified.

**13 September follow-up:** physical v11 testing exposed cache access failures
under the Limited service account that administrative qualification missed. See
[the service-account repair and memory-pressure return](TV_MEDIA_RECOVERY_20260913.md)
for corrected evidence and TV v12 delivery. Earlier sample checks below retain their
original qualification scope.

## Exact source and artifact

- Deployed backend: `5269257b4b2a791b59f9181aa83d8e70a5d03b4d`.
- Background launcher change: `bdf9232037288a6cdd3395aa34aafbae1cd9b9b0`.
- Android contract pin: `65e40e486d5e35a14f07d692ff5664ba096b7399`.
- Android application source: `e9ce77b2ed068bd734b1098366043c543ab1cf46`.
- TV v11 APK: 10,431,322 bytes; SHA-256
  `3b8f1258a39473096b8d432e1c2310730ca886697fd6f381a3f4a886674b8e5b`.
- Existing debug signer retained. Private origin/LAN routing embedded only in the
  local configured build; no credentials, private source index or media in Git.

## Current coverage and checks

The unchanged catalog has 27,842 entries: 23,599 photos and 4,243 videos.
The read-only photo-header index admits 23,588 photos: 23,573 on-demand displays
plus 15 existing prepared displays. Eleven remain unavailable: two missing files,
eight header-read failures and one unsupported MPO. These are admission counts,
not proof that every file successfully decodes. Video coverage remains two existing
prepared streams; this rollout did not probe or transcode the entire video library.

- Native Windows: 15 delivery tests and nine bounded-launcher tests passed.
  The 15 delivery tests also passed under pythonw, exercising windowless decoder
  subprocesses. The earlier fixture cleanup error was fixed by closing the synthetic
  SQLite connection explicitly; the index builder already closed its connection.
- Four real-photo samples, including two 199,756,800-pixel images and a 56.2 MB
  original: grid/display responses, cache reuse, original HEAD/range equality and
  unchanged source modification times passed. Cold previews took 0.437–1.641 s;
  cache hits took 0.015–0.031 s. Sampled owned RSS peaked at 116,482,048 bytes;
  this is sampled evidence, not a hard peak-memory guarantee. Cache held 3,687,745 bytes.
- First/last-page ASGI checks, both prepared video suffix ranges and denied credential/
  operator-peer requests passed. This is Windows ASGI evidence with a synthetic
  allowed peer, not a physical projector network request.
- Actual listener: trusted certificate and hostname validation passed; the actual
  unapproved operator peer received 403. No peer allowlist or public ingress bypass.
- Listener survived separate SSH calls. A manual Windows task uses the existing
  TV account and Limited privilege level, pythonw, bounded logging and zero automatic
  triggers. It requires the user's Windows login; no reboot/logout recovery was tested.
- Existing API, caption and v1/v2 listener PIDs/start times were unchanged from this
  turn's preflight. Existing control/catalog hashes are unchanged; API health HTTP 200.
- Configured TV debug build and lint passed; signature and SMB operator read-back
  hash verified. Reader ACL remains read-only. No ADB device was attached.
- Independent Android v3 producer/checksum verifier passed after the test-only repin.
  Previous 192 JVM and synthetic emulator evidence remains in the Android return;
  these were not all repeated for configuration-only packaging.

The first direct SSH-launched process ended when its SSH session closed; it was
replaced by the manual task before APK publication. An inspection command expanded
PowerShell provider metadata excessively; it completed and was corrected to plain
file strings. It is not used as a service logger. No persistent diagnostic console
or unbounded service log was introduced.

## Remaining work

Projector acceptance: later pages, previously unavailable photos, Fit/Zoom/Original,
video Play/Pause/Seek and full diagnostic codes on failure. The service keeps the
previous prepared-video path; this is not a confirmed JMGO video-decoder fix.

Next source/runtime slices: conservative full-library video probing, guarded
preparation for incompatible videos, investigate the eleven photo exceptions,
protected prepared-video delivery and authenticated phone endpoint activation,
and v3 discovery/search integration. No real phone credentials/audience were added.

Manual rollback scripts and private deployment receipts are retained in the owner's
local rollout handoff; rollback was syntax-checked, not executed. The old TV v10 APK
is retained, but Android may reject installing a lower version over v11. Do not
silently uninstall a family app; prepare a same-or-higher-version v2 build if needed.
No push, merge, WAN ingress, caption restart or bulk media conversion was performed.
