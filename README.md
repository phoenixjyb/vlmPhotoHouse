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
