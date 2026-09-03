# Agent Entry

Use the shared memory pack:

1. `docs/agent-memory/PROJECT_TRUTH.md`
2. `docs/agent-memory/STATUS_AND_PRODUCT_READINESS_2026-04-07.md`

Agent-specific notes:

- Codex: `docs/agent-memory/CODEX.md`
- Claude: `docs/agent-memory/CLAUDE.md`
- Copilot: `docs/agent-memory/COPILOT.md`

Critical truths:

- use repo-root `.venv` for app/runtime work
- do not assume the old HTTP caption-server path is the live production path
- verify live state against `http://127.0.0.1:8002/health`
