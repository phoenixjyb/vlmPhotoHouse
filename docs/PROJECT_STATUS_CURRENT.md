# VLM Photo Engine - Current Project Status

Last Updated: 2026-04-07

This file is now a pointer and short snapshot. The shared agent memory lives under:

- `docs/agent-memory/PROJECT_TRUTH.md`
- `docs/agent-memory/STATUS_AND_PRODUCT_READINESS_2026-04-07.md`

Use those files first for onboarding and current operational truth.

## Short Snapshot

- API/UI: `http://127.0.0.1:8002` and `/ui`
- originals root: `E:\01_INCOMING`
- data root: `E:\VLM_DATA`
- database: `E:\VLM_DATA\databases\metadata.sqlite`
- active providers on 2026-04-07:
  - face detect: `InsightFaceDetectionProvider`
  - face embed: `LVFaceSubprocessProvider`
  - caption: `Qwen2VLSubprocessProvider`
- pending tasks: `9,529`
- running tasks: `1`
- failed tasks: `46`
- current backlog: caption-only

Important correction:

- several older docs still describe an HTTP caption-server-first runtime
- the live working runtime is currently the external subprocess caption path

Important product gap:

- `backend\app\tasks.py` has handlers for `phash` and video tasks
- `TaskExecutor.run_once()` still does not dispatch them

For detailed status, backlog, dependencies, and readiness gaps, use the dated status doc in `docs/agent-memory/`.
