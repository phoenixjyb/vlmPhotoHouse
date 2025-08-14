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

### Face Embedding / Detection Providers

Pipeline components are pluggable and selected via environment variables (see also `app/face_embedding_service.py` and `app/face_detection_service.py`).

Providers:

| Purpose | Provider | Env Value | Dependencies | Notes |
|---------|----------|-----------|--------------|-------|
| Embedding | Stub (deterministic hash) | `stub` | none | Fast, used for tests / dev by default |
| Embedding | Facenet (InceptionResnetV1) | `facenet` | `facenet-pytorch`, `torch`, `torchvision` | 512-D, classic baseline |
| Embedding | LVFace (ONNX) | `lvface` | `onnxruntime` (and CUDA variant if GPU) | Load custom ONNX model path (see `LVFACE_MODEL_PATH`) |
| Embedding | Insight (ArcFace) | `insight` | `insightface`, `onnxruntime` | Optional advanced model (kept as fallback) |
| Detection | Stub (random boxes) | `stub` | none | Non-deterministic; for quick UI smoke |
| Detection | MTCNN (facenet-pytorch) | `mtcnn` | `facenet-pytorch`, `torch`, `torchvision` | Multi-face detection |

Key Environment Variables:

```
FACE_EMBED_PROVIDER=stub|facenet|lvface|insight|auto
FACE_DETECT_PROVIDER=stub|mtcnn|auto
EMBED_DEVICE=cpu|cuda
LVFACE_MODEL_PATH=./models/lvface.onnx  # path to ONNX file when using lvface
FORCE_REAL_FACE_PROVIDER=1  # allow real providers during tests (default tests force stub)
```

Automatic selection (`FACE_EMBED_PROVIDER=auto`) tries `insight`, `facenet`, then falls back to `stub`. Set explicit provider for predictable deployments.

GPU Notes:

1. Install CUDA-enabled wheels for torch / onnxruntime before enabling `EMBED_DEVICE=cuda`.
2. If CUDA is requested but unavailable, providers log a warning and fall back to CPU.
3. LVFace uses ONNX Runtime provider order: CUDAExecutionProvider (if present) then CPUExecutionProvider.

Testing:

The deterministic stub test (`test_face_embedding_stub.py`) always uses `stub` unless `FORCE_REAL_FACE_PROVIDER=1`.

Example (Facenet GPU run):

```
pip install facenet-pytorch torch torchvision --extra-index-url https://download.pytorch.org/whl/cu121
export FACE_EMBED_PROVIDER=facenet EMBED_DEVICE=cuda FACE_DETECT_PROVIDER=mtcnn
python -m backend.app.cli embed-dataset  # example future CLI
```

Example (LVFace ONNX):

```
pip install onnxruntime-gpu  # or onnxruntime for CPU
export FACE_EMBED_PROVIDER=lvface LVFACE_MODEL_PATH=/models/lvface.onnx EMBED_DEVICE=cuda FACE_DETECT_PROVIDER=mtcnn
```

