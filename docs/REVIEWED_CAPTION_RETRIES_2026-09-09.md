# Eight reviewed caption retries and progress monitoring

## Scope and source

The owner approved addressing the eight failures identified in the earlier
caption-refresh checkpoint and adding read-only progress monitoring. This is
separate from the mobile-security worktree and does not change the caption model.

Source commit `01ade4729cebc153bc71b3a004ffa498d86ab9a3` on
`codex/infant-care-caption-policy` adds a fixed `caption_review=factual_rewrite`
task mode. It asks for directly visible facts, omission of uncertain details,
and aligned English/Simplified Chinese paragraphs. It explicitly forbids turning
uncertain statements into confident claims. It does not accept arbitrary task
prompts, weaken validation, change the global prompt or impose a hard word limit.
Saved results record the `-factual-review-v1` model-version suffix.

Five approved baby-care assets use the existing private operator allowlist,
extended only for this library's reviewed assets. The original four successful
exceptions remain configured. No real asset IDs are embedded in source defaults.
The three speculation/activity failures use the new factual-review mode.

Manual-caption protection, append-only caption content/history, final bilingual
validation and the normal bounded corrective retries remain in effect.

## Validation and deployment

- 18 policy tests passed locally with app startup isolated. The ordinary Mac app
  import is unavailable because this checkout lacks the full runtime dependencies.
- All 18 policy tests and 18 selection/persistence tests passed in the actual
  Windows environment, using full module imports, synthetic SQLite data, a mocked
  provider, GPU disabled, and no skipped tests. No models or data were copied to
  the Mac. These are focused tests, not full backend regression or visual accuracy
  acceptance.
- The immutable `photohouse-01ade47-reviewed-eight` release was staged with source
  archive SHA-256
  `3cd6a9d92d7ee55ce3c49b13c9dae39de15a552a45ca09fb9cdf47e5b9fbcb29`.
  It reuses the existing app environment and leaves the previous release intact.
- Preflight and PowerShell parsing passed. A fresh consistent database backup
  passed `quick_check`. The 20,472 pending continuation jobs were temporarily
  deferred with an exact restoration manifest and a finite automatic expiry.
- After the active task completed, a SQLite write reservation guarded stopping
  the old API with zero running/due tasks. No running task was reset.
- At **19:28:28 China time**, API cutover passed. The Qwen process remained
  unchanged. API/database/worker health and InsightFace CUDA/LVFace configuration
  passed. No migration, Qwen restart, wake/sleep change or model update occurred.
  The API task action points at the new release; its triggers/settings/principal
  and the entire Qwen scheduled task were unchanged.
- All 20,472 deferred schedules were restored. Eight distinct priority-50 tasks
  `470099`–`470106` were committed as `reviewed-eight-retry-20260909`, preserving
  the original failed rows. The first retry was observed running.

At this deployment boundary, `refresh-20260909-full-v1` had 456 finished,
20,472 pending and 18 failed tasks. Eight of those historical failures are the
approved retry targets; ten newer failures require separate review. Do not
silently add them to this operation or infer that the full library is complete.

Windows evidence remains in the new release directory: `windows-tests.json`,
`before-cutover.sqlite`, `queue-hold.json`, `api-task-before.xml`,
`api-cutover-receipt.json`, `reviewed-retry-intent.json`,
`reviewed-retry-committed.json`, and `queue-resume.json`. Never replay a mutation
from an intent file alone; reconcile committed receipts and live state first.

## Eight-photo saved-result acceptance

At **19:32:42 China time**, all eight retry tasks finished without errors.
New caption records `86500`–`86507` each use
`qwen3-vl-http|bilingual-en-zh-cn` and pass the unchanged validation checks with
the appropriate scoped policy. The five baby-care results record
`bilingual-v1-infant-care-v1`; the three factual rewrites record
`bilingual-v1-factual-review-v1`. This verifies stored model outputs, not human
visual factual-accuracy acceptance.

Comparison with the pre-cutover backup found zero changes to existing caption
text/model/manual flags and zero changes to original path/hash identity. All
eight original failed task records remain preserved. No deferred pending schedule
remained changed. API/database/worker and Qwen were healthy, the UI returned
HTTP 200, and the RTX 3090 sample was **67 C**. The main queue had resumed with
one running task, 20,471 pending, 456 finished and 18 historical failed rows.

Of those 18 historical failures, eight are now resolved by the new successful
retries. Ten newer failures remain outside this retry authorization:

- Speculative wording: assets 206 (`likely`), 291 (`suggests`),
  and 355 (`likely`, `可能`).
- Baby-care wording: assets 447, 448, 449, 450, 451 and 453
  (`diaper`, with `尿布` in five cases).
- Chinese inferred activity: asset 463 (`拍摄`).

These ten were inspected through task diagnostics only, not requeued or granted
new exceptions. Windows evidence: `eight-retry-verification.json`. The full
library backlog remains ongoing; historical failed-row counts do not subtract
later successful retries automatically.

At **19:33:32 China time**, a separate SSH connection verified the new API release
identity and the same Qwen process. Main-batch completions advanced to **457**, with
**20,470 pending and one running**. This proves continued main-queue progress
after the retries, beyond the startup-health check. Windows evidence:
`post-retry-progress.json`.

## Monitor

Thread heartbeat `photohouse-caption-progress` is configured every 15 minutes.
It reads current access instructions and checks service identity/health, batch
counts, recent completions/failures and GPU temperature. It stays quiet during
normal progress and alerts on actionable changes: unavailable services, a
30-minute stall while work should run, five new failures, completion, or a
conservative operator alert threshold of 80 C. This threshold is a notification
choice, not a hardware safety certification or automatic thermal control.

The monitor has no authority to restart, wake/sleep, requeue, change policy,
edit repositories or write the live database. Existing intentional pauses must
be respected. Queue drain is not proof of bilingual caption coverage or visual
accuracy. Configuration was confirmed through the app; a future scheduled run
and its notification delivery are separate acceptance gates.

Source is committed locally; no GitHub push or merge is part of this operation.
