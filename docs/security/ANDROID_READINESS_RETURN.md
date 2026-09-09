# Return to Android — PH-BACKEND-ANDROID-READINESS-01

**Status: review/proposal complete; NO-GO for real-phone credentials.**

- Deployed: **unknown**, no live host checked; this session performed no deployment.
- Candidate backend: **`87a60b475b37b1d6873cd977bcb6e7254472da7e`**, including
  caption fix `0cf5058` and the explicit staging launcher.
  Android's frozen consumer still pins `1e394f789ff1f7cef6d9930bb541186684f5a9a0`.
  Actual deployed/approved release: **unknown/unset**.
- HTTPS origin/certificate/network: **not established**. Do not configure a private
  origin or enable real credentials from this report. Private configuration remains
  with the operator/Android owner after target approval.
- Migration: runtime requires `b6e3f9a5c721`; actual target unverified.
  Owner/library/mappings, backups and restored-access state: unverified.
- Audience: propose synthetic owner/viewer and generated media for first isolated
  staging; no real owner, phone login, invitation or library has been selected.
- Local evidence: **211 backend security tests pass**, including 10 launcher tests.
  **14 actual Kotlin adapter cases pass** for caption fix `0cf5058`; its application
  and frozen fixture source hashes are unchanged by the launcher commit. No sockets
  were opened. The former 657749-byte
  caption case is now 493328 bytes with 15 whole rows and `has_more=true`.
  Exact-limit responses pass and oversized responses remain rejected. Eight
  unchanged backend source hashes/eight contract hashes match; two reviewed
  backend hashes changed. The earlier 38-case pinned replay remains baseline
  evidence; Android repinning and replay against the new candidate remain pending.
  Earlier TLS/emulator/CI reports are not new runs or remote-status verification.
- **Compatibility fix delivered locally; consumer update pending.** Read
  [the caption-budget handoff](CAPTION_RESPONSE_BUDGET.md) for semantics, exact
  commit, evidence and reproduction. Keep the client limit and explicitly repin
  reviewed backend source/contract checksums before consuming this fix.
- **Launcher delivered locally:** [explicit staging launcher](STAGING_LAUNCHER.md)
  validates only the selected config in `--check-config` mode. `--serve` remains a
  separate operation; only its mocked invocation was tested. No certificate, DB,
  listener or host acceptance is implied by configuration validation.
- Authorized next work here: local provisioning/operator-package and runtime-lock review
  and synthetic no-listener tests. No new host/deployment/account/phone/push/merge
  authority is granted by this return.

Read [the staging proposal](ANDROID_STAGING_PROPOSAL.md),
[decision record](ANDROID_STAGING_DECISION.json) and
[probe evidence](evidence/android-readiness/source-asgi-probe.json).
The [latest local validation and changed-file manifest](evidence/android-readiness/local-validation.json)
separates the new checks from retained historical evidence.
The proposal contains target/configuration choices, backup/migration/provisioning,
rollback, phone acceptance and explicit unset operator inputs. Its target is a
proposal, not confirmation that a host, certificate or unused port is available.

Preserve all existing mobile and backend worktrees. Do not change the frozen
consumer files or launch the loopback TLS suite as part of this no-listener task.
When a release/origin/audience and authority are established, the Android owner
configures only ignored local properties, rebuilds privately and records a new
APK/installed-build identity before phone acceptance. Public PR/check/merge status
requires a separately current review; earlier publication is not merge authority.
