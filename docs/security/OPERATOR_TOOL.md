# Offline provisioning tool and source package

2026-09-11. Local implementation following the Android repin to `87a60b4`.
The operator command is `scripts/provision_access.py`. It wraps the existing
reviewed services; it changes no HTTP API, migration, account policy or Android
contract. All executed database operations use disposable synthetic fixtures.

## Authority and effects

This is a tool for an independently authorized local database administrator.
Plan seals, digests, CLI flags and audit references are not authentication or
approval. The operator must first confirm the exact host, existing database,
separate matching backup, restore procedure, selected audience and stopped
application/worker processes. The tool neither stops processes nor verifies
operational quiescence. Do not use it against a live/real database under the current
local-only task authorization.

- `plan-owner` reads a private request containing exactly `phone_login` and
  `library_id`. Its sealed plan proposes a **new owner and system operator**, new
  library and approved owner membership. Application creates no session, original
  grant or automatic asset mapping. It refuses existing owner/library targets.
- `plan-assets` reads exactly `library_id`, `operator_account_id` and integer
  `asset_ids`. Only the exact selected active unmapped IDs are eligible. Existing
  current readers, including already approved original readers, gain visibility
  under their existing permissions when the mapping is applied. No new original
  permission or audience membership is created.
- `validate` checks a saved plan read-only. `review` checks a separate matching
  backup, rehearses SQLite restoration in memory and returns `applied=false`.
- `apply` is a separate command. It reconstructs a fresh in-process review and
  requires the exact review digest from the earlier review before calling the
  existing atomic apply service. No serialized `ApplyReview` is accepted.
- `receipt` reads a committed receipt by exact plan UUID and plan digest. It is
  useful after lost output or interruption; never infer that a retry is safe from
  a missing terminal success message.

The phone is an unverified login label, not proof of telephone ownership. Normal
family members still use owner-issued phone-bound invitations through the protected
app. This administrative owner workflow is not public registration.

## Private artifact workflow

Use the existing repo-root test/runtime interpreter. Every path is explicit,
absolute and native to the machine; there are no `.env`, database, country-code,
backup or credential defaults. Select private files outside Git and the media roots.
Do not put phones/passwords/invitations in command arguments or public artifacts.
Review request/plan contents privately before proceeding.

```sh
"$PHOTOHOUSE_PYTHON" scripts/provision_access.py plan-owner \
  --database "$PHOTOHOUSE_DATABASE" --request "$PHOTOHOUSE_REQUEST" --out "$PHOTOHOUSE_PLAN"
"$PHOTOHOUSE_PYTHON" scripts/provision_access.py validate \
  --database "$PHOTOHOUSE_DATABASE" --plan "$PHOTOHOUSE_PLAN"
"$PHOTOHOUSE_PYTHON" scripts/provision_access.py review \
  --database "$PHOTOHOUSE_DATABASE" --backup "$PHOTOHOUSE_BACKUP" \
  --plan "$PHOTOHOUSE_PLAN" --reviewed-plan-digest "$PHOTOHOUSE_PLAN_DIGEST" \
  --authority-reference "$PHOTOHOUSE_AUTHORITY_REF" --restore-reference "$PHOTOHOUSE_RESTORE_REF"
```

For asset planning, use `plan-assets` with the corresponding private request shape.
Owner plans contain the phone login; output files are created exclusively with
mode 0600 on POSIX. Existing files/symlinks are not overwritten. Windows ACLs and
operator-controlled parent directories require separate host review; mode bits
alone are not an ACL guarantee. JSON reads are bounded and reject duplicate keys,
nonfinite numbers, invalid shapes and direct-file/symlink violations.

Copy the `plan_digest` only after reviewing the plan. Copy `review_digest` from
the separate successful backup review only after checking its reported effects.
The latter binds target/backup paths and physical identities, the entire logical
SQLite snapshot, plan digest and authority/restore references. Refreshing a changed
backup or replacing a file cannot silently preserve that acknowledgement. Both
digests are acknowledgements, not credentials or proof of operator authority.

Under separately authorized application, run `apply` with the same database,
backup, plan, plan digest and reference arguments, plus
`--review-digest "$PHOTOHOUSE_REVIEW_DIGEST"`. No apply occurs automatically after
review. Owner application prompts for password and confirmation with echo disabled;
getpass fallback is refused. Application rechecks expiry/state under the existing
write reservation and commits grants/mappings, audit and receipt atomically.

For receipt lookup use `receipt --database "$PHOTOHOUSE_DATABASE" --plan-id
"$PHOTOHOUSE_PLAN_ID" --reviewed-plan-digest "$PHOTOHOUSE_PLAN_DIGEST"`. Output is a
small summary including actor UUID for subsequent asset planning. It excludes
phones, passwords, tokens, keys, media paths and SQL dumps. A missing receipt only
describes that exact selected database/history, not other targets or pre-restore history.

Exit 0 means that command completed; review/validation explicitly remain
`applied=false`. Exit 2 is a sanitized refusal/error, 3 means result output failed
after application, and 130 is interruption. For an ambiguous apply result, inspect
the durable receipt before retrying. Failed plan writes may leave incomplete private
files; choose a fresh output after review rather than overwriting them.

## Source-only package

`scripts/build_staging_package.py --commit "$PHOTOHOUSE_RELEASE_SHA" --out
"$PHOTOHOUSE_SOURCE_ZIP"` accepts a full immutable local Git commit. A fixed
allowlist selects the protected app/UI, metadata/migrations, staging launcher,
operator and database-preparation tools, their guides and the incomplete config example. It reads Git blobs,
not working-tree files. Symlinks, missing files and oversized source blobs fail.

The deterministic ZIP includes `manifest.json` with source SHA and per-file SHA-256;
the builder reports the ZIP SHA-256. It includes no environment, dependencies,
database, media, certificate, private configuration, legacy server, model runner or
test credentials. It does not install/extract/deploy anything. Verify the ZIP hash
against independently reviewed evidence before later transfer/extraction; a manifest
is not a signature or authority. Existing output files are never overwritten.

The package needs an independently reviewed CPU-only environment; it is **not a
Windows runtime lock or an installable service**. The separate
[database preparation tool](DATABASE_PREPARATION.md) initializes new empty databases,
creates private backups and rehearses migrations only in memory. It never upgrades
an existing file. Do not invoke generic Alembic with ambient DATABASE_URL:
preparation uses an explicit in-memory connection. Runtime/application never
creates or upgrades the database.
Required schema remains `b6e3f9a5c721`.

`scripts/staging_app.py --config "$PHOTOHOUSE_PRIVATE_STAGING_CONFIG" --check-config`
validates only the selected config syntax. A separate `--serve` action would start
TLS and remains unauthorized/unexecuted here. Syntax checks do not verify a host,
certificate, DB, file ACL, ingress boundary or phone. The included example is
intentionally incomplete and must fail validation.

## Validation and remaining gates

Focused tests exercise actual CLI dispatch/services on migrated synthetic SQLite:
private plans, read-only review, owner bootstrap, exact mapping and existing original
audience, review acknowledgement, stale/changed/replaced files, tampering, expiry,
protected input refusal, non-overwrite and receipt recovery after output loss.
Package tests cover determinism, exact membership/checksums and unsafe Git objects.
The fresh-process package smoke uses only extracted source, synthetic SQLite and
in-process ASGI with socket/process guards; it is not Windows/TLS/device acceptance.

Run focused tests using `-m unittest discover -s tests/security -p test_operator_cli.py -v`
and `-p test_staging_package.py -v`. The repository retains the full security suite
and package smoke harness outside the runtime ZIP.

No restore, quarantine CLI, password reset, access reopening,
existing-database migration application, production-size rehearsal, dependency installation,
Windows/macOS service setup or phone installation is supplied by this slice.
Existing recovery services remain available only through their separately reviewed
offline APIs. Restored databases must stay closed until quarantine/reopening review;
this tool cannot reconstruct post-backup revocations or certify an old backup safe.
Initialization, backup and in-memory rehearsal now have a separate tested command.
Next local work is the CPU environment lock and a reviewed existing-database migration
apply/recovery procedure. Host/HTTPS/audience selection, legacy and
standalone service isolation and live/device acceptance remain separate gates.
