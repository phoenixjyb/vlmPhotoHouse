# PhotoHouse application

This repository owns API, UI and orchestration. External model repositories and
Windows runtime state have separate lifecycles.

## Task context

Use the relevant implementation and tests first. For runtime/environment work,
read `docs/agent-memory/PROJECT_TRUTH.md` and `docs/agent-memory/CODEX.md` as dated
handoffs; the April readiness document is historical, not mandatory reading for
every edit. Verify current launch configuration and provider code before making
runtime claims. Do not read other agents' notes unless the task needs them.

## Boundaries

- Use the repo-root runtime environment on its owning Windows host; do not
  substitute `backend/.venv`. A disposable Mac test environment is source-test
  infrastructure, not the Windows GPU installation.
- Do not infer the caption provider from old HTTP-server notes or infer external
  GPU use from the backend `/health` device field. Runtime claims require checks
  against the actual target; Mac localhost is not the Windows service.
- Prefer API/CLI workflows for application changes. Direct database repair,
  reprocessing, retrying jobs and caption-service control require task authority.
- Keep anonymous selected-photo TV access separate from protected phone/library
  routes. Do not broaden access because a TV fixture or LAN request succeeds.
- Preserve originals, user data and existing edits. Keep credentials, media,
  biometric data and model weights out of code, fixtures and reports.

For a source fix, complete relevant tests and inspect the affected UI where
applicable. Report fixtures, API checks, live GPU/runtime state and real phone/TV
navigation or playback separately. Deployment, restarts, scheduled jobs and
publication remain specific external actions, not automatic post-test steps.
