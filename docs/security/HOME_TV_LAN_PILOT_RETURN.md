# PH-BACKEND-HOME-TV-LAN-PILOT-01 — preflight blocked

The user authorized the separate synthetic home-LAN deployment after Android's
local review. That authority is recorded in the deployment plan. This preflight
does not yet provide a served origin or a configured-projector acceptance input.

## Identity and verification

Branch `codex/backend-home-tv-feed`, worktree `_worktrees/backend-home-tv-feed`.
Observed clean base: `7c3cbc7dace8b032a4c58bb01a27ec9a7139e8fb`.
Runtime pin: `e6b2827842b2c0b5223c85208299b60e8a1257f6`.
Contract SHA-256:
`70328a653ddaa559bad6a4d654cf9870c89c5217e8e9e6c46a3501e9dd9e7548`.

Fresh verification passed the ZIP checksum and size (596,784 bytes), exact eleven
archive members, all ten payload hashes and seven source Git-blob hashes. ZIP
SHA-256: `934339ab96ed42a6301ad45acf6aa51bb917b9b6947e03c0d3ccecd72fbe0b79`.
Only synthetic asset 101, revision 1, and the pinned grid/4K display fixtures are
selected; originals remain off. No runtime test, build or emulator check was rerun.

## Observed blockers

1. **Windows SSH authentication.** The saved direct profile and a second attempt
   using the prior Windows deployment username reached SSH but rejected the saved
   key. The earlier deployment used a different Windows key through a Mac mini
   relay. The user has been asked for that specific exception to the original
   no-Mac-mini restriction. No relay was accessed and no credentials were changed.
   A working authorized route is required before refreshing actual Windows identity,
   listeners, processes, task state, certificate ACLs or the offline wheel cache.
2. **Normal local DNS.** The current Mac on the home LAN resolves the candidate
   hostname to a public address. This does not establish the required private route
   for the projector. Router/local DNS capabilities and projector settings remain
   unverified. Public forwarding and TLS bypass are excluded; a forced address
   mapping alone will not count as normal-client acceptance.

No Windows writes, new listener, router/DNS/firewall change, model load, real-media
access, caption/protected-service action, device install, push or merge occurred.
Existing service health was not established because authenticated inspection failed.

## Resume and Android return

The [preflight receipt](evidence/home-tv-feed-readiness/lan-pilot-preflight.json)
separates successful local package verification from missing operational evidence.
Private handoff reference: `HOME-FEED-E6B2827-LAN-PILOT`. The Android owner receives
its exact local path separately; it includes no usable served-origin claim.

After the pending SSH route is resolved, refresh host/port/process identity, verify
native certificate and locked CPU inputs, and stage a fresh independent synthetic
publication. Establish normal local DNS, trusted HTTPS and actual LAN/guest/outside
isolation before marking the feed ready. Source-IP admission cannot identify an
outside client hidden by a permitted proxy or SNAT address. Complete feed/display/
HEAD and denial checks, then scoped disable/remove/restart/rollback. Android owns
the later configured APK and real JMGO acceptance; no mobile checkout was changed.
