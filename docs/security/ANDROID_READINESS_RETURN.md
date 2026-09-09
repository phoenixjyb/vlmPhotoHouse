# Return to Android — PH-BACKEND-ANDROID-READINESS-01

**Status: review/proposal complete; NO-GO for real-phone credentials.**

- Deployed: **unknown**, no live host checked; this session performed no deployment.
- Candidate backend: `1e394f789ff1f7cef6d9930bb541186684f5a9a0`.
  Actual deployed/approved release: **unknown/unset**.
- HTTPS origin/certificate/network: **not established**. Do not configure a private
  origin or enable real credentials from this report. Private configuration remains
  with the operator/Android owner after target approval.
- Migration: runtime requires `b6e3f9a5c721`; actual target unverified.
  Owner/library/mappings, backups and restored-access state: unverified.
- Audience: propose synthetic owner/viewer and generated media for first isolated
  staging; no real owner, phone login, invitation or library has been selected.
- Local evidence: ten backend/eight contract checksums and 38 ASGI response cases
  pass; connected APK hash matches the handoff. Earlier JVM/TLS/emulator/CI reports
  are retained evidence, not new runs or current remote-status verification.
- **New compatibility blocker:** valid backend captions can be **657749 bytes**;
  Android JSON limit is **524288 bytes**. Probe exits 1 and records the finding.
  Keep the client limit; coordinate a bounded server response-budget fix/regression
  and repin any changed backend source before claiming unrestricted compatibility.
- Authorized next work here: local caption-budget/launcher/operator-package review
  and synthetic no-listener tests. No new host/deployment/account/phone/push/merge
  authority is granted by this return.

Read [the staging proposal](ANDROID_STAGING_PROPOSAL.md),
[decision record](ANDROID_STAGING_DECISION.json) and
[probe evidence](evidence/android-readiness/source-asgi-probe.json).
The proposal contains target/configuration choices, backup/migration/provisioning,
rollback, phone acceptance and explicit unset operator inputs. Its target is a
proposal, not confirmation that a host, certificate or unused port is available.

Preserve all existing mobile and backend worktrees. Do not change the frozen
consumer files or launch the loopback TLS suite as part of this no-listener task.
When a release/origin/audience and authority are established, the Android owner
configures only ignored local properties, rebuilds privately and records a new
APK/installed-build identity before phone acceptance. Public PR/check/merge status
requires a separately current review; earlier publication is not merge authority.
