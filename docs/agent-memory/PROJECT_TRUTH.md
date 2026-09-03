# Project Truth

Last verified: 2026-04-07

## Purpose

`vlmPhotoHouse` is a local-first photo and video intelligence system for a personal media library on Drive E.

Its core product goals are:

- ingest originals from `E:\01_INCOMING`
- extract metadata and GPS
- create image and video embeddings for search
- detect faces, embed faces, and support person assignment
- generate captions and derive tags
- expose a local web UI and API for browse, search, people, tasks, and admin flows

This repo is the product surface and orchestration layer. It is not the whole model stack by itself.

## Multi-Repo Runtime

The working stack under `C:\Users\yanbo\wSpace\vlm-photo-engine` is:

1. `vlmPhotoHouse`
   - API, inline worker, SQLite DB, UI, CLI, queue orchestration
2. `LVFace`
   - external face embedding runtime used by subprocess provider
3. `vlmCaptionModels`
   - external caption-model repo used by subprocess caption provider
4. `llmytranslate`
   - optional voice runtime
5. `vlmPhotoHouse\rampp`
   - optional in-repo image-tag service module

## Canonical Data Locations

- originals: `E:\01_INCOMING`
- data root: `E:\VLM_DATA`
- database: `E:\VLM_DATA\databases\metadata.sqlite`
- derived outputs: `E:\VLM_DATA\derived`

Do not migrate active data to Drive C unless the user explicitly asks for that.

## Real Runtime Path

The production-like path is:

1. ingest with `python -m app.cli ingest-scan E:\01_INCOMING`
2. write assets and tasks into SQLite
3. run the FastAPI app on `http://127.0.0.1:8002`
4. let the inline worker drain the queue

The web UI is served from:

- `http://127.0.0.1:8002/ui`

Important correction:

- The current working runtime is not primarily the old HTTP caption-service flow documented in several legacy docs.
- The working caption path now resolves to `Qwen2VLSubprocessProvider` when `CAPTION_EXTERNAL_DIR` is configured.
- `scripts\start-dev-multiproc.ps1` sets caption env for the backend, but its caption pane only activates the caption env; it does not actually start `caption_server.py`.

## Current Live Provider Truth

Verified from the running `/health` endpoint on 2026-04-07:

- face detection: `InsightFaceDetectionProvider`
- face embedding: `LVFaceSubprocessProvider`
- captioning: `Qwen2VLSubprocessProvider`
- worker mode: inline worker enabled inside the API process

Important nuance:

- `/health` currently reports `device: cpu` for face and caption settings.
- That reflects backend process settings, not necessarily the accelerator actually used inside external subprocess repos.
- Do not infer true GPU usage from that field alone.

## Python Environments

Use these exact environments:

- app runtime: `vlmPhotoHouse\.venv\Scripts\python.exe`
- LVFace runtime: `LVFace\.venv\Scripts\python.exe`
- caption-model runtime: `vlmCaptionModels\.venv\Scripts\python.exe`

Do not use `vlmPhotoHouse\backend\.venv` for real runtime work. It is not the working production-like env and does not carry the full ML stack.

Verified versions:

- app env: Python `3.12.10`
- LVFace env: Python `3.11.9`
- caption env: Python `3.13.5`

## Key Dependencies

App-side Python requirements are tracked in `backend\requirements-*.txt`. The working stack depends on:

- FastAPI, Uvicorn, SQLAlchemy, Pydantic, Typer
- Pillow, ExifRead, ImageHash
- NumPy, sentence-transformers, open-clip, transformers
- torch and torchvision in the app env
- insightface for face detection in the app env
- onnxruntime-gpu in LVFace env
- transformers, torch, and bitsandbytes in `vlmCaptionModels`

Host/runtime dependencies also matter:

- NVIDIA drivers and CUDA-compatible wheels
- `ffmpeg` and `ffprobe` on PATH for video probing and frame extraction
- `curl --noproxy '*'` for localhost checks on this machine because Clash/proxy settings can intercept localhost

## Environment and Config Truth

`backend\app\config.py` now loads repo-local `.env` files from both repo root and `backend\` before building settings.

That change is useful for direct CLI usage, but there is still a sharp edge:

- repo-local `.env` currently defaults `CAPTION_PROVIDER=blip2`
- the launcher overrides runtime env to the real stack values
- direct CLI work can therefore see different defaults than the live API if you do not export the intended env first

Treat launcher env and live `/health` as the operational truth, not just `.env` defaults.

## Queue and Processing Model

Ingest creates tasks for the pipeline. The main active task families are:

- `embed`
- `thumb`
- `caption`
- `face`
- `face_embed`
- `image_tag`
- person-label propagation tasks

There are also video and phash tasks in the codebase.

Worker dispatch now covers the implemented `phash` and video task families,
including segment embeddings. Unknown task types fail explicitly instead of
being marked finished without a handler.

## Optional Subsystems

These are not required for the core ingest -> embed -> face -> caption flow:

- `rampp` image tagging on port `8112`
- `llmytranslate` voice service on port `8001`

The main product can operate without them, but docs and launchers still assume them in places.

## Files That Matter Most

- `backend\app\main.py`
- `backend\app\cli.py`
- `backend\app\tasks.py`
- `backend\app\config.py`
- `backend\app\caption_service.py`
- `backend\app\caption_subprocess.py`
- `backend\app\face_detection_service.py`
- `backend\app\face_embedding_service.py`
- `backend\app\lvface_subprocess.py`
- `scripts\start-dev-multiproc.ps1`

## Operational Truths for Future Agents

- Use repo-root `.venv` for app commands.
- Use `curl.exe --noproxy *` when checking localhost endpoints on this machine.
- Treat stale `running` tasks as repair work after an unclean shutdown.
- Prefer API and CLI workflows over direct DB mutation unless doing explicit repair.
- Keep Drive E as the active storage root.
- Assume README-level docs may be stale until confirmed against code, launcher, DB, and `/health`.
