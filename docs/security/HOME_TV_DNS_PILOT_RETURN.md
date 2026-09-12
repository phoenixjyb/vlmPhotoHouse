# Home TV DNS pilot — resolver and synthetic feed running

Both independent Windows tasks are running for the projector/operator pilot.
The user subsequently requested connection settings embedded in the APK; Android
is implementing an app-scoped address mapping with hostname/TLS validation. That
route does not require a manual TV DNS change and must not be called normal system
DNS acceptance. The prior Save state is unknown, so the existing DNS service is
retained to avoid disruption. No further DNS changes are planned for the new build.
Exact values and the screenshot remain private in `HOME-FEED-E6B2827-LAN-PILOT`.

## What changed

A separate CoreDNS 1.14.7 instance binds only the selected wired address, UDP and
TCP port 53. Its published Windows archive checksum and extracted binary checksum
were verified locally and again on Windows. It maps the single PhotoHouse hostname
to the local feed, returns an empty AAAA answer, and forwards other requests to the
projector's existing resolver. No router, DHCP, global DNS or public forwarding
setting changed. The feed source/contract and synthetic revision 4 remain unchanged.

[CoreDNS bind](https://coredns.io/plugins/bind/),
[hosts](https://coredns.io/plugins/hosts/) and
[ACL](https://coredns.io/plugins/acl/) configuration implement the explicit address,
local mapping and actual-source admission. ACLs apply to both local and forwarding
zones; Windows rules additionally allow the two pilot addresses and block their
IPv4 complement. DNS firewall rules are limited to the exact new binary. These
restrictions bound the pilot and do not introduce personal sign-in/device approval.

The feed's retained client admission and two scoped ingress rules now include the
projector address observed in the photo and the operator Mac. Four new DNS rules
cover UDP/TCP allow/block. The DNS child has below-normal process priority, two Go
execution threads and a 128-MiB soft memory limit configured by its private wrapper.
No query logging is enabled.

## Verification and current state

- Eleven DNS cases passed before and after a scoped restart: UDP/TCP local A,
  empty AAAA, normal upstream forwarding and repeated queries alongside SharedAccess.
- Four disallowed Windows-peer DNS queries returned REFUSED with no answers,
  covering both transports and local/forwarded zones.
- Seven HTTPS checks used the actual DNS response for the connection while keeping
  hostname certificate validation. Feed, grid/4K bytes, HEAD and route denials
  passed without `--resolve`, an injected connection address or a TLS bypass.
- A fresh disallowed Windows HTTPS peer received 403 with certificate verification
  zero. This supplements the earlier 37 diagnostic HTTPS checks; prior backend and
  Android test suites were not rerun.
- Both tasks are Running, Limited/Interactive, with zero triggers and `PT0S`
  execution limits. **There is no 30-minute shutdown deadline.** They are manual
  pilot tasks and do not automatically start after reboot/logon.

These are configured-test-client DNS/TLS results, not a claim that the projector's
OS resolver or installed app has passed. ADB availability is not a server/DNS gate;
Android may use the already authorized manual sideload workflow.

SharedAccess remains running with its original PID and wildcard UDP endpoint;
CoreDNS concurrently owns the specific wired endpoint. Caption/API process IDs,
start times and executable paths are unchanged. The protected task remains stopped
as originally found. No real database/media/model access, credential rotation,
caption/protected restart, mobile edit, push or merge occurred.

## Lifecycle, corrections and next action

DNS stop/restart released its specific UDP/TCP endpoints and produced a new PID
without changing SharedAccess. Raw task stop left the native DNS child behind;
the verified scoped procedure also terminates only a process matching the exact
private CoreDNS executable. The staged private `stop-dns.ps1` captures that cleanup
and removes only DNS pilot rules. Restore the projector's previous DNS before
ending the resolver pilot. Keep Windows/the user session available during testing.

The package reports bare plugin names; the initial inventory guard expected a
prefix and was corrected before serving. The first start caller timed out despite
successful DNS responses. The wrapper now redirects its own streams and supplies
closed child stdin; independent inspection and the subsequent scoped restart
completed successfully. Original failure evidence is retained privately.

The [receipt](evidence/home-tv-feed-readiness/dns-ready-pilot.json) binds the binary,
configuration, tests, screenshot hash and observed running state. Android's configured
APK remains SHA-256
`15680809a11ab00639046bf2cca30953d66fea4b84061bd4437c1edfdbcca795`.
Next Android verifies the newly requested app-scoped mapping and returns its new
source/APK/TLS evidence, then verifies physical install/launch, connection, remote
controls, images, slideshow and lifecycle. The configured APK hash above predates
that mapping change. Confirm the saved projector DNS state before retiring the
existing resolver; no user-visible network change is inferred from the screenshot.
Actual guest/WAN/SNAT probes, broader admission and durable startup/renewal remain
separate from this two-client synthetic pilot.

## Mapped v3 APK received and reviewed

Android source `c42918a54991895a3869977f92aa29ffee2377e5`, evidence commit
`2b2ebf88dc9699860438438d43344eb48aefdfcf`, now implements the requested exact-host
private address mapping. The backend's bounded source review found no blocker:
canonical RFC1918 parsing uses numeric bytes, unexpected hosts fail, proxy routing
is disabled for mapped mode, default hostname/certificate validation remains, and
invalid configuration stops at setup. The frozen backend/phone contracts remain.

Backend review independently verified all eleven source-delta files against Git,
both configuration strings in DEX against the private handoff, no main APK assets,
APK checksum/size, package/version and unchanged signer. The private v3 APK is
8,802,427 bytes, SHA-256
`710c9d3aecd17dcc4b05f00e578504c0522cb1026652520242fe782b8b244b13`,
package `dev.photohouse.tv`, version code 3 / `0.3-home-lan-dev`.
It supersedes the v2 candidate above. Private reference: `HOME-TV-V3-LAN-MAPPED`.

Android retains 29 passing home JVM tests and one opt-in live adapter test making
four real HTTPS requests against the running synthetic feed using normal JVM trust.
Those results were reviewed, not rerun here, and are not physical APK/projector
acceptance. A [review receipt](evidence/home-tv-feed-readiness/android-v3-review.json)
binds the source/artifact checks. Next install v3 and verify the actual JMGO; no
manual projector DNS change or further server resume is required for this build.
The existing resolver remains untouched because prior user Save state is unknown.
