# Deployment: Hybrid Workstation (WSL2 + Docker Desktop + NVIDIA)

This guide sets up the backend via Docker Compose on a Windows workstation using WSL2 with NVIDIA GPU support, matching the "Hybrid Workstation + Dual-GPU NAS" layout.

## Prerequisites
- Windows 11 with WSL2 and Ubuntu (or similar)
- Docker Desktop with WSL integration enabled
- NVIDIA GPU drivers + NVIDIA Container Toolkit (GPU support in Docker Desktop)
- E: drive (or equivalent) containing photos/datasets, visible in WSL as `/mnt/e`

## Folder layout
- Project repo checked out (this repo)
- Host storage paths (examples for your setup):
  - Photos (NAS/library on E:): `E:\photos` → `/mnt/e/photos` in WSL
  - Derived (fast local on D:): `D:\vlm\derived` → `/mnt/d/vlm/derived`
  - WSL VHDX may live on F:, but mounts are still `/mnt/c|d|e|f/...`

## Configure environment
In `deploy/`, copy `env.sample` to `.env` and edit paths to match your host:

```
PHOTOS_PATH=/mnt/e/photos
DERIVED_PATH=/mnt/d/vlm/derived
DATABASE_URL=sqlite:////data/app.sqlite
WORKER_CONCURRENCY=1
ENABLE_INLINE_WORKER=true
API_GPU=1  # Prefer RTX 3090 (usually index 1) for heavy inference; verify with nvidia-smi
```

Notes:
- The compose file mounts `PHOTOS_PATH` at `/photos` and `DERIVED_PATH` at `/derived`.
- `DATABASE_URL` defaults to a SQLite DB persisted in the `api-data` volume; you can switch to Postgres later.
- GPU selection: the container requests all GPUs and selects the index via `NVIDIA_VISIBLE_DEVICES` (driven by `API_GPU`).

## Start services
From the repo root:

### macOS (CPU-only, core-only deps)
```bash
cd deploy
cp env.sample .env  # if not yet created, then edit .env
# Keep INCLUDE_ML=false for fast builds on mac
docker compose build api
docker compose up -d
```

### Windows/WSL2 with GPU (enable heavy ML deps)
```bash
cd deploy
cp env.sample .env  # if not yet created, then edit .env
export INCLUDE_ML=true
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile vlm up -d
```

Services:
- `api` (FastAPI backend) → http://localhost:8000 (direct) via uvicorn
- `proxy` (nginx) → http://localhost/ (for future multi-service fronting)
- `vlm` (VLM server) → optional profile. Use a real image/command. Start with:
  - `docker compose --profile vlm up -d` (CPU-only)
  - `docker compose --profile vlm -f docker-compose.yml -f docker-compose.gpu.yml up -d` (GPU)
  - Endpoint: http://localhost:7860 (direct) or http://localhost/vlm/

## Health and verification
- API docs: http://localhost:8000/docs
- Through proxy: http://localhost/
- Check container logs:
  - `docker compose logs -f api`
  - `docker compose logs -f proxy`

## Docker + VPN note (macOS/WSL2)
Some VPNs or local proxies (e.g., Clash/ClashX/Clash Verge) can break Docker networking or container startup with errors like unexpected EOF or containers hanging. If you see issues:
- Temporarily disable the VPN or set it to bypass Docker local traffic.
- In Docker Desktop Settings, clear HTTP/HTTPS proxy and add No Proxy for 127.0.0.1, localhost, docker.internal, host.docker.internal.
- Restart Docker Desktop after changes.

## WSL2 + GPU tips
- Ensure Docker Desktop shows GPU support enabled for your WSL distro.
- If the container reports no GPUs, verify:
  - NVIDIA drivers installed on Windows
  - Docker Desktop > Settings > Resources > WSL Integration > Enable GPU support
  - Try setting `API_GPU=all` to expose all GPUs to the container
  - Ensure `INCLUDE_ML=true` before building so torch/faiss install
  - Verify GPU indices with `docker compose exec api nvidia-smi` and adjust `API_GPU`
  - Ensure you included the GPU override file with `-f docker-compose.gpu.yml`

## Stopping and cleanup
```bash
cd deploy
docker compose down   # stop
# To remove volumes (including SQLite DB):
docker compose down -v
```

## Next steps
- Add a separate VLM service that pins to GPU 1 for batch workloads.
- Move to Postgres for production DB requirements.
- Extend nginx config for additional services (e.g., Immich) if co-located.
