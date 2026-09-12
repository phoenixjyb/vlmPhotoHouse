# Windows synthetic protected backend — verified 2026-09-11

The protected backend is now running as a separate synthetic Windows staging task.
The existing caption/API release continues unchanged. No real database migration,
real-library cutover, caption pause, router change, firewall change or phone install
was performed. Aggregate queue metrics were read through the existing API; no real
media or real SQLite file was opened by the deployment tools.

## Immutable artifact and environment

- Deployed source: `f15e50753a09b46c8b8748ec87a26f15853bcf0c` on
  `codex/backend-android-readiness`.
- Source ZIP: 54 allowlisted files, 369,881 bytes, SHA-256
  `7ec6b6a2a32869b4e47eee0bbc809ef53e6b521c5622c13062a3d4d82772d4e5`.
  All manifest members verified before execution and again after serving.
- Runtime lock SHA-256:
  `b4e4e92f67dd3740986494ff3c8cc4b10557fd41329efee030dda03e05897a42`.
  All 18 Windows CPU wheels installed offline with `--require-hashes` into a new
  private environment. `pip check` and the exact Windows runtime probe passed.
- Native Windows x64 Python 3.12.10, OpenSSL 3.0.16, SQLite 3.49.1. The runtime
  probe covers versions, scrypt and SQLite/TLS capabilities; it is not a fresh
  vulnerability scan or a full installed-file integrity attestation.
- New synthetic database at schema `b6e3f9a5c721`: two finite generated images,
  bilingual synthetic captions, cached thumbnails and one selected owner/library.
  Viewer admission used actual owner-issued phone-bound invitations over HTTPS.
  No original grants were enabled. No existing account was recovered or reopened.
- Preview fixture SHA-256:
  `c311363ddcc33e304b4f657d7fb3353c839bcdbdb9bdbd09bea62b1152fac42d`.
  This is the existing generated 8x8 JPEG, not family media or a loaded model.

## Served checks and isolation

At 05:34 UTC, **26 real HTTPS checks passed**: system trust/hostname, protected UI,
anonymous session/gallery denial, six closed legacy/operational paths, owner login,
invitation creation, wrong-phone refusal, invited registration, scoped session/
gallery/detail/caption/thumbnail and thumbnail HEAD, original Range denial,
cross-library/unmapped-object denial, logout and rejection of the revoked session.
A fresh separate pilot invitation was issued and retained encrypted on Windows.

The listener binds one explicitly selected wired private address on port 8443.
The limited, interactive-user scheduled task is manual-start only, with no boot or
login trigger. It runs only the new isolated source and CPU environment. Its private
root and certificate/key ACLs permit only the selected user, SYSTEM and local
administrators. Credentials are protected with user-scoped Windows DPAPI and never
placed in command arguments, server logs, public documentation or the source ZIP.

At 05:35 UTC, **rollback/restart passed**: stop only the new staging task, observe
its listener disappear, preserve the existing caption/API process identities,
restart to a new staging PID, and pass **seven more HTTPS read/login/logout checks**.
The fresh process read the same on-disk certificate. This exercises a scoped reload
mechanism; it does not prove a future renewed certificate is automatically adopted.

A second home-LAN machine reached the UI with HTTP 200 and normal certificate
verification (`ssl_verify_result=0`), using an explicit hostname-to-private-address
mapping. This proves that LAN route, not normal public DNS/NAT or Android trust.
The earlier bulk stdin transfer stalled before creating a staging directory; it was
terminated and replaced with verified file transfer. No partial runtime was activated.

## Source checks and review state

- 277 synthetic security tests pass (34.102 seconds).
- Five native PowerShell retirement checks and the shell refusal check pass.
- Three package tests and extracted-package smoke pass: seven ASGI checks,
  nine operator commands and eight database-preparation invocations.
- The 26 acceptance cases were rehearsed with local synthetic ASGI before the
  distinct live TLS run; that rehearsal does not count as network evidence.
- Inventory remains 152 entries: 23 active, 97 retired, 32 standalone. Historical
  unsafe handlers retain their 84/84 failed denial ledger. Inventory is not security;
  separate legacy/standalone ingress still requires review before real cutover.

GitHub master advanced to `b886aca9344c8f9e838f28e2a1b380caad0ec40e`.
Its nine new caption/viewer commits must be preserved. The local dry merge was
textually clean, but no actual merge or push was performed. The
[review draft](BACKEND_REVIEW_DRAFT.md) covers the full foundation and launcher
compatibility change; it is not an approved PR or remote CI result.

## Android handoff and remaining gates

The private operator handoff identifies the served origin, release location, task,
credential references, pilot invitation lifetime and exact rollback. It contains no
plaintext password, token, code or certificate key. Android can prepare a private
configured debug APK against that selected origin while retaining its frozen API
pin `87a60b475b37b1d6873cd977bcb6e7254472da7e` and original-access-off policy.
No Android repository file was modified by this backend task.

Remaining: normal client hostname routing and any reviewed public-router ingress;
selected physical phone/operator and installed APK acceptance; managed startup,
renewed-certificate reload/renewal observation; integration of latest master and
reviewed publication/merge; and, separately, safe caption drain/backup, real database
size/migration rehearsal, writer compatibility, owner recovery and real-library
cutover. Keep the current caption release running until that cutover is ready.
