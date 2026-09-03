# Windows launcher quickstart

This guide summarizes the common commands and options for the tmux‑style Windows launcher and related backend CLIs.

## Prereqs

- Windows Terminal installed (for multi‑pane mode).
- Backend venv created at `.venv/` in repo root and dependencies installed:
  - Core: `pip install -r backend/requirements-core.txt`
  - ML (optional): `pip install -r backend/requirements-ml.txt`
- Keep the three stack repositories as siblings under one directory:
  - `<stack-root>\vlmPhotoHouse`
  - `<stack-root>\LVFace` (with `models/*.onnx` and its own `.venv`)
  - `<stack-root>\vlmCaptionModels` (with `.venv`, `inference_backend.py` and models)

The launcher derives sibling repository paths from its own location. Explicit
`-LvfaceDir`, `-CaptionDir`, `-RamppDir`, and `-VoiceDir` arguments still override
the derived paths.

The interactive launcher opens panes for the API, voice ASR, LVFace, and TTS.
Caption inference is invoked by the backend through the configured external
caption repository; there is no separate caption-server pane.

## Read-only preflight

Before the first real launch from a new workspace location, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dev-multiproc.ps1 `
  -Preset RTX3090 `
  -PreflightOnly
```

Preflight reports resolved paths, providers, ports, and storage locations. It
does not stop processes, create directories, move a database, warm models, or
start services. Missing required repositories or the repo-root Python executable
cause a non-zero failure.

## Independent unattended operations

Use separate entry points for the persistent Qwen3-VL label service, durable
API startup, and photo intake. Check them from the Windows checkout before
enabling any operation:

```powershell
# Read-only checks
.\scripts\start-caption-service.ps1 -PreflightOnly
.\scripts\start-photohouse-api.ps1 -PreflightOnly
.\scripts\run-photo-intake.ps1 -PreflightOnly
```

After the preflights pass, the corresponding operations are:

```powershell
# Persistent Qwen3-VL-8B label service; loads once on the RTX 3090
.\scripts\start-caption-service.ps1

# Long-running API plus inline worker; the script remains its foreground owner
.\scripts\start-photohouse-api.ps1

# Health/UI canary with no queue processing and no schema migration
.\scripts\start-photohouse-api.ps1 -DisableInlineWorker -NoAutoMigrate

# One idempotent scan of E:\01_INCOMING
.\scripts\run-photo-intake.ps1
```

Keep these as separate scheduled tasks so a model-load or intake failure cannot
suppress unrelated startup. The scripts derive sibling repositories from the
PhotoHouse checkout, use cross-session locks, and write retained logs under
`E:\VLM_DATA\logs\photohouse`.

The caption launcher loads `models\qwen3-vl-8b-instruct` in 4-bit NF4, pins it
to the RTX 3090, and requires the service to report a loaded Qwen3-VL cache on
that GPU. It uses one inference slot and a shared bilingual prompt covering
subjects, actions, setting, objects, clothing, lighting, composition, readable
text, and detailed phone/device attributes when genuinely visible. Each result
contains a 60-120 word English paragraph followed by a fact-aligned natural
Simplified Chinese paragraph. The prompt also requires neutral person terms,
respectful family-photo wording, and no inferred intent. The PhotoHouse API now
defaults to `CAPTION_PROVIDER=http` at `http://127.0.0.1:8102` and refuses to
start before that caption service is ready.

API startup separately verifies the PhotoHouse health identity, database, and
inline worker before declaring readiness. If port 8002 belongs to an unknown or
unhealthy process, it fails without killing that process.

For a bounded health/UI canary, combine `-DisableInlineWorker` and
`-NoAutoMigrate`. Readiness then requires `worker_enabled=false`; this mode must
not be mistaken for the production queue-draining launcher.

For a fully retained one-sample runtime check, use
`scripts\run-runtime-canary.ps1`. It owns both services in one shell, verifies
the UI and API health, runs one detailed-caption request, compares the database
SHA-256 before and after, stops both exact PIDs, and writes a JSON receipt.

`tools\morning-intake-and-start.ps1` remains only as a compatibility coordinator
for an existing caller: it starts the caption service, runs intake, and then
starts the API with `-Detached`. New automation should use the three independent
scripts. These files do not create or modify Windows scheduled tasks.

## Face embedding model

Keep `LVFace-B_Glint360K.onnx` as the active checkpoint. Its official published
results are stronger than the practical ArcFace/AdaFace alternatives for this
stack. PhotoHouse currently preserves the existing 128-dimensional embedding
space. Moving to LVFace's full 512-dimensional output requires a versioned
re-embed and recluster migration; never mix 128- and 512-dimensional vectors in
the same active person index.

The versioned artifact schema records legacy 128/512-dimensional vectors as
`unknown-legacy` without rewriting their active paths. Landmark-aligned LVFace
512-dimensional vectors can be retained separately with status `shadow` by
`scripts\run-aligned-face-shadow-canary.py`. A shadow artifact is evaluation
evidence only: it does not change a face assignment, person centroid, task, or
the active `face_detections.embedding_path`.

## Quick start (presets)

Run from the repo root (`vlmPhotoHouse`). Use `-UseWindowsTerminal` for panes and `-KillExisting` to reset the session.

Low VRAM preset (Quadro P2000 style): facenet + vitgpt2 on GPU if available

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dev-multiproc.ps1 `
  -Preset LowVRAM `
  -UseWindowsTerminal -KillExisting
```

RTX 3090 preset: LVFace + Qwen3‑VL on GPU

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dev-multiproc.ps1 `
  -Preset RTX3090 `
  -UseWindowsTerminal -KillExisting
```

Presets set defaults; any explicit flag overrides them.

## Common overrides

- Choose providers/devices explicitly:

```powershell
# Example: LVFace + BLIP2, CUDA on, custom port
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dev-multiproc.ps1 `
  -FaceProvider lvface -CaptionProvider blip2 -Gpu -ApiPort 9000 `
  -LvfaceDir "C:\...\LVFace" -CaptionDir "C:\...\vlmCaptionModels" `
  -UseWindowsTerminal -KillExisting
```

- Enable remote UI/voice control over Tailscale:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dev-multiproc.ps1 `
  -Preset RTX3090 `
  -TailscaleAccess `
  -UseWindowsTerminal -KillExisting
```

This sets API bind host to `0.0.0.0`. For remote browser voice capture, publish HTTPS with:

```powershell
tailscale serve --bg --https=443 http://127.0.0.1:8002
```

Then use `https://<this-node>.<tailnet>.ts.net/ui` from the other device.

## Validations and warmup

Run from `backend/` or use the repo `.venv` Python with `-m`:

```powershell
# From repo root
& .\.venv\Scripts\python.exe -m app.cli validate-lvface
& .\.venv\Scripts\python.exe -m app.cli validate-caption
& .\.venv\Scripts\python.exe -m app.cli warmup
```

These commands preload models and run a tiny inference. Non‑critical issues (e.g., CUDA unavailable) fall back to CPU with a warning.

## What the launcher sets

Environment passed to the backend:

- `FACE_EMBED_PROVIDER`: stub|facenet|lvface|insight|auto
- `EMBED_DEVICE`: cpu|cuda
- `LVFACE_EXTERNAL_DIR`, `LVFACE_MODEL_NAME`
- `CAPTION_PROVIDER`: stub|http|blip2|llava|qwen2.5-vl|qwen3-vl|vitgpt2|auto
- `CAPTION_DEVICE`: cpu|cuda
- `CAPTION_EXTERNAL_DIR`, `CAPTION_MODEL` (usually `auto`)

## Troubleshooting

- “CUDA requested … but not available; using CPU”
  - Ensure you installed CUDA‑enabled builds of Torch/ONNX Runtime and have compatible NVIDIA drivers.
  - Otherwise, operation continues on CPU.

- facenet‑pytorch import errors
  - Install into the backend venv: `pip install facenet-pytorch` (on some Python versions, you may need `--no-deps`).
  - The LowVRAM preset selects facenet; switch to LVFace with `-FaceProvider lvface` if preferred.

- Persistent Qwen3-VL service
  - Ensure `CAPTION_EXTERNAL_DIR` has `.venv`, `caption_server.py`, and `models\qwen3-vl-8b-instruct`.
  - Start `scripts\start-caption-service.ps1` before the PhotoHouse API and check port 8102.

## Pane layout

When `-UseWindowsTerminal` is set, the launcher opens one Windows Terminal window with panes:

- API server (uvicorn, reload) on port 8002 (or `-ApiPort`)
- Voice ASR service
- LVFace shell (in its directory, isolated venv activation attempted)
- TTS environment shell

When `-EnableRampp` is set, RAM++ opens in an additional tab.

Use `-KillExisting` to close any previous Windows Terminal instance before launching.
