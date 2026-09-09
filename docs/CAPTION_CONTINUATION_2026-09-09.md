# Qwen3 caption continuation — 9 September 2026

The user approved inspecting the four first-batch failures and continuing the
remaining Qwen3 caption workload. This is a live queue operation, not a backend
security deployment. No service restart, model change, wake/sleep schedule change,
caption-policy relaxation or Git push was performed.

## First batch review

Batch `refresh-20260909-first100`, tasks 449049–449148, finished with 96 successful
tasks and four explicit failures. All 96 successful assets had current bilingual
Qwen3 caption records. Its final success was at 09:57:16 China time.

The four failures were project caption-policy validation failures after bounded
correction attempts, not GPU/service failures:

| Task | Asset | Rejected wording |
| --- | --- | --- |
| 449056 | 27857 | English `no clothing` |
| 449099 | 693 | English `diaper`, Chinese `尿布` |
| 449100 | 694 | English `diaper`, Chinese `尿布` |
| 449136 | 51 | English `diaper`, Chinese `尿布` |

These four assets remain quarantined from automatic continuation. They need a
separate wording-policy decision or reviewed correction; no blind retry or claim
of successful repair is made. The historical failed tasks remain intact.

## Fresh audit and committed continuation

The current audit accounted for all 27,842 active assets:

- 20,946 eligible continuation assets.
- 6,879 already current or protected by manual-edit history.
- Four policy-quarantined assets above.
- Two missing/changed originals and 11 known unreadable/sidecar entries.

Eligible work: 12,571 older/short image captions, 4,147 missing image captions,
2,246 older/short video captions, and 1,982 missing video captions. Video captioning
uses the existing representative-frame path; it does not prove complete keyframe
processing or multi-frame understanding.

Batch `refresh-20260909-full-v1` committed **20,946 pending tasks**, IDs
**449149–470094**, at priority 110 with `force=true` and `replace_generated=true`.
All passed a fresh active-status, original-path/size/timestamp, caption-fingerprint
and manual-edit eligibility recheck under the queue write transaction.

The existing SYSTEM-owned API/worker processes this persistent queue serially.
`refresh_chunk` partitions the work into 210 reporting groups of at most 100; these
are **not** separate admission gates or an automatic failure-rate stop. The whole
eligible continuation is queued, with the worker's existing per-task retry and
terminal-failure behavior. It does not depend on the development SSH connection.

Evidence stays on Windows under the configured data root, in
`verification/caption-continuation-20260909/`:

- `plan.json`: fresh selection and pinned source hashes.
- `before-queue.sqlite`: consistent SQLite backup, verified with `quick_check`.
- `queue-intent.json`: fsynced exact task/asset IDs before commit.
- `queue-committed.json`: post-commit database count and task range.

An intent receipt alone never proves commit. Do not replay this operation; inspect
the exact batch in the database before any recovery or further queueing. The local
one-shot queue helper passed seven synthetic checks covering success/replay, busy
queue refusal, manual edits, changed originals, duplicate candidates, quarantined
IDs, and receipt-failure rollback. Its deployment targets were not generalized
into a new public CLI. The existing worker source hash was verified before use.

## Live acceptance checkpoint

At **15:53:34 China time**:

- Three new tasks finished, one running, 20,942 pending, no new batch failures.
- New caption records 86040–86042 reported
  `qwen3-vl-http|bilingual-en-zh-cn`; all passed the existing bilingual/policy validator.
- Qwen3 was ready and actively inferring; API/database/worker health passed.
- RTX 3090: 55 C, 39% utilization, approximately 113 W at the sample instant.
- Comparison with the fresh backup found zero changes to previous caption text,
  model labels or manual-edit flags, and zero original path/hash changes.

This proves resumed processing and initial saved outputs, **not completion or
visual factual-accuracy acceptance**. The workload is multi-day. Final coverage,
terminal failures, quarantined assets, file exclusions, and video/face processing
remain separate acceptance items. No new monitoring automation was installed.
