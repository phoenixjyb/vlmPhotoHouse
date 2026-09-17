# Protected payload upgrade — `4022a57` → `e718b84` (return note)

**Status: DONE, 2026-09-17 ~12:25 CST.** The live protected API payload was staged at
source `e718b846c14205133b5a48df6e454916447154fe` and the protected API task was
restarted. The previous tree and both previous pin files are retained on the host.

Nothing in this note contains a host address, account name or private path. Operational
paths and credentials stay in the private access file, as the workspace rules require.

## What changed

| item | value |
| --- | --- |
| previous live source | `4022a57f56e6b2f976931a20569e15c879871d93` (85 files) |
| new live source | `e718b846c14205133b5a48df6e454916447154fe` (93 files) |
| bundle | `protected-e718b84.zip`, sha256 `f9b839de…6138d1`, 2 155 233 bytes, `deployed: false` |
| payload delta | **19 files — 11 modified, 8 added, 0 removed** |
| migration revision | unchanged, `d8e5b2f7a904` |
| database | **not written**; opened read-only for preconditions only |
| worker payload | **not re-staged** (supervisor byte-identical across the gap) |

The eight additions are the four discovery modules, `ownership_repair.py`, `tags.py`,
`OWNERSHIP_REPAIR.md` and the offline discovery-index producer. Three of those
(`discovery.py`, `discovery_provider.py`, `discovery_transport.py`) already existed at the
previous source but had never been in the payload allowlist — so the *payload* delta is
19 while the *source* diff against the allowlist is 16. The two numbers are not
interchangeable; this note records the payload one.

The entry script was patched in the same transaction, by byte-replacing the previous
commit string with the new one. **A stale assertion there is an outage, not a warning**,
which is why the patch is part of the swap rather than a separate step.

## Verification

- The staging script verified every bundle hash, the manifest file set, and asserted the
  exact changed set (11 modified / 8 added) before the swap. It exited 0 with
  `services_started: false`, `live_database_written: false`,
  `previous_source_retained: true`.
- It exercised the **new** code in-tree before the swap, using the task's own interpreter:
  the discovery, tags and ownership-repair modules import; the app composes with 48
  routes; the discovery transport exposes exactly its two routes; the artifact loader
  refuses a relative path; the reviewed provider refuses an unreviewed index.
- After restart the listener is held by a **new** process (the previous pid is gone), the
  task is Running, and the public UI shell answers `200` over TLS.
- The two discovery routes are **mounted and boundary-admitted** on the live service: they
  answer with the discovery transport's own `invalid_request` envelope, while a
  neighbouring unknown path (`…/discovery/v2/…`) still gets the closed boundary's
  `403 Access denied`. This is the first deployment in which those routes exist at all.
- Rollback is prepared and needs no rebuild: the retained tree, the previous entry script
  and the previous pins are all on the host, written before the swap.

## Two deviations from the plan, both deliberate

1. **The precondition block was replaced, as the plan instructed — but the plan's
   suggested replacement also does not hold.** `running_tasks == 0` is unachievable on
   this host by design: the caption worker legitimately keeps one task running while it
   drains, and the plan explicitly does not stop it. The assertion used instead is
   **"no running task outside the caption worker"**, which is the invariant that actually
   protects an API-only upgrade. Asserting zero would have failed for the wrong reason —
   exactly the failure mode the plan warned about.
2. **The in-tree sanity check could not use the template's `sys.path`.** The template put
   the application package directory itself on `sys.path`, which only works for modules
   that do not transitively import FastAPI: the application's own `logging` module shadows
   the standard library one, so `import logging` from inside FastAPI resolves to the
   application module and dies on a relative import. The check puts the *parent* directory
   on `sys.path` and imports through the `app.` package instead. Verified against the same
   source before staging; the naive form fails with `ImportError`.

## One operational observation, not caused by this upgrade

The caption worker was found **stopped** after the window (state `Ready`, no triggers, so
it will not restart itself). This is **not** damage from the upgrade, and the evidence is
the worker's own receipt: it exited through the supervisor's *clean-drain* path
(`clean_drain_confirmed: true`, `supervisor: "stopped"`, `claimed_tasks_processed: 3092`)
after a run spanning roughly 30 hours. An interrupted or killed worker takes the other
branch and records `refused-or-interrupted` with a non-zero task result; the recorded
result is `0`.

The upgrade did not stop it: the worker runs as a separate scheduled task, its entry
script asserts only its own three pins (not the protected manifest), and it had already
started its final claimed task before the API was stopped.

**Resumed 2026-09-17 ~13:42 CST on owner instruction.** Preconditions were checked
read-only before starting: the three pins the worker entry asserts
(`runtime-environment.json`, `worker-config.json`, `supervisor`) all still verify, the
worker tree is present, and the configured `stop_file` is absent. Note that the worker's
`stop_file` is the **same path** as the staging `stop-request` token — so removing that
token after the upgrade was not merely tidiness; had it been left behind, the worker would
have refused to run.

Started via the worker's scheduled task. It is confirmed **consuming the queue**, not
merely "started": a new `started` receipt was written, caption task ids advanced across
successive samples, five tasks finished within ten minutes, and the pending count fell
4451 → 4445. Both scheduled tasks are now Running (API on its new process, worker on a new
run). At the observed cadence the remaining queue is a multi-day drain, which is its normal
mode.

## Not done

- **No authenticated browser acceptance.** The plan's step 6 calls for one owner request
  against the new viewer control as the only proof the new UI serves. That needs owner
  credentials and the private relay, and is deliberately left to the owner. The evidence
  above proves the service is up, composed and answering; it does not prove a member
  journey.
- **No database change, no worker change, no other task touched.** The two
  `PhotoHouse-Home*` and legacy tasks were left alone.
