# PhotoHouse service cutover — 9 September 2026

## Scope and deployed identity

The user approved upgrading and restarting the PhotoHouse services on Windows.
Only the API/UI/inline worker and Qwen caption server were restarted. Optional
inactive services and unrelated applications were untouched. No model weights,
Python packages, media, or databases were copied to the development Mac.

| Component | Previous runtime | Verified new runtime |
| --- | --- | --- |
| API/UI/worker | `1248e5e`, listener PID 492 | `d51b7e7`, listener PID 19180 |
| Caption server | older source in `photohouse-7c0079e-cuda`, PID 11604 | `f2bb0a0`, listener PID 2116 |
| LVFace | existing Windows installation | unchanged; source matches local `2ab0e27` |

Cutover receipt: `PASS` at **2026-09-09 08:59:48 +08:00**. Source bytes and
process ancestry were checked, not just release labels: the old caption release
manifest claimed newer code, but its actual server lacked `avoid_terms` support.

The immutable deployments are `photohouse-d51b7e7-services/vlmPhotoHouse` and
`photohouse-caption-models-f2bb0a0/vlmCaptionModels` under the Windows deployment
root. Junctions reuse the proven Windows environments and Qwen weights. The
caption model remains Qwen3-VL-8B-Instruct, 4-bit NF4, on the RTX 3090. This is a
tested source upgrade, not an unvalidated latest-model/dependency migration.

Verified SHA-256:

- API archive: `5dfee449858ffac42664b7836738108369d5aa91712e0604bc0bcf91b952c487`.
- Caption server: `a8136aef8755a52d4333dcd0aa5c67f7dd14316a8fcee04da90d5e9f884e4601`.
- LVFace `src/inference_onnx.py`, normalized line endings:
  `1bd8bbebad2a30059cc176bcf4dfa7e3b048a87dd96a1884c4c3ee0c6898545e`.

## Restart ownership and rollback

Existing SYSTEM tasks now point to the new launchers/releases:

- `VLMPhotoHouse OneShot Start API 2026-09-07 0700 SYSTEM`.
- `VLMPhotoHouse OneShot Warm Qwen 2026-09-07 0645 SYSTEM`.

Both were verified running independently of the initiating SSH command. Task
triggers, settings, and principals match their exported pre-cutover XML. Wake and
sleep times were not changed; this does not establish a new daily schedule.
Stopping the tasks left child processes, so only verified old release process
trees owning the listeners were terminated before restarting. Launchers retain
foreground ownership. Log retention was set to 365 days to preserve older logs.

A consistent SQLite backup, `backups/services-before-d51b7e7-20260909.sqlite`,
passed `quick_check`: 28,206 assets and 35,553 captions. Before the new canary,
comparison found zero changes to original paths/hashes or existing caption text,
models, superseded flags, and manual-edit flags. No database restore occurred.

The new API deployment's parent directory retains `services-cutover.ps1`,
`services-cutover-receipt.json`, `api-task-before.xml`, `caption-task-before.xml`,
and health snapshots. The old API and caption releases remain available. A
rollback should restore the exported task actions and restart only these services;
it should not replace the database with the pre-cutover backup and lose new work.

## Validation

- 11 caption-refresh safety tests and 10 intake safety tests passed in the staged
  Windows API environment; both launcher preflights and cutover syntax passed.
- API/database healthy; UI HTML, JavaScript, and CSS served hashes match release.
- Search endpoints returned HTTP 200; the index reloaded 13,621 existing 512-D
  vectors. This does not mean missing general embeddings have been backfilled.
- InsightFace detection reports `CUDAExecutionProvider`.
- Two on-demand LVFace calls on an existing face crop produced finite 128-D
  embeddings, norm 0.99999994, maximum repeat difference 0.0, without DB writes.
- Qwen loaded in 42.8 seconds; health stayed responsive, the new inference
  concurrency fields were present, and OpenAPI exposed translation `avoid_terms`.
- GPU temperature was 45 C after startup and 58 C during the initial batch check.

Previously failing photo asset 27703 completed through the actual upgraded live
worker: task 449048, new bilingual caption 85943, no error, finished at
2026-09-09 01:02:09 UTC. The earlier failed task remains historical evidence.
The global historical failed-task count was 384; these were not blindly reset.
Automatic validation is not a substitute for reviewing caption factual accuracy.

## Controlled caption continuation

After the canary and an idle-queue check, batch `refresh-20260909-first100` queued
exactly 100 tasks, IDs **449049–449148**:

- 17 previously failed recent photo captions.
- 60 older short photo captions.
- 10 newly ingested videos missing captions.
- 13 additional photos missing captions.

Selection rechecked the saved audit's caption fingerprint, active status, original
path, file size and timestamp, and manual-edit protection. An immediate SQLite
transaction guarded the idle queue and duplicate batch check. The fsynced
`refresh-20260909-first100-queue.json` records intent and exact task IDs before
commit; live task rows independently confirm the committed batch. Do not replay
this batch based solely on its intent receipt.

Tasks opt into the upgraded worker's `replace_generated` path: only successful
validated bilingual captions supersede prior machine captions, retaining history.
This queue batch is bounded at 100, but unlike the standalone refresh runner it
does not stop the entire batch automatically on repeated failures. Do not expand
to the full 21,049-asset plan until this batch's outcomes have been reviewed.

At **09:11:39 +08:00**, live batch counts were **4 finished, 1 running, 95
pending, 0 failed**. A fresh whole-database comparison still found zero changes
to original paths/hashes or old caption text, model labels, and manual-edit
flags. These are initial processing results, not completion of the batch.

## Access and remaining gates

The previously closed Mac viewing connection was restored using dedicated
loopback-only SSH forwards through the Mac mini. Mac
`http://127.0.0.1:18002/ui` returned HTTP 200. On Windows use
`http://127.0.0.1:8002/ui`. These forwards are not configured as boot-persistent;
no public listener or OpenClaw configuration was introduced.

The full caption refresh is not complete. Video keyframe repair, general
embedding backfill, face embedding dimensional consistency, and person matching
remain separate acceptance gates. No face identities were reassigned. Source
commits remain local; no GitHub push was performed.
