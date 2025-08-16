# Operations Runbook

This runbook covers daily operations for the Docker Compose deployment.

## Start/Stop
```bash
cd deploy
# Start
docker compose up -d
# Stop
docker compose down
```

## Environment
- `.env` in `deploy/` controls mounts, DB, and worker/GPU settings.
- Key variables:
  - `PHOTOS_PATH`, `DERIVED_PATH` (host paths mounted in containers)
  - `DATABASE_URL` (default SQLite in `api-data` volume)
  - `WORKER_CONCURRENCY`, `ENABLE_INLINE_WORKER`
  - `API_GPU` (select GPU index)

## Health checks
- API docs: http://localhost:8000/docs
- Nginx root: http://localhost/

## Logs
```bash
# Tail logs
cd deploy
docker compose logs -f api
```

## Backups
- Photos/Derived: backup the host directories (e.g., file-level snapshots, mirror, or cloud backup).
- Database (SQLite): backup the `api-data` volume content.
  - Inspect: `docker compose run --rm api bash -lc 'ls -l /data'`
  - Copy out: `docker cp $(docker compose ps -q api):/data/app.sqlite ./app.sqlite.bak`
  - For consistent backups, stop the `api` service first or use application-level export.

## Troubleshooting
- No GPUs visible:
  - Confirm NVIDIA drivers and Docker Desktop GPU support in WSL.
  - Set `API_GPU=all` or verify GPU index.
- Permission issues on mounts:
  - Ensure the host folders exist and are shared with Docker Desktop.
  - Check WSL permissions (`ls -la /mnt/e/...`).
- 502 from proxy:
  - Ensure `api` is healthy: `docker compose ps`, `docker compose logs -f api`.
- App fails to start migrations:
  - `AUTO_MIGRATE=true` is set; inspect logs for DB path and permissions.

## Test suite note
- A global skip exists for local/dev runs:
  - Set `SKIP_ALL_TESTS=true` to skip all tests (useful during heavy iteration).
  - Ensure CI leaves this unset.
