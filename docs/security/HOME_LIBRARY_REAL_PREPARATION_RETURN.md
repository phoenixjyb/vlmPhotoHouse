# Real-library preparation — active qualification checkpoint

2026-09-12, 15:42 +08. **Representative qualification is running; the uncapped
full-library preparation has not started.** This is an operational checkpoint,
not a completed preparation or publication receipt.

User continuation authorized real qualification, then full-snapshot preparation
only after resource, correctness and capacity gates pass. Preserve originals,
the metadata database, existing publications and caption/service processes.
No audience publication, service activation/restart, caption pause, weaker guard,
backend push or merge is included.

Source remains `ee5c06faea3d6f62ec356a9f7bb086d3569aea59`, with the previously
verified `library-sdr-v1` profile. New derived job: `home-library-profile-v3`,
revision 3, **27,842 visible entries**, 12 reviewed representative cases. Private
operator paths and per-asset IDs remain on Windows. The source checkout is
`codex/home-media-profile-coverage` in `_worktrees/home-media-profile-coverage`.
The independent protected-phone candidate uses another checkout and has not
changed this preparation source.

| Job pin | SHA-256 |
| --- | --- |
| Job file | `082dd880edbd08b5a500b9d93648be4a32e1c4051f9a6eeceaa0b62bb534b818` |
| Full snapshot | `85d462852d7ef1a017e2e8ac5921a615fe6fea144bdf2826ab6eaa83d38cc067` |
| Qualification plan | `51ffe86b8578fb439ae973a11f59e4bbcad4b1ec2b54c8bd1cd25033824d25b1` |

Current checkpoint: **4 ready, 1 working, 27,837 pending, 0 deferred, 0 errors**.
Completed cases are two verified carry items and two real 8K clips:

- 11.6936-second source: 84.125 seconds preparation; full decode/hash checks passed.
- 53.931367-second source: 351.141 seconds preparation; full decode/hash checks passed.

The largest/longest 8K HEVC file (8,193,114,694 bytes, 816.667433 seconds) is still
encoding. No completed output or throughput claim is made for it. The selected
large photos, long full-range video and two diagnostic probe cases remain pending.
An owned hash stop was observed, its child killed/waited, and the same checkpoint
resumed without adopting the interrupted attempt. Both carried results were
verified before reuse.

At 15:30, the active child had about 649 MB observed peak working set, below the
1 GiB guard. Coordinator and child priorities were verified below normal. The
initial detached launcher exited before any checkpoint attempt; qualification
therefore runs through a held SSH invocation. The attached coordinator initially
remained at normal priority; a verified owned-PID operation corrected it. No
unrelated process priority or lifecycle was changed.

The latest control/config/seed hashes and four service PID/start identities still
match baseline. Caption rows progressed from 42,687 at preflight to 42,765; failed
caption tasks rose from 440 to 441, with four dead tasks still recorded. This is
coexistence evidence, not proof of zero performance impact or causation for the
failure. No caption retry, pause or model endpoint was invoked. Free storage
remains about 5.245 TB.

[Checkpoint evidence](evidence/home-library-real-preparation/checkpoint-initial.json)
contains aggregate/case aliases only. Its checkpoint resource summary reflects
the last completed stop pass, not the active encoder's current peak; native process
observations are reported separately above.

Next: finish all representative cases, inspect errors/deferrals and measured
source/output/time/resource distributions, then decide whether the authorized
full run satisfies its gates. The per-file worst-case output caps total about
18.2 TB for videos alone, so 5.245 TB free is not a mathematical guarantee that
all outputs fit. Measured storage estimates and the unchanged reserve guard both
matter. No bulk completion ETA is established from two 8K examples.
