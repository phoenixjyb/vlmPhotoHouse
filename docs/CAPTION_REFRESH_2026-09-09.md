# Caption refresh — 9 September 2026

Follow-up: the user subsequently approved the PhotoHouse service upgrade and
restart. The blocker below is now resolved by the live `f2bb0a0` caption server;
see [service cutover evidence](SERVICES_CUTOVER_2026-09-09.md). The remainder of
this document preserves the pre-cutover implementation and canary snapshot.

## Requested outcome and phased plan

The user approved progressing from the coverage audit and explicitly requested
replacement of the old short one-line captions. The intended outcome is detailed,
factual bilingual Qwen3 captions, with no hard output word-count requirement.

1. Implement and verify a history-preserving bounded refresh runner.
2. Repair the caption-service constraint mismatch; verify previously failed cases.
3. Expand controlled batches over eligible older/short/missing captions.
4. Separately repair incomplete video keyframes and standardize face embeddings
   before person matching. These stages are not completed by caption refresh.

The API, model server, wake/sleep schedule, model weights, and face assignments
were not restarted or changed in this slice. The runner uses the existing Windows
HTTP inference service. No private media, model, or database file was copied to
the development Mac. Source commits remain local; no GitHub push was performed.

## Implementation

PhotoHouse release `e4f1ffe` contains `scripts/refresh_captions.py` and an opt-in
`replace_generated` caption-handler path. Applying requires an explicit saved
plan, new receipt, a bounded limit (1–100), an idle queue and a single-run lock.
It records its own running/terminal task rows and never gives the old live worker
replacement jobs. Repeated failures stop the batch. A stale lock or running row
after an interrupted process needs inspection, not automatic deletion/requeue.

Successful validated bilingual Qwen3 output is appended. Previous machine
captions are marked superseded in the same SQLite transaction; their text, model
labels, and IDs are preserved. Existing user edits are excluded. Edits made during
inference are checked again under a write transaction and preserved. Failed
generation or saving does not archive old captions. Status updates are part of
the successful save; commit errors propagate instead of reporting success.

Selection includes missing captions, older-model/monolingual captions and short
bilingual one-liners. The short-caption heuristic is selection-only, not a new
minimum/maximum length requirement on generated text. Current detailed bilingual
captions, all user-edited history, known unreadable files/sidecars, and missing or
size-changed originals are excluded. PhotoHouse's general API regenerate route
has not been upgraded to expose this opt-in path; use the guarded runner.

## Audit and safety evidence

Initial eligible plan: 21,049 assets.

| Kind | Older/short replacement | Missing caption |
| --- | ---: | ---: |
| Images | 12,632 | 4,178 |
| Videos | 2,246 | 1,993 |

Excluded: 6,780 current-or-user-edited assets, two missing/changed originals,
and 11 known unreadable/sidecar entries. This is a planning snapshot, not queued
or completed work.

A consistent SQLite backup remains on Windows under the configured data root:
`backups/caption-refresh-before-edf7d59-20260909.sqlite`. It passed `quick_check`
and recorded 28,206 assets and 35,551 captions before any refresh writes.

Focused validation on Windows:

- 11 refresh selection/persistence tests passed in the existing app environment.
- 29 existing caption-service and prompt-policy tests passed in an isolated test DB.
- 11 caption-model server tests passed in the app environment and again in the
  actual caption runtime (nine plain test functions and two unittest cases).
  No new packages or model downloads were needed; the caption runtime has no pytest.

An initial canary conservatively skipped the old-caption asset because SQLite
integer booleans and ORM booleans produced different fingerprints. `e4f1ffe`
normalizes their representation and adds a regression test. The saved plan
remains compatible because its SQLite representation is unchanged.

## Live canaries

Two assets received new validated bilingual Qwen3 captions:

- An old one-line photo: three prior captions archived intact, a new 70-word
  English paragraph plus Chinese paragraph saved. The live caption API returns
  the new record last, matching the UI's current selection behavior.
- A newly ingested video: a 67-word English paragraph plus Chinese saved from
  the existing representative-frame caption path. This is not multi-frame
  understanding or proof of complete video processing.

One previously failed new photo still failed Chinese policy validation after
bounded corrective retries. It remains explicitly failed, not marked complete.
The canary receipts are in the corresponding immutable Windows deployment
folders (`canary-receipt.jsonl` and `one-liner-canary.jsonl`).

A whole-database comparison against the backup found zero old caption text,
model, or manual-edit flag changes. Three superseded flags changed intentionally
for the successfully refreshed photo. Model output passed automatic structure
and policy checks; visual factual accuracy still needs user review.

## Identified blocker and staged remedy

The live caption server is still the older source under `photohouse-7c0079e-cuda`.
Its `caption_server.py` has no `avoid_terms` handling, decoder exclusions, or
translation-correction helper. The newer backend sends translation constraints
that this older server ignores. This explains why a corrective translation can
repeat wording the backend rejects; replaying the same failed tasks is insufficient.

Caption-model source `f2bb0a0` is staged separately as
`photohouse-caption-models-f2bb0a0`, with junctions to the existing Windows
environment and weights. Tests cover reviewed-term filtering, decoder token
exclusions, masked corrective translation, and serialized inference while health
remains responsive. It is NOT the running model service yet.

Next gate: explicitly approve upgrading/restarting only the Windows caption
service while retaining the web API/UI, model weights and existing wake/sleep
times. Then rerun the failed-photo canary before expanding the refresh batches.
The full 21,049-asset plan has not been queued. Video-keyframe repair and face
embedding/person-assignment work remain separate subsequent stages.
