# Home TV backend readiness — Android integration may proceed

**Latest pilot status:** the authorized Windows synthetic pilot passed 37 real HTTPS
checks. It is now stopped with temporary firewall rules removed; normal projector
DNS and device acceptance remain pending. Direct SSH is resolved. See the
[pilot return](HOME_TV_LAN_PILOT_RETURN.md). The preparation-only authorization and
local-packaging statements below describe the earlier readiness milestone.

**The anonymous feed contract is frozen and ready for local Android integration.
Synthetic LAN deployment is planned, not authorized or executed by this follow-up.**
The user chose selected-photo sharing without personal sign-in or device approval.
The protected phone API remains unchanged. There is no remaining access-policy
choice for Android to resolve, and no need to wait for a serving origin before
implementing its TV-specific adapter against synthetic fixtures.

## Exact implementation and contract

Worktree: `_worktrees/backend-home-tv-feed` in the PhotoHouse workspace.
Branch: `codex/backend-home-tv-feed`.
Runtime implementation pin: `e6b2827842b2c0b5223c85208299b60e8a1257f6`.
Later readiness-document commits do not replace this implementation pin.

| Input | SHA-256 |
| --- | --- |
| [Contract v1](home-feed-contract-v1.json) | `70328a653ddaa559bad6a4d654cf9870c89c5217e8e9e6c46a3501e9dd9e7548` |
| `backend/app/home_feed.py` | `c7f22deab8cd58a7bc6060ce6427086568a30073c13917727da30be9865cf37c` |
| `scripts/home_feed_app.py` | `98c2bbcda284cfbc39f2d6c6bf2468ecae1c66952f2bad2ac512b09c3704a8ed` |
| [Synthetic selection](home-feed-manifest.example.json) | `90e49245370c3695de22d5c0bd261c0bee9bfd9ce99f7085c3d1e652e30600d7` |
| CPU runtime lock | `b4e4e92f67dd3740986494ff3c8cc4b10557fd41329efee030dda03e05897a42` |

All 12 entries in the retained [source-input manifest](evidence/home-tv-feed/source-inputs.json)
were freshly verified. The independent frozen phone pin remains
`87a60b475b37b1d6873cd977bcb6e7254472da7e`. There is no SQLite schema change.

The [implementation guide](HOME_TV_FEED.md) and contract define the three operations:
GET feed, GET prepared preview and HEAD prepared preview. The TV adapter sends no
Authorization or Cookie header, uses relative revision-bound grid/display URLs,
and exposes no original mode. Display derivatives permit 3840x2160 within the
4,096-edge, 8,847,360-pixel and 12-MiB limits. Missing previews are placeholders;
there is no provider/original/personal-API fallback.

## Selected feed and lifecycle

The initial deployment proposal contains only fixture feed `synthetic-home`, asset
101, literal synthetic caption, an 8x8 grid fixture and a generated 3840x2160 display
fixture. Both exact hashes are in the contract/example and source manifest. These
are deliberately different synthetic test patterns; this is not a real-photo
export or a claim about source-thumbnail correspondence. No real library is selected.

For selection-only changes where prepared bytes stay unchanged, write a complete
valid manifest next to the active one and atomically replace it on the same volume.
Increment revision. `enabled=false` denies new admissions with 403 `feed_disabled`.
Removal excludes the ID from feed pages; old-revision preview requests get 409
`feed_changed`, and missing IDs at the current revision get 404 `preview_unavailable`.
An enabled empty selection returns HTTP 200 with no items. Malformed/missing state
fails closed with 503; no last-known snapshot is served.

Prepared files have fixed paths relative to the configured media root. A change
of those bytes needs a fresh publication directory and a **stopped TV-service
release switch**, not a claimed atomic update of unrelated files: stage/verify the
new publication, stop only the TV task, atomically replace its private config with
the new manifest/media-root pair, and restart. Keep previous publications for
rollback. Do not edit JPEGs underneath a live manifest or repoint the caption service.

Android cold start/foreground fetches the feed directly. On revision conflict it
clears stale content and refetches metadata. Background/disconnect/denial stops the
slideshow and clears/covers content; old connection generations cannot restore it.
Visible metadata revalidation is at least every 60 seconds. Reconnect uses bounded
2/5/15/30/60-second delays with jitter and honors `Retry-After: 2` on 429. There is
no password/token renewal. Requests already admitted may finish and copies already
downloaded cannot be recalled; this feed has no per-device revocation.

## Local staging artifact, newly verified

A deterministic ZIP was built from regular Git blobs at the exact implementation
pin, using a fixed ten-file mapping. It contains seven source/lock/guide files,
the synthetic selection and two generated JPEGs, plus `artifact.json`. It includes
no wheels/venv, TLS files, private config, credentials, legacy server or real media.

- ZIP SHA-256: `934339ab96ed42a6301ad45acf6aa51bb917b9b6947e03c0d3ccecd72fbe0b79`.
- Size: **596,784 bytes**; ten payload files plus the artifact manifest.
- [Bundle receipt and member hashes](evidence/home-tv-feed-readiness/bundle.json).
- Fresh extraction verified exact membership and every checksum. A fresh isolated
  Python process imported only the extracted feed implementation, passed config
  syntax validation and **ten actual in-process ASGI checks**, including exact
  contract response, real 4K fixture bytes, HEAD, denial, disable/removal/revision
  and public-peer rejection. Socket bind/connect, process spawning and SQLite were
  blocked. [Smoke result](evidence/home-tv-feed-readiness/smoke.json),
  [replay harness](evidence/home-tv-feed-readiness/package_smoke.py).

The 296 security tests, including 18 feed tests, remain the earlier verified result
at the implementation pin. They were **not rerun** for this readiness/document
follow-up. New verification is separated in the
[readiness receipt](evidence/home-tv-feed-readiness/verification.json).
The durable bundle and candidate host/origin proposal have a private operator
reference `HOME-FEED-E6B2827-PROPOSAL`; they are not public APK inputs or deployment
approval. No serving origin is approved by this note.

## Concrete synthetic LAN deployment sequence

The [machine-readable plan](home-feed-deployment-plan.json) retains actual
host/origin/operator values only in the private handoff and records current gates.
The original private proposal suggested reusing the
existing Windows host with a distinct home-feed port; all historical values require
fresh verification after authority. The proposed task must be independent of the
protected API and ongoing caption runtime.

1. **Select target and authority.** Record the approved operator and window, current
   Windows identity, unused RFC1918 bind address/port, service principal, task name,
   new private release/publication paths, actual home/guest/projector network and
   narrow peer CIDRs. Do not infer these from a previous protected-service success.
2. **Resolve normal client DNS and trust.** Choose the HTTPS hostname and ensure the
   projector normally resolves it to the selected LAN address. A public DuckDNS WAN
   answer, server-local check or `curl --resolve` alone does not satisfy this gate.
   Do not assume the router supports a local DNS override. If reusing a hostname,
   review the effect on phone/web clients; a distinct hostname requires its own
   reviewed DNS/certificate choice. Verify the actual system trust chain/hostname
   on the client, certificate expiry/key ACLs and future renewal/reload ownership.
   No user-CA, IP-hostname mismatch or trust bypass is part of the plan.
3. **Prepare a fresh runtime and publication.** Verify the ZIP receipt independently,
   exact members, source hashes and existing CPU lock. Install/verify a separate
   runtime with the locked wheels, `pip check` and the runtime environment probe.
   A proposed layout is `release-e6b2827/source/`, `publication-r1/selection.json`,
   `publication-r1/prepared/{grid,display}/101.jpg`, private `config.json`, logs and
   venv under a new operator-controlled root. Use the bundle's synthetic fixtures
   only. Config/manifest/certificate/key remain outside prepared media. Record ACLs.
4. **Validate before serving.** Run the explicit launcher `--check-config` on Windows.
   That proves syntax only. Inspect matching certificate/key, native paths, port
   availability, selected manifest, JPEG hashes/dimensions and process/task identity.
   Keep a reviewed stop/restart command that names only this new TV task.
5. **Apply only the separately authorized deployment.** Start the new task on the
   selected private interface. Restrict host ingress to the intended LAN peers.
   No public forwarding, DMZ, UPnP mapping, public reverse proxy or routing from the
   protected API into this feed. Review SNAT/proxies: a source-IP check cannot detect
   outside clients hidden behind an allowed LAN address. No change to captioning.
6. **Record real network evidence.** From allowed LAN verify normal DNS, trusted
   HTTPS, exact feed/version, no-store, preview bytes/hash/4K dimensions and HEAD.
   Verify the old account/operational/original routes and Range remain denied.
   Confirm disallowed/guest/outside sources cannot read the feed, including proxy/
   forwarding behavior. Record network isolation separately from ASGI denials.
7. **Rehearse lifecycle and rollback.** Publish disabled state, restore enabled state,
   remove the synthetic asset with a new revision and observe all expected statuses.
   Rehearse the fresh-publication stop/config-switch/restart sequence and rollback
   while preserving old publications. Verify caption/protected-service identity is
   unchanged. Re-enabling or restarting this feed must never activate a real selection.
8. **Return to Android for device acceptance.** Bind the actual serving origin,
   service/source/package/lock identities, normal DNS/trust and network receipts to
   the selected projector/firmware, configured APK/signature, installation operator
   and separately authorized window. Actual projection, remote keys, sleep/wake,
   foreground refresh and disable behavior remain device evidence.

No host, router, DNS, task, firewall, certificate, credential, real-media or physical
installation action was performed in this follow-up. Packaging and local ASGI
verification do not remove any of those unresolved operational gates.

## Android local integration reviewed

PH-ANDROID-HOME-FEED-01 is complete locally at Android source commit
`e8ab9be3c5497778783edf1b4a009707922248d1`, with evidence commit
`c866c74de881a24714282bbb8c426f7c29d03103` on `codex/android-tv-foundation`.
The backend review found no blocker in the inspected HTTPS transport and lifecycle
store. This is a bounded review, not an exhaustive security audit. The frozen
backend implementation and contract above remain unchanged.

Fresh checks verified all 29 recorded Android source hashes against both working
files and pinned Git blobs, both APK hashes and sizes, exact backend contract match,
and absence of assets in the main APK. Android SDK tools independently verified
the APK v2 signature, package `dev.photohouse.tv`, version code 2 and version
`0.2-home-feed-dev`. The debug APK is 8,779,354 bytes with SHA-256
`3fba5917cd0215f4696d4bdc8ae1e962e787409273c7ed92f574301aaec3c0d1`;
signer SHA-256 is
`56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28`.
The [review receipt](evidence/home-tv-feed-readiness/android-review.json) binds
these checks to the Android evidence files.

Android's retained results report 110 passing JVM tests, ten actual backend ASGI
checks, successful APK builds, zero lint errors with three existing warnings,
and eight emulator tests each at normal and 2x font scale. These tests were not
rerun during backend review. The emulator was a landscape phone AVD, not the JMGO;
its 3840x2160 fixture decode does not prove projector surface resolution or quality.

The TV app automatically loads the anonymous selected feed, refreshes visible
metadata and clears content on background/disconnect/denial. The current APK has
no configured origin and stops at setup. No real LAN end-to-end result, real-photo
selection or physical installation is claimed. The grid cache is limited to
16 MiB per page; overflow tiles are placeholders. Cross-page slideshow, albums,
search, video, screensaver and offline storage remain outside this slice.

The next backend step is the separately authorized synthetic LAN deployment
sequence above, including normal DNS, trusted HTTPS and network isolation.
Android then owns a private configured APK and JMGO launcher/remote, cold-start,
sleep/wake, reconnect, disable/removal and visible-quality acceptance. Local adapter
implementation no longer blocks that sequence; all operational gates remain open.
