# VLM Photo Engine

Local-first AI photo engine. See docs/ for Rev-B specs.

## Deployment (Hybrid Workstation)
See `docs/deployment.md` for Docker Compose on Windows + WSL2 with NVIDIA GPUs.

## Operations
Runbook in `docs/operations.md`. Security notes in `docs/security.md`.

## Tests
To skip all tests locally during fast iteration, set `SKIP_ALL_TESTS=true` (documented in operations).

## Development

- macOS (fast): builds only core dependencies. Heavy ML packages (torch, faiss, open-clip, sentence-transformers) are deferred.
- GPU/WSL2: enable heavy ML packages for full functionality.

### Environment Matrix

| Platform | Intent | Install | Lock File |
|----------|--------|---------|-----------|
| macOS / lightweight | Core only (no GPU) | `pip install -r backend/requirements-core.txt` | `backend/requirements-lock-core.txt` (optional exact) |
| Windows / Linux (GPU) | Core + ML | `pip install -r backend/requirements-core.txt && pip install -r backend/requirements-ml.txt` | `backend/requirements-lock-ml.txt` (full superset) |

Generate / refresh locks after intentional upgrades:
```
pip freeze > backend/requirements-lock-core.txt        # in a core-only venv
pip freeze > backend/requirements-lock-ml.txt          # in a full (core+ml) venv
```
Use the appropriate lock to reproduce an environment:
```
pip install -r backend/requirements-lock-core.txt   # mac
pip install -r backend/requirements-lock-ml.txt     # gpu
```

Scripts (after commit) will live in `backend/scripts/`:
- `setup-core.sh` / `setup-core.ps1`
- `setup-ml.sh` / `setup-ml.ps1`

These automate venv creation, pip upgrade, and installs.

Steps:

1. Copy `deploy/env.sample` to `deploy/.env` and adjust paths. On macOS keep `INCLUDE_ML=false`.
2. From the `deploy/` folder:
	 - Build and start API:
		 - `docker compose build api`
		 - `docker compose up -d`
	 - GPU/WSL2 (optional): set `INCLUDE_ML=true` and use the GPU override file:
		 - `export INCLUDE_ML=true`
		 - `docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile vlm up -d`

Tip: If Docker hangs or errors with unexpected EOF on macOS/WSL2, a VPN/proxy (e.g., Clash) may be interfering. Disable it or exclude local Docker traffic, clear Docker Desktop proxy settings, and restart Docker.
