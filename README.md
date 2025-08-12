# VLM Photo Engine

Local-first AI photo engine. See docs/ for Rev-B specs.

## Environment / Python Version

Baseline Python: 3.12.x (pinned for now — 3.13 wheels for some deps like faiss / torch may lag or differ).

Use a virtual environment on every platform to avoid global package drift:

Windows (PowerShell):
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

macOS / Linux:
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Optional exact lock install (repro builds):
```
pip install -r backend/requirements-lock.txt
```

Regenerate lock after intentional upgrades:
```
pip freeze > backend/requirements-lock.txt
```

Future: migrate to `pyproject.toml` + pip-tools for deterministic hashes.

## Single-machine (P1) quickstart

This profile runs everything on one machine via Docker Compose. It mounts your code and data directories and exposes the API on port 8000.

Prereqs:
- Docker Desktop (Windows/macOS) or Docker Engine (Linux)
- Git clone of this repo

Steps:
1) Configure env
	- Edit `deploy/.env.p1.sample` (it will be loaded by Compose). Adjust paths or settings as needed.

2) Create local data folders (host paths mounted into the container)
	- `deploy/data/originals`
	- `deploy/data/derived`

3) Start the stack
	- From the `deploy/` folder, run Docker Compose with the P1 file:
	  - Windows PowerShell/macOS/Linux: `docker compose -f compose.p1.yml up --build`

4) Use it
	- API: http://localhost:8000
	- Docs: http://localhost:8000/docs
	- Metrics: http://localhost:8000/metrics.prom

Notes:
- The Compose file mounts `../backend` into the container at `/app` and runs `uvicorn app.main:app`.
- You can copy `deploy/.env.p1.sample` to `deploy/.env.p1` for local overrides; if you do, update `env_file` in `deploy/compose.p1.yml` to point at `.env.p1`.
- For GPU on Linux with NVIDIA Container Toolkit, see the commented `deploy.resources` section in `deploy/compose.p1.yml`.
