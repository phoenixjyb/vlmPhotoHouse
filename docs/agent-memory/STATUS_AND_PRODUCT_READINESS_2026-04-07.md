# Status And Product Readiness

Snapshot date: 2026-04-07

This file is intentionally time-stamped. Refresh it when queue counts or major risks change.

2026-09-03 follow-up: the task-dispatch gap described below was closed by
wiring the existing `phash` and video handlers into `TaskExecutor.run_once()`
and making unknown task types fail explicitly. The queue counts in this file
remain the historical 2026-04-07 snapshot.

## Live Snapshot

Verified from the live API and SQLite DB:

- API/UI: `http://127.0.0.1:8002`
- worker enabled: `true`
- pending tasks: `9,529`
- running tasks: `1`
- failed tasks: `46`
- pending task mix: `caption=9,529`

Library state:

- total assets: `26,838`
- images: `22,838`
- videos: `4,000`
- assets with captions: `12,697`
- assets still missing captions: `14,141`
- face detections: `29,361`
- images with faces: `12,578`
- face embeddings present: `29,361`

Failed task mix:

- `image_tag`: `21`
- `thumb`: `14`
- `face`: `8`
- `person_label_propagate`: `3`

Known stale asset rows still in DB:

- `E:\01_INCOMING\Jane\mostjane_s25_2026Feb\Camera\20240825_112216.jpg`
- `E:\01_INCOMING\Jane\mostjane_s25_2026Feb\Camera\20260213_155855.jpg`

## What Has Been Achieved

- Intake for `E:\01_INCOMING` is complete for the current corpus.
- Image and video embedding coverage is in place for the current library.
- Face detection and face embedding are effectively caught up for the current corpus.
- The live stack is using the real face and caption providers, not stub providers.
- `backend\app\config.py` now loads repo-local `.env` files for direct CLI work.
- `backend\app\caption_service.py` now prefers the external caption repo when configured, which matches the working runtime.

## What Is Still Running

- Caption generation is still draining.
- The backlog is now almost entirely a caption backlog.
- One worker slot is active and the queue is decreasing, but the job is not done yet.

## Product-Readiness Gaps

These are the main issues that still separate the project from a cleaner product-ready state.

1. Runtime docs are inconsistent.
   - Root `README.md`, old handoff docs, and several architecture notes still describe an HTTP caption-server-first setup.
   - The live system is currently using external subprocess captioning instead.

2. Launcher behavior and docs do not line up.
   - `scripts\start-dev-multiproc.ps1` sets caption env for the backend.
   - Its caption pane does not actually launch a caption API server.
   - Several docs still say it does.

3. Direct CLI defaults can still mislead operators.
   - Repo-local `.env` defaults still point at `CAPTION_PROVIDER=blip2`.
   - The live runtime depends on launcher-exported env for the real provider mix.

4. Worker dispatch for `phash` and video task types was incomplete in this
   snapshot. It was closed on 2026-09-03; unknown task types now fail instead
   of being silently marked finished.

5. There is still residual repair work in data and tasks.
   - `46` tasks are failed.
   - `2` known asset rows point to missing files.

6. Optional subsystems are not yet cleanly separated from the core product story.
   - RAM++ and voice are useful, but they are still mixed into launcher and doc paths in ways that raise onboarding cost.

## Recommended Next Work

Highest value next steps:

1. Finish the caption backlog and confirm post-run caption coverage.
2. Triage and repair the `46` failed tasks by type.
3. Remove or reconcile the `2` stale asset rows.
4. Decide the canonical caption runtime and align launcher plus docs around it.
5. Reduce env drift by making `.env` defaults safer or clearly labeling them as non-production defaults.
6. Collapse stale handoff docs into pointers so future agents stop reading old runtime assumptions.

## Practical Definition Of "Product Ready" For This Repo

For this project, "product ready" should mean at least:

- one clear start path for the working stack
- one clear caption runtime story
- queue drains without manual DB repair for normal use
- full intended task families are actually dispatched
- docs match code and launcher behavior
- optional services are explicit add-ons, not hidden core dependencies

The project is already operational and useful. It is not yet fully product ready because the runtime story, task-dispatch completeness, and docs are still not clean enough.
