# PH-BACKEND-HOME-TV-LAN-PILOT-01 — Windows staged, TV routing pending

The independent Windows synthetic feed has been staged and exercised over real
home-LAN HTTPS. **It is currently stopped, with its temporary firewall rules removed.**
Normal projector DNS and physical TV acceptance remain unresolved. No real family
photos are selected, and this is not a completed LAN-wide deployment.

## Exact artifact and runtime

Branch `codex/backend-home-tv-feed`, worktree `_worktrees/backend-home-tv-feed`.
Observed clean follow-up base: `ea8dc42884181791596f62c4af62e6d33b7ced72`.
Runtime pin remains `e6b2827842b2c0b5223c85208299b60e8a1257f6`.
Contract SHA-256:
`70328a653ddaa559bad6a4d654cf9870c89c5217e8e9e6c46a3501e9dd9e7548`.
ZIP: 596,784 bytes, SHA-256
`934339ab96ed42a6301ad45acf6aa51bb917b9b6947e03c0d3ccecd72fbe0b79`.

Direct Windows SSH now works after the user installed the Mac public key. The saved
home profile's username was corrected and verified; its previous configuration was
backed up privately. No Mac mini relay was used. A fresh private Windows root holds
the exact release, separate CPU environment, synthetic publications and pilot logs.
All ten payload hashes matched on Windows before execution and after the tests.

All 18 runtime packages installed offline with the pinned hash lock; `pip check`
and the Windows runtime probe passed. Runtime is Python 3.12.10 / OpenSSL 3.0.16.
This verifies installation against the lock and environment metadata, not a complete
installed-file integrity attestation. Native configuration, certificate/key matching,
Windows certificate chain construction and both synthetic JPEG hashes/dimensions
passed. The private key remained on Windows and was not copied.

## Fresh network and lifecycle evidence

| Check | Passed |
| --- | ---: |
| Mac home-LAN HTTPS feed, exact grid/4K bytes, HEAD and route/header/Range denials | 23 |
| Disabled feed, removed selection, stale/current preview revisions and restore | 7 |
| Fresh publication switch, new service PID, old-publication rollback and revision conflicts | 6 |
| Actual Windows peer outside the allowed operator address denied over trusted HTTPS | 1 |
| Total real HTTPS checks | 37 |

Both client paths used normal certificate validation. Mac requests used an explicit
hostname-to-private-address override for diagnostics. **That is not normal DNS or
projector acceptance.** No guest-network or WAN request was performed. Earlier
backend security suites, Android JVM/build/emulator checks were not rerun here.

During the diagnostic, the app admitted only the Mac operator's single address.
Temporary Windows ingress rules allowed that address and blocked its IPv4 complement
on the selected wired address and TV port. This bounded diagnostic does not alter the
chosen product policy: selected home-LAN sharing without sign-in or device approval.
Broader LAN admission and proxy/SNAT isolation still require actual network evidence.

The task `PhotoHouse-HomeFeed-Synthetic` is manual-start, interactive user, Limited,
with a 30-minute execution limit and zero triggers verified independently in exported
XML. The scoped stop/config-switch/restart sequence changed only its process. The
final task is Ready/stopped, no feed listener remains, and both temporary rules are
gone. Publication directory `publication-r1` now holds synthetic asset 101 at revision
4; the alternate revision-5 publication and previous configs are preserved. Grid
and 3840x2160 display bytes still match the frozen fixtures; originals remain off.

Caption/API process IDs, start times and executable paths matched the initial
snapshot. The older protected staging task was already stopped and remains stopped.
No real database/media, caption pause, model load, existing service restart, public
forwarding, global firewall relaxation, credential rotation, push or merge occurred.
Process preservation does not establish caption queue health or GPU progress.

## Corrected pilot helper failures

The first long encoded PowerShell command exceeded Windows' command-line limit;
stdin script transport resolved it before staging. The selection helper initially
used Windows' default GBK decoding for a UTF-8 fixture and failed before mutation;
explicit UTF-8 fixed it and the full lifecycle checks passed. Early denied-peer
probes assumed an incorrect response tier; direct capture verified HTTP 403 and TLS
verification zero. A PowerShell null collection also reported one trigger; the
corrected count and independently parsed task XML both show zero. Original failure
receipts remain private. These were pilot-helper corrections; the frozen feed source
was unchanged.

## Remaining action and Android handoff

The [Windows receipt](evidence/home-tv-feed-readiness/windows-lan-pilot.json) binds
source/package/runtime identities, checks, helper hashes and final state. The older
[preflight receipt](evidence/home-tv-feed-readiness/lan-pilot-preflight.json) remains
historical; its SSH blocker is resolved. Exact host/origin/key references are retained
only in private handoff `HOME-FEED-E6B2827-LAN-PILOT`.

Normal home-LAN DNS still resolves the candidate hostname publicly. The user has
been asked for the JMGO IP and whether manual IP/DNS settings are available. Existing
Windows SharedAccess occupies UDP 53 and its DNS probe did not answer the Mac; it
was not modified. Do not assume a usable local resolver or router DNS override.

Next establish the projector's normal local hostname route, trusted HTTPS and actual
LAN/guest/outside isolation. The backend owner then restores reviewed scoped rules
and client admission before resuming the service. Starting the retained task alone
is not the next step. Android owns the private configured APK and real JMGO remote,
image quality, slideshow, sleep/wake, reconnect and disable/removal acceptance. A
candidate configured build can be prepared with networking explicitly pending; no
TLS bypass or forced diagnostic mapping counts as completed device access.

## Configured TV APK received

Android evidence commit `887db83eb96db136d85589276bc9c6e93081bb54` returns the
private configured build from unchanged source
`e8ab9be3c5497778783edf1b4a009707922248d1`. Backend review independently verified
APK SHA-256 `15680809a11ab00639046bf2cca30953d66fea4b84061bd4437c1edfdbcca795`,
size 8,834,278 bytes, package `dev.photohouse.tv`, version code 2 /
`0.2-home-feed-dev`, and debug signer SHA-256
`56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28`.
No main APK assets exist; the private origin handoff hash matches and that origin
string is present in the APK DEX. Exact private artifact reference:
`HOME-TV-E8AB9BE-CONFIGURED-NETWORK-PENDING`.

Android reports a successful offline build/lint with zero errors and the same three
warnings. Backend did not rerun builds or test suites for this artifact review.
Android found no ADB-connected device. The configured artifact is available, but
normal DNS, service resume and physical installation/acceptance remain pending.
No backend runtime or mobile source change accompanied this receipt.
