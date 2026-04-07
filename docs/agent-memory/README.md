# Agent Memory Pack

This folder is the shared onboarding pack for future work on `vlmPhotoHouse`.

Use it as the common source of truth for Codex, Claude, Copilot, and any other coding agent. It is intentionally split into:

- `PROJECT_TRUTH.md`: stable architecture and runtime truths.
- `STATUS_AND_PRODUCT_READINESS_2026-04-07.md`: dated operational snapshot and backlog.
- `CODEX.md`: Codex-oriented working notes.
- `CLAUDE.md`: Claude-oriented working notes.
- `COPILOT.md`: Copilot-oriented working notes.

Read order for a new agent:

1. `PROJECT_TRUTH.md`
2. `STATUS_AND_PRODUCT_READINESS_2026-04-07.md`
3. Your agent-specific file in this folder

What this pack fixes:

- Root docs still contain stale references to an HTTP caption-server-first runtime.
- The real working stack now uses the repo-root Python env plus external subprocess integrations for captioning and face embedding.
- The live backlog on 2026-04-07 is caption-only; face work for the current corpus is effectively caught up.

Refresh policy:

- Keep `PROJECT_TRUTH.md` mostly stable and only change it when the architecture or canonical runtime changes.
- Add or replace dated status files when queue counts, readiness, or operational risks materially change.
