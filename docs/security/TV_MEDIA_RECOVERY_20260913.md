# TV service-account cache repair and memory pressure

13 September 2026. Backend source remains
`5269257b4b2a791b59f9181aa83d8e70a5d03b4d`; this is a runtime correction and
qualification addendum to [the v11 rollout](ON_DEMAND_WINDOWS_RETURN.md).

## Findings and repair

The reported photo assets 28206 and 28205 returned valid grid/display responses
under administrative ASGI qualification, but returned 503 `media_unavailable`
under the actual service's Limited interactive account. The administrative cache
creation left a protected OWNER RIGHTS ACL owned by Administrators. The Limited
service token could not use that cache. Earlier administrator qualification did
not establish service-account cache readiness; that limitation was missed.

Saved the prior ACLs privately, then applied explicit service-user, SYSTEM and
Administrators rights only to the owned cache and diagnostic cache (16 entries).
No original-media, database, share or publication ACL was changed. Cached reads
then passed under the Limited principal without a service restart.

A separate fresh cache still returned 503 `resource_pressure`. Available RAM was
near the existing 4 GiB admission floor. WindowsTerminal.exe held 50,460,925,952
bytes of working set and 74,364,276,736 bytes of private committed memory, while
its PowerShell child used 78,651,392 bytes. Three samples over ten seconds were
stable. This identifies the process retaining memory, not the exact allocation
bug. It is not evidence of a PhotoHouse Python memory leak.

The user explicitly approved closing that terminal and its interactive shell.
The process tree was revalidated and the API/caption/v1/v2/v3 listeners were
verified outside it before termination. Available RAM subsequently recovered to
54,737,047,552 bytes. All five listener PIDs remained unchanged. A separate smaller
terminal remained running and was left alone. No service or caption restart.

## Qualification after repair

Under the same non-admin Limited account, with the resource guard enabled:

| Asset | Grid | Display | Video |
| --- | --- | --- | --- |
| 28206 | 200, 26,294 bytes | 200, 489,907 bytes | n/a |
| 28205 | 200, 24,428 bytes | 200, 431,905 bytes | n/a |
| 28204 | 200, 22,120 bytes | 200, 359,286 bytes | n/a |
| 28157 | 200, 26,981 bytes | 200, 167,608 bytes | 206, 262,144-byte prefix |

The first two photos passed using the previously failing fresh diagnostic cache
after RAM recovery. A subsequent run passed all rows using the actual service
cache, including the additional photo 28204. No guard refusal was recorded in
these final runs. These are Windows ASGI requests with a synthetic allowed peer,
not physical projector network/decoder acceptance. No family-media bytes were
copied to the Mac or committed.

## Prevent recurrence

Run cold-cache qualification using the exact service principal and privilege
level. If an operator pre-creates or warms a private cache as Administrator,
explicitly grant the intended service SID access and verify both a cache miss and
a cache hit under that service account before calling the rollout ready. Preserve
restricted ACLs; do not elevate the service or loosen original/media access.

Keep the 4 GiB RAM floor, single decoder and other resource budgets unchanged.
Keep long-running service output in bounded files using the existing pythonw
launcher. Avoid sustained verbose output in an interactive terminal; the terminal
incident requires its own reproduction or allocation evidence for root cause.
Microsoft's [issue 20342](https://github.com/microsoft/terminal/issues/20342)
describes memory retention when scrolled up during continued output; this is a
candidate explanation, not a confirmed match for installed version 1.24.2607.10001.
Closing the terminal is recovery, not a permanent leak fix. No terminal settings
or installed package were changed.

## Android delivery and remaining gates

TV v12 preserves the selected asset on recoverable media errors, exposes diagnostic
codes and supports thumbnail retries. Its APK uses the existing home configuration
and signing key. Signature, metadata and SMB operator read-back hash were checked;
the dedicated reader ACL remains read-only and prior APKs remain available.
Physical v12 installation and JMGO playback of 28157 still require user testing.

The temporary, manually triggered Limited diagnostic task was used for bounded
qualification only and is removed after completion. Private receipts, previous
ACLs and the installer are retained in the owner's local v12 handoff.

No backend source change, contract repin, bulk transcode, public ingress, protected
phone activation, push or merge. Full-library decoding/video preparation and
physical target acceptance are still separate readiness gates.
