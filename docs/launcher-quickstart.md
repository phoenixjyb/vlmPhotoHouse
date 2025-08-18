# Windows launcher quickstart

This guide summarizes the common commands and options for the tmux‑style Windows launcher and related backend CLIs.

## Prereqs

- Windows Terminal installed (for multi‑pane mode).
- Backend venv created at `.venv/` in repo root and dependencies installed:
  - Core: `pip install -r backend/requirements-core.txt`
  - ML (optional): `pip install -r backend/requirements-ml.txt`
- External model folders available:
  - LVFace: `C:\...\LVFace` (with `models/*.onnx` and its own `.venv`)
  - Captions: `C:\...\vlmCaptionModels` (with `.venv`, `inference_backend.py` and models)

Tip: The launcher opens panes for LVFace and Caption so you can activate their venvs and run ad‑hoc tests.

## Quick start (presets)

Run from the repo root (`vlmPhotoHouse`). Use `-UseWindowsTerminal` for panes and `-KillExisting` to reset the session.

Low VRAM preset (Quadro P2000 style): facenet + vitgpt2 on GPU if available

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dev-multiproc.ps1 `
  -Preset LowVRAM `
  -LvfaceDir "C:\Users\<you>\...\LVFace" `
  -CaptionDir "C:\Users\<you>\...\vlmCaptionModels" `
  -UseWindowsTerminal -KillExisting
```

RTX 3090 preset: LVFace + Qwen2.5‑VL on GPU

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dev-multiproc.ps1 `
  -Preset RTX3090 `
  -LvfaceDir "C:\Users\<you>\...\LVFace" `
  -CaptionDir "C:\Users\<you>\...\vlmCaptionModels" `
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
- `CAPTION_PROVIDER`: stub|blip2|llava|qwen2.5-vl|vitgpt2|auto
- `CAPTION_DEVICE`: cpu|cuda
- `CAPTION_EXTERNAL_DIR`, `CAPTION_MODEL` (usually `auto`)

## Troubleshooting

- “CUDA requested … but not available; using CPU”
  - Ensure you installed CUDA‑enabled builds of Torch/ONNX Runtime and have compatible NVIDIA drivers.
  - Otherwise, operation continues on CPU.

- facenet‑pytorch import errors
  - Install into the backend venv: `pip install facenet-pytorch` (on some Python versions, you may need `--no-deps`).
  - The LowVRAM preset selects facenet; switch to LVFace with `-FaceProvider lvface` if preferred.

- External caption subprocess
  - Ensure `CAPTION_EXTERNAL_DIR` has `.venv`, `inference_backend.py`, and model files.
  - The launcher opens a caption pane and activates the venv for manual checks.

## Pane layout

When `-UseWindowsTerminal` is set, the launcher opens one Windows Terminal window with panes:

- API server (uvicorn, reload) on port 8000 (or `-ApiPort`)
- LVFace shell (in its directory, venv activation attempted)
- Caption shell (in its directory, venv activation attempted)

Use `-KillExisting` to close any previous Windows Terminal instance before launching.
