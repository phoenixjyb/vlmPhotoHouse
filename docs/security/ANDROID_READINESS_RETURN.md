# Return to Android — backend readiness, 2026-09-11

**Android repin complete locally. Database-preparation/source-package slice verified locally.
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
  **`8d5e9cce77aaeb079d1dfb5801a932c2a01194d1`**, branch
  `codex/backend-android-readiness`. It adds explicit initialization, backup and in-memory migration
  rehearsal to the offline operator/source package; it changes no frozen API source, wire contract or migration. The mobile
  pin remains `87a60b4`. No immediate mobile change is requested by this tooling slice;
  final deployment source identity still needs coordinated review.
- Fresh backend verification: **240 security tests pass**, including 14 database-preparation,
  12 operator and three package tests; route completeness remains **152 entries**. The extracted
  45-file package passed three database-preparation commands, seven in-process ASGI
  checks and three operator commands, including review of the generated backup. No listeners or live data were used.
- Source ZIP SHA-256:
  `ea682cdac754ec510dab7846f6d2b6674fd1e88b3878d99fcb617386bd8ce8f5`.
  It contains source and a manifest only; no dependencies, database, media, private
  configuration or certificates. It is not installed or deployed.
- The [operator tool](OPERATOR_TOOL.md) separates planning, validation, backup review,
  application and receipt lookup. It requires exact plan and cross-command review
  digests, uses protected password prompts and preserves the existing atomic service
  checks. Review references remain audit labels, not operator authentication.
- The [launcher](STAGING_LAUNCHER.md) remains tested through config validation and
  mocked serving only. Default `app.main:app` remains closed. Required schema stays
  `b6e3f9a5c721`; actual target schema/owner/library/mappings/recovery state are unknown.

Read [the current database-preparation evidence](evidence/android-readiness/database-preparation-validation.json)
and [staging decision](ANDROID_STAGING_DECISION.json). Earlier caption and launcher
evidence remains historical, including the pre-repin probe's old consumer pin.

**New local capability:** [database preparation](DATABASE_PREPARATION.md) creates a new
empty migrated database, makes a separate private backup and rehearses migration only
in memory. It refuses existing outputs, unknown revisions and WAL/sidecar databases;
its current size limit is 64 MiB. Existing-database migration and restore are not implemented.

**Next local backend work:** reviewed CPU environment lock and existing-database
migration apply/recovery procedure. No Android repin is requested: all ten pinned
backend source hashes remain unchanged. Continue Android work within the current
synthetic scope; keep real credentials and phone connectivity gated.

**Coordination:** the user requested a handoff to Android thread
`01a08537-1f09-7bb3-9b0c-5781f1cabd60`. This document was queued to open there through
the app file-panel tool. That is not a sent message, session wake-up or acknowledged receipt.

**Still unset/unverified:** host/service identity, deployment/release approval,
HTTPS origin/certificate/private-network behavior, approved synthetic audience,
real backup/restore and provisioning, legacy/standalone ingress isolation and
physical-phone acceptance. No Windows/Mac mini access, real DB/media/credentials,
service operation, push or merge was performed or authorized by this return.

Preserve existing worktrees. Once target/origin/audience and scoped authority are
established, the Android owner privately configures and rebuilds the connected APK,
records its new identity and performs separately authorized phone acceptance.
Publication/merge status was not rechecked; earlier publication is not merge authority.
