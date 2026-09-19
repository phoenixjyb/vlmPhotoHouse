# September 19 readiness and deployment return

The owner authorized source repairs, review and Windows deployment on September 19.
Work began from clean `master` at `9d7e1d097519ffa37a79171671046933b3a2b10b`, in
`codex/readiness-deploy-20260919`. Existing worktrees and the mobile repository were
preserved. This receipt supersedes the September 18 handoff only where fresh evidence
is recorded below.

## Deployment state

**Deployed on Windows at 23:19 China time, September 19.** The owner identified the
existing Mac-mini Wake-on-LAN method; wake succeeded and the documented SSH route
reconnected. The protected API now serves source `45f2123` with schema `f2a6d8b4c915`.
The original source, task definitions and a verified stopped-boundary database backup
are retained on Windows. The caption worker is staged for the new schema but remains
fenced because its existing local model endpoint is unavailable. No model was loaded.

See [the Windows rollout return](WINDOWS_READINESS_ROLLOUT_20260919.md) for native,
service-account and public-HTTPS evidence. Authenticated owner/device acceptance is
still pending; the earlier connectivity block below has been resolved.

## Source repairs

- The deployment allowlist omitted seven new modules: upload, upload schema, upload
  transport, duplicates, captions, promotion and task recovery. Extracted-package
  import/CLI coverage now checks those modules; checkout-only tests had missed the gap.
- The staging launcher now accepts an explicit `discovery_indexes` list, default empty.
  Before this repair the runtime supported indexes but its production launcher could
  not configure them. Artifact paths must be distinct, canonical and outside media,
  incoming storage and credential/database files. The loader still refuses invalid
  artifacts; the configuration check does not produce or approve one.
- The offline schema tool now accepts `--from-revision d8e5b2f7a904`, preserving
  existing authentication and library data while adding upload metadata. Its default
  remains the pre-access transition. The current-account upgrade has synthetic
  preservation, stale-backup, stopped-writer, repeat and rollback tests.
- Promotion and unassignment must compensate file moves on plan expiry and other
  failures after a move, not only SQLite errors. The reproduced defect left database
  paths pointing to absent files; the repair is qualified with synthetic fault injection.
- The registration/profile documentation now includes required `name` and nullable
  session `display_name`. Upload documentation distinguishes its implemented source,
  25 MiB per-file bound and header validation from full decoding and deployment.
- Refused discovery-index preparation and SQLite environment qualification now close
  their database handles. Synthetic fixtures also close their handles; the runtime
  reload test restores class identities instead of polluting later refusal checks.

## Verified local evidence

- Packaged source commit: `45f2123ad3447213aad68010154a6d14ff3613f9`.
- Whole security suite: **986 tests, 0 failures, 0 errors, 7 skipped** (169.835 s).
  Four skips require native Windows APIs and three require separate worker dependencies.
  The run retained two upload-fixture connection warnings: their allocation sites were
  traced, then closed, with all **20 upload tests** rerun successfully under tracemalloc
  without resource warnings. The full run preceded that last fixture-only cleanup.
  Starlette/httpx and naive-UTC deprecation warnings remain; they were not suppressed.
  Operator refusal/cleanup checks separately pass **19 tests** without resource warnings.
- Browser: **53 checkpoints pass** with Chromium and the synthetic ASGI pipe bridge.
  The archived-album and saved-caption screenshots were visually inspected. The
  missing archive toggle loader and the stale no-caption hint after save are fixed.
- Promotion/transfer fault tests: **46 pass**; configuration and schema tests:
  **39 pass**. A failed compensation now reports manual recovery instead of hiding it.
  This is exception recovery, not a durable filesystem/SQLite crash transaction;
  power loss and the actual incoming/original-root ACL and cross-volume round trip still
  need separate qualification. Five transfer fault tests subsequently passed on Windows.
- Native pack: **candidate.12**, 61 captures unchanged from candidate.11, 109 source
  hashes and 7 payload hashes verified; all client profile defaults remain off.
- Extracted immutable package smoke: **pass**, 7 ASGI checks, 19 operator commands,
  9 preparation commands, schema `f2a6d8b4c915`, no listeners or live data.

| Artifact | Files | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| `protected-45f2123.zip` | 101 | 2,280,747 | `4a43efa1e789bb30f49038cb25c7b714dd39447375a3cfd94a4bdfa272be96c2` |
| `worker-45f2123.zip` | 15 | 196,341 | `2736e53b8ac41bb442a7f0c21aba00cf3391ed9c3c96aa3473517f62bb7a0687` |

File counts exclude each archive's manifest. These are source-only bundles, retained in the workspace's private handoff directory.
The protected bundle is now active on Windows. The worker bundle and compatible
configuration are staged, but worker execution remains fenced and unqualified against
the unavailable model endpoint. Immutable archive manifests retain their build-time
source-only labels; the separate rollout receipt records activation.

The local checks use the existing Workbuddy Python 3.13.12 environment, with no
dependency installation or upgrade. Reproduce from this worktree using that interpreter:

```sh
PYTHONPATH=tests/security:backend python -m unittest discover -v -s tests/security -t tests/security -p 'test_*.py'
python scripts/verify_protected_native_contract.py
python -I tests/security/package_smoke.py /absolute/path/to/extracted/protected-package
```

Chromium uses the existing `playwright-core` installation and
`tests/security/test_web_browser.cjs`, with `PH_BROWSER_PYTHON` selecting that Python
and `PH_BROWSER_ARTIFACTS` selecting a synthetic evidence directory. The browser
talks to an ASGI pipe bridge; these checks open no HTTP listener.

## Windows rollout procedure and deferred steps

Steps 1–5 are complete; step 6 has native/public transport and file-access evidence,
with authenticated acceptance pending. Steps 7–8 remain deferred. Do not replay the
migration: the live database is already on the new revision.

1. Re-read the private access runbook and inspect the actual host, task actions,
   payload manifests, launch assertions, environment/config pins, TLS, schema and
   writers. The directory names and previous receipts are historical evidence only.
2. Verify the immutable protected and worker bundles, including every manifest hash.
   Run synthetic extracted-package/native checks under the intended service interpreter.
   Prepare the replacement launchers/configuration and rollback bundle before an outage.
3. Drain the caption worker and fence every database writer. Record running tasks and
   confirm none remain. Do not clear an abandoned claim without the reviewed recovery
   operation. Retain the old task/config/payload state and take a fresh stopped-boundary
   backup on Windows; verify integrity and its full logical digest.
4. Run the read-only schema review against that exact backup, then repeat with
   `--execute --all-writers-stopped --from-revision d8e5b2f7a904` only if the observed
   source revision matches. See [SCHEMA_APPLICATION.md](SCHEMA_APPLICATION.md). Preserve
   existing accounts and sessions; do not use a recovery/quarantine preparation tool.
5. Stage the compatible protected payload and caption worker; update the entrypoint's
   source assertion, artifact pins, and worker `expected_revision` together. The old
   worker does not admit the new schema. Keep the prior source and configuration.
6. Start and verify the protected service under its actual principal: TLS/origin,
   anonymous and legacy denials, authenticated library reads, thumbnail/display ACLs,
   original grant and Range behavior, and the reviewed new features. Do not equate a
   task start or HTTP 200 shell with authenticated feature acceptance.
7. Generate and qualify the library-scoped discovery artifact before opting it in.
   Upload remains off until the incoming-root ACLs and the reviewed promotion/unassign
   round trip are qualified; do not enable it merely because its route is packaged.
8. Resume the caption worker only against the verified existing local model service,
   with the new schema configuration. Check real queue progress and failures. Do not
   start an arbitrary model or retry failed captions as part of an API deployment.

Before writes resume, rollback must restore the compatible payload/configuration and
database together. After writes resume, restoring the old backup would discard new
data and requires a separate write-preserving recovery decision. Anonymous TV/LAN and
SMB services are separate; this rollout must not broaden their access or restart them.

## Remaining delivery gates

- Authenticated owner/member journeys and phone/TV acceptance remain pending.
- The caption model endpoint is down; 3,029 caption tasks remain pending and the
  compatible caption worker remains fenced. No model startup or retry was performed.
- Discovery artifact freshness must be qualified alongside caption and metadata writes
  before enabling its deployment configuration.
- Upload header checks are not a full decode, an aggregate quota or a durable transfer
  journal. Upload stays off until its separate Windows qualification.
- Protected video/player parity, original-permission handling and Android/TV playback
  need client and device evidence; a successful Range response alone is insufficient.
- Existing caption editing, similarity reduction, map privacy and other deliberately
  deferred UI capabilities remain in [the parity ledger](WEBUI_PARITY.md).

## Android adoption handoff

The inspected protected Android worktree is at `f24fc41`, with a clean worktree and
`android/protected-native-contract/manifest.json` still on candidate.1, backend
`4022a57`, schema `d8e5b2f7a904`. This is a local checkout observation, not a fresh
GitHub or installed-APK check. Its registration API takes phone/password/code and
does not send the new name field.

The Android owner should adopt the newly issued backend pack explicitly, add the
registration name field (normalized to 1–64 Unicode code points), accept nullable
`display_name` for existing accounts, and replay the captured transport cases. Keep
invitation-only membership, no automatic originals grant, origin/TLS checks, revoked
membership handling and default-off profile flags. The new people/duplicates/caption/
album endpoints need their own client adoption; unchanged old captured cases do not
prove support for these features. Upload remains a separately disabled capability.

The backend rollout now makes the required registration name live. Existing login
remains supported, but the inspected old Android registration request must be updated.
Build and test a matching APK against this deployed source. Emulator fixtures,
installed-phone interaction and TV playback remain distinct evidence. No Android
source, contract pin, APK or device was changed by this backend task.

## Local source record

Worktree: `/Users/yanbo/Projects/vlm-photo-engine/_worktrees/readiness-deploy-20260919`.
Branch: `codex/readiness-deploy-20260919`. Local commits were not pushed or merged.
The original application checkout remains unchanged.

- `14bd371`: deployment packaging, configuration, migration, promotion and UI repairs.
- `45f2123`: refused-discovery and environment-check connection cleanup.
- `ec7b960`: candidate.12, final local evidence and upload-test cleanup.
- The subsequent rollout receipt records the successful Windows migration and activation.

Changed files relative to `9d7e1d0`:

- `backend/app/access/promotion.py`
- `backend/app/ui/access/app.js`
- `docs/contracts/protected-native-v2/CONTRACT.md`
- `docs/contracts/protected-native-v2/UPLOAD_NEXT.md`
- `docs/contracts/protected-native-v2/VALIDATION.md`
- `docs/contracts/protected-native-v2/cases.json`
- `docs/contracts/protected-native-v2/manifest.json`
- `docs/security/PROTECTED_UPLOAD_CONTRACT.md`
- `docs/security/READINESS_DEPLOYMENT_20260919.md`
- `docs/security/SCHEMA_APPLICATION.md`
- `docs/security/WEBUI_PARITY.md`
- `docs/security/WINDOWS_READINESS_ROLLOUT_20260919.md`
- `scripts/apply_access_schema.py`
- `scripts/build_home_discovery_export_fixture.py`
- `scripts/build_staging_package.py`
- `scripts/check_access_environment.py`
- `scripts/prepare_access_discovery_index.py`
- `scripts/staging_app.py`
- `scripts/verify_protected_native_contract.py`
- `tests/security/browser_bridge.py`
- `tests/security/caption_worker_fixture.py`
- `tests/security/native_contract_v2_probe.py`
- `tests/security/package_smoke.py`
- `tests/security/test_discovery_index_producer.py`
- `tests/security/test_discovery_wiring.py`
- `tests/security/test_existing_access_upgrade.py`
- `tests/security/test_home_discovery_export.py`
- `tests/security/test_home_people_review.py`
- `tests/security/test_home_search_metadata.py`
- `tests/security/test_phone_discovery_http.py`
- `tests/security/test_promotion.py`
- `tests/security/test_promotion_transfer.py`
- `tests/security/test_runtime_adapter.py`
- `tests/security/test_staging_config.py`
- `tests/security/test_staging_package.py`
- `tests/security/test_upload.py`
- `tests/security/test_web_browser.cjs`
