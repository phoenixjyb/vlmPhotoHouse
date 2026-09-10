# Return to Android — backend readiness, 2026-09-11

**Android repin complete locally. Operator/source-package slice verified locally.
Real-phone credentials and deployment remain NO-GO until external gates are met.**

- Android repin branch: `codex/android-backend-repin`, observed clean at
  `1d4fc49c043d553df510c52b9a368ee0313398c6`. Its return reports the coordinated pin
  to **`87a60b475b37b1d6873cd977bcb6e7254472da7e`**, 38 unchanged ASGI cases, 211
  backend tests and 14 Kotlin boundary checks. This session read that return and
  structured evidence; it did not rerun those historical integration checks.
- Fresh mobile checks: the 12-operation/38-case/eight-file frozen contract validates,
  all eight verifier regression tests pass, and all ten pinned backend source hashes
  match this backend checkout. No mobile edits, APK build/install or TLS test occurred.
- Latest backend implementation/source package:
  **`18adeb6116280703f27613c8e1f0de1ed72f7345`**, branch
  `codex/backend-android-readiness`. It adds offline operator commands and a source
  package; it changes no frozen API source, wire contract or migration. The mobile
  pin remains `87a60b4`. No immediate mobile change is requested by this tooling slice;
  final deployment source identity still needs coordinated review.
- Fresh backend verification: **226 security tests pass**, including 12 operator
  and three package tests; route completeness remains **152 entries**. The extracted
  43-file package passed a fresh-process synthetic migration, seven in-process ASGI
  checks and two operator commands. No listeners or live data were used.
- Source ZIP SHA-256:
  `9741d521cbda424656d95ff4b1ab771b36361a914518d0941beb74ab4160995c`.
  It contains source and a manifest only; no dependencies, database, media, private
  configuration or certificates. It is not installed or deployed.
- The [operator tool](OPERATOR_TOOL.md) separates planning, validation, backup review,
  application and receipt lookup. It requires exact plan and cross-command review
  digests, uses protected password prompts and preserves the existing atomic service
  checks. Review references remain audit labels, not operator authentication.
- The [launcher](STAGING_LAUNCHER.md) remains tested through config validation and
  mocked serving only. Default `app.main:app` remains closed. Required schema stays
  `b6e3f9a5c721`; actual target schema/owner/library/mappings/recovery state are unknown.

Read [the current operator/package evidence](evidence/android-readiness/operator-package-validation.json)
and [staging decision](ANDROID_STAGING_DECISION.json). Earlier caption and launcher
evidence remains historical, including the pre-repin probe's old consumer pin.

**Next local backend work:** explicit synthetic initialization/migration/backup
rehearsal command and CPU environment lock. The operator command assumes an already
migrated database and separately prepared matching backup; it creates neither.

**Still unset/unverified:** host/service identity, deployment/release approval,
HTTPS origin/certificate/private-network behavior, approved synthetic audience,
real backup/restore and provisioning, legacy/standalone ingress isolation and
physical-phone acceptance. No Windows/Mac mini access, real DB/media/credentials,
service operation, push or merge was performed or authorized by this return.

Preserve existing worktrees. Once target/origin/audience and scoped authority are
established, the Android owner privately configures and rebuilds the connected APK,
records its new identity and performs separately authorized phone acceptance.
Publication/merge status was not rechecked; earlier publication is not merge authority.
