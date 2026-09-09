# PH-BACKEND-ANDROID-READINESS-01 — staging readiness review

2026-09-09. **Outcome: proposal prepared; real-phone browsing is NO-GO.**
Follow-up: [caption response budget fixed locally](CAPTION_RESPONSE_BUDGET.md) at
`0cf5058acdb25224b26847fb55670307f8113181` with 201 backend tests and 14 in-memory
Kotlin adapter cases passing. Android still pins `1e394f7`; coordinated review/repin
is pending. The initial source observations and failure below are retained as
historical evidence, not a claim that the new candidate still has that failure.
Deployment identity, origin, host configuration and test audience remain unknown.
This session has not deployed the protected backend. No live host, database, media,
phone, private configuration or remembered endpoint was accessed. The receiving
handoff asks for a proposal before external approval; it does not grant deployment.

## Answer to the Android handoff

| Question | Evidence-backed answer and remaining gate |
| --- | --- |
| Is the protected backend deployed? | **Unknown.** Local backend source is verified at `1e394f789ff1f7cef6d9930bb541186684f5a9a0`. No live process/release identity was inspected. A legacy web UI or a local pass cannot establish deployment. |
| What HTTPS origin should Android use? | **Unknown; do not configure credentials yet.** Exact hostname/port, system-trusted chain, DNS/private-network reachability and lifecycle must be selected/verified privately. Never infer an origin from historical host notes or reuse a test certificate. |
| Are migrations/provisioning ready? | Code requires **`b6e3f9a5c721`**, not the historical adapter document's `a5d2e8f4b610`. Actual target schema, owner, mappings, cached thumbnails and recovery state are **unverified**. Local audited services exist, but no reviewed operator command/package is shipped. |
| Is the exposure boundary correct? | Default `app.main:app` is closed: controlled synthetic `/auth/session` returns **503** without explicit runtime. The configured entry point has 23 active routes; 97 retired handlers and 32 standalone routes remain separate risks. Host ingress, other listeners, file shares and TLS forwarding have not been inspected. |
| Who is the first audience? | **No real operator/owner/viewer/library selected.** Proposed first stage uses reserved synthetic owner/viewer labels and generated media only. Later, the owner manually issues a phone-bound invitation to a deliberately scoped viewer; no original grant is needed for Android's current browsing flow. |
| What operations are authorized here? | Local source review, synthetic no-listener checks, proposal/doc edits and local commits. No Windows/Mac mini access, real DB/media/credentials, listener, service/account change, configured APK, phone installation, push or merge. Android's earlier fixture installation and PR publication do not transfer new authority here. |
| Who integrates the work / can CI fetch the backend? | This conversation remains the coordinator; platform owners retain their worktrees. Local stacked ancestry/evidence is inspected. Current remote PR/CI/merge status and backend availability to CI are **not rechecked**. Publication is not merge authority. |

## Exact source and artifact observations

- Mobile handoff checkout: `codex/android-backend-integration` at
  `5dd01eb48f3f9a0f1d4f81e3ae7cd22fe790d628`; latest implementation before its
  documentation-only handoff: `2bfb218a71e807e3531ebdcca79525574966aa5c`.
- Connected implementation: `1f42d5d93e273b4a39b09a5f1a121ff4f7fea6a6`; fixture
  implementation: `2d0382d22ad3ef1e15a55931765ad43e0cbd3ec7`.
- Frozen contract: `1.0.0-fixture.1`, mobile tag `photohouse-mobile-fixture-v1` at
  `5db14f38d3ff7872420f4c5ed16ff54b2cf9b4ac`.
- Ten backend source checksums and eight contract-pack checksums match. All **38
  synthetic ASGI contract responses replayed successfully** without a listener.
- The local connected APK exists and its SHA-256 matches the handoff:
  `259a42051066ae862fe96a311a0fd128607b5cde185d5442d7385d35d3056ab9`.
  Configuration/installation status is reported by the handoff, not inferred from
  its hash. Its default configuration is empty in source. No ignored local.properties
  file was opened and no APK was configured or installed in this task.
- Earlier Android evidence reports 49 ordinary JVM tests plus six real-loopback-TLS
  backend tests, two APK builds and prior emulator checks. Those reports/XML/JSON
  were read; the socket-opening TLS suite and emulator/device tests were not rerun.
  Earlier backend evidence reports 198 security tests; no fresh full-suite claim.

## New compatibility finding: caption response budget

A source check found Android's `HttpsPhotoHouseApi.JSON_LIMIT = 524288` bytes.
The pinned server permits 20 caption texts of 8192 characters each, with no aggregate
UTF-8 response budget. A controlled temporary SQLite/ASGI probe returned a valid
**200 response of 657749 bytes**, containing twenty 8192-character synthetic texts.
Android's adapter rejects a response above its limit as TOO_LARGE. A normal small
caption response was 194 bytes and succeeded. This is an interoperability/availability
failure, not an authorization bypass. It was absent from the canned baseline cases.

The reproducible [probe result](evidence/android-readiness/source-asgi-probe.json)
records `caption_budget_compatible=false`; the probe exits **1**, deliberately
reporting the unmet compatibility requirement. Do not relabel it as a passing test
or hide it behind a fixture-only exception. Fix the backend encoded-response budget
with honest `truncated`/`has_more` semantics, or agree a bounded cross-platform limit;
retain Android's memory protection. Add a real Kotlin/backend boundary regression,
then review and repin the changed backend source/contract before unrestricted use.
For a separately approved synthetic staging experiment, use only known bounded
fixtures; that does not close the compatibility finding for real-library readiness.

Other pilot limits to verify on the selected data: Android JSON <=512 KiB, thumbnail
body <=1 MiB, decoded width/height <=1024, memory cache <=8 MiB. The current app
requests cached previews and does not need originals. Missing previews must remain
placeholders and must not trigger original fallback or model work.

## Concrete proposed staging target and configuration

**Proposed target, not confirmed:** a separate CPU-only staging instance on the
existing Windows PhotoHouse host, reachable only on its deliberately selected
private/VPN interface. The operator was asked to confirm this target preference;
no answer or approval is inferred from elapsed time. No Mac mini proxy, public
internet ingress, legacy listener reuse or GPU/model integration is proposed.

Use a dedicated staging root, release directory, Python environment, database,
original-fixture directory, derived-fixture directory, backup directory, local
configuration and service identity. Do not share the production database, model
virtualenv, media root, logs or worker process. Select the actual absolute paths,
interface address and unused port privately after host review; this task invents
no real host/path/port values. Keep them out of public artifacts.

The [machine-readable decision record](ANDROID_STAGING_DECISION.json) intentionally
has null origin/path/target/approved-release values and `deployment_authorized=false`.
It is a proposal checklist, not a launch configuration. Every null deployment input
must be supplied and reviewed locally before generating a runnable command.

| Setting | Proposed requirement |
| --- | --- |
| Source | Candidate with caption-budget fix `0cf5058acdb25224b26847fb55670307f8113181`; approved release SHA is unset. Android pin update remains pending; later launcher work needs a new reviewed release. Export/review exact immutable Git objects, never a moving master or dirty worktree. |
| Runtime | Explicit `RuntimeConfiguration(database=Path(...), web_origin=..., original_roots=(...), derived_root=...)` followed by `build_app()`. No `.env`/legacy settings/default-path discovery, schema fallback or worker startup. |
| ASGI entry | A separately reviewed private launcher constructs that runtime; **stock `app.main:app` alone will not activate access**. The launcher/config/operator tool still need local implementation/review; existing model startup scripts are unsuitable. |
| TLS | Direct TLS at the staging ASGI server using the selected host's system-trusted certificate chain and protected private key; Android normal system trust and hostname validation. No test/user CA bypass, cleartext, redirects, path prefix or custom trust in the APK. |
| Network | Explicit private/VPN interface and reviewed staging port; firewall/ACL permits only the approved test network/devices. No `0.0.0.0`/`::` wildcard bind, public router forwarding or implicit existing-service route. |
| Host/origin | One canonical HTTPS origin matches Android and `web_origin` exactly. Omit explicit default `:443`; retain a selected nondefault port. No path/query/fragment/userinfo. Verify actual Host serialization on the phone. |
| Forwarding | Initial direct-TLS stage uses `proxy_headers=False`; ignore supplied forwarding headers. If a reverse proxy is later chosen, separately review its fixed peer allowlist, stripped/rebuilt headers, exact Host, scheme, source/admission identity and cache policy. Never trust `*`. |
| Serving | Proposed one worker, asyncio/h11, no reload or websockets, explicit concurrency/timeout limits (initially 16 requests and 5-second keepalive), no access-log request URLs or raw credential/body logging. Tune only after measured synthetic tests. |
| Database | Separate explicit SQLite target at `b6e3f9a5c721`; `foreign_keys=ON`, no silent create/migrate/repair by runtime. Local writable DB directory only for SQLite and access state; no shared network-drive assumption. |
| Media | Generated synthetic originals/prebuilt cached thumbnails only at first. Read-only runtime media ACLs, no static-file/proxy media alias, no worker/model generation. |
| Dependencies | A separately reviewed CPU-only lock/environment. Existing requirements are broad and include unrelated processing dependencies; current Mac test overlay is not a Windows production lock. Verify installed Python/SQLite/OpenSSL/scrypt and package versions on the target before use. |

Direct TLS, explicit bind addresses, proxy-header controls, asyncio selection and
access-log controls are supported by [Uvicorn's official settings](https://uvicorn.dev/settings/).
The choices above are this proposal, not evidence of host configuration. Do not use
untrusted HTTPS test certificates or the JVM integration harness as a deploy launcher.

## Sequence, backups and rollback

1. **Local release preparation (partially complete):**
   caption budget and Kotlin boundary checks are implemented locally; coordinate
   Android review/repin and baseline replay with its owner, then
   prepare explicit launcher/config validation and operator provisioning tool; pin
   a CPU runtime; review source and update the frozen consumer pin coherently.
2. **Operator target review (new scoped authority required):** establish exact host,
   staging paths/interface/port, certificate/renewal, stopped-worker procedure,
   filesystem identity/ACLs, current process versions and protected versus legacy
   ingress. Read only the approved metadata. Do not probe remembered services or
   read photo/account rows. Confirm the intended owner and rollout/rollback owner.
3. **Isolated synthetic staging (separate external-write authority):** provision only
   the reviewed staging root/environment/config. Keep ingress closed. Verify release
   hashes and dependency lock. Create an empty synthetic database explicitly, migrate
   it with Alembic's **supplied connection** to the exact required head so ambient
   DATABASE_URL cannot redirect it. Capture pre/post revision, integrity and foreign
   keys; no production migration or automatic startup migration.
4. **Reviewed provisioning while quiescent:** seed only generated synthetic assets
   and cached thumbnails, then preserve a separate consistent backup with hashes,
   ACLs and a rehearsal restored into a different temporary target. Make a sealed
   new-owner/library plan; verify its digest/backup/authority; use protected password
   input for atomic apply. Refresh the backup/review before exact unmapped-asset
   assignment because the first apply changes database state. Preserve receipts.
   No automatic household mapping or original permission. Use the owner web/session
   flow to issue a phone-bound viewer invitation manually; no secret in commands/logs.
5. **Host synthetic acceptance before phone credentials:** launch only the explicit
   staging application under direct TLS after approved ingress changes. Correlate
   process executable/release hashes/config with the reviewed source; a 200 UI or
   401 anonymous session alone does not prove DB/runtime readiness. Run actual login,
   session, library, caption, thumbnail and denial checks with synthetic accounts.
6. **Configured Android and phone (separate operation authority):** Android owner
   places the private approved origin in ignored android/local.properties and builds
   `dev.photohouse.connected`; record source and new APK hash locally. Keep that APK
   out of public CI/uploads. Confirm exact phone identity and installation scope;
   earlier fixture installation is not connected-install approval. Test synthetic
   invited registration/login, foreign/unavailable access, actual thumbnails/captions,
   revocation, background/foreground, offline/error recovery and acknowledged logout.
7. **Real-library pilot is a later gate:** nominate actual owner/viewer and exact
   selected library/asset IDs privately; separately authorize real backup, migration,
   mapping and credential operations. Reconcile any prior access history/restore
   state before activation. Do not point staging at the real database to save time.

Rollback is confined to staging: close its ingress and stop its process, preserve
sanitized failure/receipt evidence and leave legacy production processes/config/data
untouched. Never route the app back to an anonymous legacy service as a fallback.
Restore only to an explicitly selected offline target with the approved backup and
matching code/schema; the migrations intentionally refuse destructive downgrade.
An access-bearing restore requires quarantine: fresh plan key, revoked sessions,
cancelled invitations, disabled accounts and closed libraries. Reopening is still
unimplemented and must remain closed pending review. For disposable synthetic
staging, prefer a newly provisioned clean synthetic environment after approval over
reopening restored credentials. Keep invalidated archives and credentials private.

## Acceptance and return to Android

A staging release is not ready until all of these have evidence:

- Exact live executable/source/config/runtime identity; required migration head and
  explicit owner/library/asset mapping; backup and offline restore/quarantine rehearsal.
- Android system TLS/hostname success at the selected private origin; invalid host,
  HTTP, forwarding spoof and expired/untrusted certificates fail without fallback.
- Approved viewer reads only mapped library metadata/previews; invalid invitation,
  anonymous/expired/revoked/foreign/deleted/unmapped access is denied before effects.
- Cached previews/caption responses fit agreed client budgets; missing media stays
  unavailable; pagination/error/admission/Retry-After and logout behave as specified.
- Legacy search/albums/voice/operations, standalone service ports and raw media aliases
  are not alternate paths from the test audience. No real media enters public evidence.
- Configured APK SHA and installed package/device identity correlate; EN/ZH, large
  text/TalkBack, private cover, offline behavior and revocation/logout pass on that
  exact phone/build. Source, JVM/TLS, emulator and device outcomes stay separate.

Return packet is [ANDROID_READINESS_RETURN.md](ANDROID_READINESS_RETURN.md).
This review supplies no approved origin or credential. The next local work is the
Android repin and launcher preparation; the next external step needs explicit scoped
authority and private target inputs. No push, merge, deployment, service restart,
account change or phone installation was performed.
