# Real-library preparation — qualification resumed

2026-09-12, 20:27 +08. The user authorized continuation after memory recovered.
**The same 12-case qualification has resumed; full-library processing has not
started.** The earlier memory stop below remains historical evidence.

Available RAM was about 50.7 GiB at both 20:21 and 20:22, similar to the earlier
post-feed-recovery measurement. A one-shot background process resumed the exact
revision-3 job, qualification plan and stopped checkpoint, with all 323 source
hashes verified against `ee5c06faea3d6f62ec356a9f7bb086d3569aea59`. The five ready
outputs are verified for reuse before remaining qualification work. No profile,
timeout, resource guard, publication or task trigger changed.

The native runner is PID 3148 (redirector 12076), started at 20:26:24 +08,
below-normal priority in session 0, independent of the launching SSH connection.
It uses a hidden session-0 console, **not** a console-free process; a synthetic
parent/child proof and native observations found no WindowsTerminal/OpenConsole.
Diagnostics use the reviewed bounded logger from the home-feed recovery. The
one-shot operator wrapper SHA-256 is
`0393d826971a59629ed6cc284d469354ce34f17ddcfd7120668f0c58825a5b14`.
Private process/telemetry receipts are under
`%LOCALAPPDATA%\PhotoHouseAccess\qualification-resume-20260912` on Windows.

[Resume checkpoint](evidence/home-library-real-preparation/checkpoint-resumed.json)
distinguishes the current run's active resource samples from the previous stopped
run's persisted resource summary. The latter is not a new memory-pressure event.
API, captioning and both recovered home-feed process identities remained unchanged.
No automatic restart or bulk transition is installed: remaining qualification
results and the capacity review must pass before a full-library launch.

## Historical memory stop

2026-09-12, 17:07 +08. **Qualification stopped at 16:58:00 +08 with
`memory_pressure`; full-library preparation has not started.** The earlier
running checkpoint below is historical.

The largest 8K HEVC sample passed full preparation and verification: an
8,193,114,694-byte, 816.667433-second original produced 1,099,456,511 bytes of
normalized video/previews. Its `prepare_one` elapsed time was 5,653.563 seconds
(94.23 minutes), including validation. This is not the encoder-only time, nor
a full-library ETA. The output video is 1920 × 1080; the original is unchanged.

The next sample, the 664-second full-range video, was interrupted when available
RAM reached **4,239,200,256 bytes**, below the unchanged **4 GiB
(4,294,967,296-byte)** floor. The completed run summary contains 6,371 resource
samples and an observed owned-process peak of 655,355,904 bytes. These sampled
measurements are not an OS memory quota or a diagnosis of other memory users.

Checkpoint: **5 ready, 1 interrupted working entry, 27,836 pending**. The working
entry is persisted recovery state, not an active encoder. The runner and its
observed children were absent at 17:06:45, and the held SSH invocation completed.
No incomplete derivative was counted as ready. Three large-photo cases, another
long-video case and two diagnostic cases remain pending; qualification has not
passed. No bulk gate, bulk process, automatic retry or guard reduction was applied.

At 17:06, free storage was 5,244,024,569,856 bytes and available RAM was
4,419,506,176 bytes, only 124,538,880 bytes above the floor. This single recovery
sample does not establish sustained headroom. All 323 staged source hashes still
matched the pinned source. Existing publication/config/seed hashes and four
service PID/start identities matched baseline. Caption rows reached 42,950;
the latest task observation recorded 442 failed and four dead tasks, versus
440 failed at preflight. Captioning continued without intervention; the cause
of the increase was not established.

[Memory-stop evidence](evidence/home-library-real-preparation/checkpoint-memory-stop.json)
records the completed run and subsequent read-only observations. Next: inspect
memory pressure without changing other workloads, establish sustained headroom,
then review a resume of the same qualification plan with unchanged guards.
After qualification passes, complete the capacity/throughput review before bulk.
No caption pause, unrelated process stop, service restart or publication is
authorized by this evidence. The checkpoint and all five ready results remain
available for verified reuse.

## Historical running checkpoint

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
