# Windows readiness rollout — September 19

The owner authorized deployment, then explicitly requested waking Windows through the
Mac mini. The established relay Wake-on-LAN command succeeded; SSH confirmed the
expected host. No router, firewall, credentials or model configuration was changed.
Private connection and power commands are in the existing private access runbook.

## Activated release

- Protected API source: `45f2123ad3447213aad68010154a6d14ff3613f9`.
- Database: `d8e5b2f7a904` → `f2a6d8b4c915`.
- Activation: **2026-09-19 23:19:39 +08:00**.
- Native client contract: **2.0.0-candidate.12**; Android adoption remains separate.
- The API retains the existing SYSTEM task, interpreter, TLS origin and listener.
  Its task name still contains the historical `04ed2fd`; the action now selects the
  new immutable stage. Runtime identity comes from its entry assertion and verified
  manifest, not the old task name.
- Upload and discovery remain off. Anonymous TV/LAN and SMB services were not changed
  or restarted by this deployment; they are not covered by protected-API acceptance.

## Evidence

1. Both source archives were verified on Windows before extraction: all **101 API**
   and **15 worker** file hashes matched. Exact archives/hashes are in the
   [readiness receipt](READINESS_DEPLOYMENT_20260919.md).
2. Under **SYSTEM**, extracted-package smoke passed seven ASGI checks, 19 operator
   commands and nine database-preparation commands. **12 native tests passed**:
   seven existing-account migration tests and five file-transfer fault tests.
   Windows event-loop wakeup sockets were preallocated before the smoke's network
   guards, as in earlier qualification; no HTTP test listener was opened.
3. The API and caption worker were already stopped after wake. Their task definitions
   were exported, both tasks fenced, and no PhotoHouse process or running database
   task remained. The unrelated OCR process was left alone.
4. Fresh backup and restore-check copy both verified **32 tables / 858,333 rows**
   with the same logical digest. The snapshot command labels itself copy-only;
   stopped-writer qualification was established separately, not inferred from that label.
5. Read-only upgrade review passed, then exclusive transactional migration preserved
   **31 data tables / 858,332 rows**, excluding only the schema-version ledger.
   Account/password/session/membership data was preserved, no accounts or asset grants
   were created, and upload provenance remains empty. Migration completed in **83.656 s**.
6. The replacement API started. **17 live checks under SYSTEM passed**, including
   certificate-chain/hostname validation, UI byte identity, anonymous denials for
   library/photo/face/album/caption/people/duplicate reads and an original Range request,
   plus closed legacy, operational and voice paths. Sample originals, 256/1024
   thumbnails and face crops were readable under SYSTEM; no media bytes were exported.
7. Independent **public-HTTPS checks from the Mac Air**, with no proxy or SSH tunnel,
   passed: JavaScript 200 and exact source hash, unauthenticated session/original Range
   401, legacy search/voice 403. No TLS verification bypass was used.

A successful unauthenticated denial is not an authenticated family journey. The owner
has been asked to sign in and check gallery, preview and people. That answer and real
Android/TV interaction are pending. No credentials or temporary production account
were created to manufacture authenticated acceptance.

## Remaining operations and rollback

The caption model endpoint is absent. At inspection the caption queue was **90,271
finished, 6,689 done, 3,029 pending, 558 failed and 15 dead**; no task was running.
The new worker configuration points to the staged compatible source/schema, but its
scheduled task remains **disabled**. This is a deliberate fence, not resumed captioning.
Qualify the intended existing local model and worker before enabling/resuming it;
do not silently retry failed jobs or load another model.

Upload still needs actual incoming-root ACL and cross-volume promotion qualification.
Discovery needs a reviewed artifact and a freshness plan alongside caption/metadata
writes. Existing Android registration omits the now-required name field: its owner
must adopt candidate.12 before claiming registration compatibility. Native voice,
protected video/player parity and the other deferred contract gaps remain separate.

Old payload/configuration, exported task definitions, stopped-boundary backup and
restore-check copy are retained on Windows. The API is now accepting requests, so
assume new writes may exist: restoring the old database would lose them. Rollback
must be an explicit write-preserving recovery decision, with compatible schema and
payload together; never start the old API or worker against the upgraded database.

The local branch remains `codex/readiness-deploy-20260919`. No Git push or merge and
no mobile-repository change accompanied this rollout.
