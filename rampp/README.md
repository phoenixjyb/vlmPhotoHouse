# RAM++ Tag Service Scaffold (Windows / Quadro P2000)

This folder provides a Windows-friendly local image-tag service endpoint for `vlmPhotoHouse`.

## What is included

- `service.py`: FastAPI service exposing:
  - `GET /health`
  - `POST /tag` (multipart image upload, returns tag list)
- `requirements.txt`: minimal runtime dependencies for the service shell.

## Modes

The service supports two modes:

1. `RAMPP_MODE=stub` (default)  
   Returns lightweight heuristic tags to validate end-to-end wiring.

2. `RAMPP_MODE=script`  
   Calls an external script (`RAMPP_TAG_SCRIPT`) that should run real RAM++ inference and print JSON:

```json
{
  "tags": [
    {"name": "stroller", "score": 0.92},
    {"name": "outdoor path", "score": 0.77}
  ]
}
```

## Windows setup (recommended for Quadro P2000)

From this folder:

```powershell
.\setup-venv-rampp.ps1
```

Run service:

```powershell
.\.venv-rampp\Scripts\python.exe -m uvicorn service:app --host 127.0.0.1 --port 8112 --reload
```

Optional full RAM++ install step (Torch + RAM package):

```powershell
.\install-rampp-p2000.ps1
```

This script also installs `requirements-rampp.txt` if present.

Quick check:

```powershell
.\.venv-rampp\Scripts\python.exe -c "import importlib.util as u; print('torch', bool(u.find_spec('torch')), 'ram', bool(u.find_spec('ram')))"
```

## Third-party components for real RAM++ path

For real inference on P2000, install in the RAM++ environment (outside this scaffold service):

- CUDA-enabled PyTorch build compatible with your installed NVIDIA driver.
- Official RAM/RAM++ inference code (cloned repo or internal mirror).
- Required model weights/checkpoints.

Then provide:

- `RAMPP_MODE=script`
- `RAMPP_TAG_SCRIPT=<path to your RAM++ adapter script>` (default: `adapter_rampp.py`)
- `RAMPP_PYTHON_EXE=<python.exe of your RAM++ environment>` (default: `.venv-rampp\Scripts\python.exe`)
- `RAMPP_MODEL_NAME=ram-plus`
- `RAMPP_CUDA_DEVICE=1` (PyTorch index for P2000 on this host)
- `RAMPP_CHECKPOINT=<absolute path to RAM++ checkpoint>`
- `RAMPP_ALLOW_STUB_FALLBACK=true` keeps service usable before full RAM++ deps are ready

## Notes

- The backend calls this service through `IMAGE_TAG_SERVICE_URL` (default `http://127.0.0.1:8112`).
- Tag source is persisted to DB as `img` (or merged into `cap+img` when applicable).
- `adapter_rampp.py` is the default script-mode adapter and expects a working RAM package + checkpoint.
