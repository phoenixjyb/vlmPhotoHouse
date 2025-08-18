# WSL setup guide (run backend from Linux instead of Windows)

This guide helps you run the backend inside WSL2 (Ubuntu) while keeping your project structure intact. It covers CPU/GPU setup, external model repos, validations, and an optional tmux-based launcher similar to the Windows multi-pane experience.

## Goals
- Stand up the backend in WSL2 (Ubuntu) with CPU or GPU.
- Reuse or mirror LVFace and caption external repos.
- Keep fast I/O by using the WSL filesystem.
- Validate with the existing CLI and run the API.

## 1) Prerequisites
- Windows 10/11 with WSL2 and a distro (Ubuntu 22.04+ recommended).
- Windows Terminal installed (optional, but handy).
- For GPU: recent NVIDIA driver with WSL support; `nvidia-smi` should work inside WSL.

## 2) Repo and models layout (performance tip)
Put hot files on the WSL filesystem for best performance:

- `~/projects/vlmPhotoHouse` (this repo)
- `~/models/LVFace` (external LVFace repo + models)
- `~/models/vlmCaptionModels` (external caption repo + models)

It also works from `/mnt/c/...` but can be slower for heavy I/O.

## 3) Python and venv in WSL
Install Python toolchain:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git
```

Create venv and install dependencies:

```bash
cd ~/projects/vlmPhotoHouse
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements-core.txt
# Full ML stack (CPU ok)
pip install -r backend/requirements-ml.txt
```

GPU (optional, recommended on RTX 3090):

```bash
# Install CUDA-enabled torch for Linux (match the recommended index URL)
pip install --index-url https://download.pytorch.org/whl/cu121 torch torchvision
# ONNX Runtime GPU
pip install onnxruntime-gpu
# If using Facenet
pip install facenet-pytorch
```

Notes:
- Python 3.10 or 3.11 on Linux tends to have the best prebuilt wheel coverage.

## 4) External repos in WSL
Mirror your Windows folders into WSL paths (recommended):

LVFace (external):

```bash
mkdir -p ~/models/LVFace
# Place models/*.onnx here (e.g., LVFace-B_Glint360K.onnx)
cd ~/models/LVFace
python3 -m venv .venv
source .venv/bin/activate
# Install what the LVFace repo needs (if applicable):
# pip install -r requirements.txt
```

Captions (external):

```bash
mkdir -p ~/models/vlmCaptionModels
# Ensure inference_backend.py and inference.py exist here
cd ~/models/vlmCaptionModels
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Tip: You can keep these on `/mnt/c` if needed, but expect slower I/O.

## 5) Environment variables
Use Linux paths in WSL:

```bash
export LVFACE_EXTERNAL_DIR=~/models/LVFace
export LVFACE_MODEL_NAME=LVFace-B_Glint360K.onnx
export CAPTION_EXTERNAL_DIR=~/models/vlmCaptionModels
export CAPTION_PROVIDER=vitgpt2   # or blip2 | qwen2.5-vl | llava | stub
export CAPTION_DEVICE=cuda        # or cpu
export FACE_EMBED_PROVIDER=lvface # or facenet | insight | stub | auto
export EMBED_DEVICE=cuda          # or cpu
```

Optional:

```bash
export ENABLE_INLINE_WORKER=true
export ORIGINALS_PATH=./originals
export DERIVED_PATH=./derived
export DATABASE_URL=sqlite:///./metadata.sqlite
```

## 6) Validate and warm up
From repo root:

```bash
source .venv/bin/activate
cd backend
python -m app.cli validate-lvface
python -m app.cli validate-caption
python -m app.cli warmup
```

You should see provider OK messages and basic timings. If CUDA isn’t available, providers fall back to CPU with a warning.

## 7) Run the API

```bash
source .venv/bin/activate
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open http://127.0.0.1:8000/ in Windows; WSL loopback works.

## 8) Optional: tmux-based multi-pane launcher (WSL)
Install tmux:

```bash
sudo apt install -y tmux
```

Use the provided script to mimic the Windows multi-pane workflow:

```bash
# From repo root
bash scripts/start-dev-tmux.sh \
  --preset LowVRAM \
  --lvface-dir "$HOME/models/LVFace" \
  --caption-dir "$HOME/models/vlmCaptionModels"
```

- LowVRAM preset: facenet + vitgpt2, GPU on (if available)
- RTX3090 preset: lvface + qwen2.5-vl, GPU on
- Override any option explicitly: `--face-provider`, `--caption-provider`, `--gpu` / `--no-gpu`, `--api-port`.

## 9) Profiles (WSL)
LowVRAM (P2000-like):

```bash
export FACE_EMBED_PROVIDER=facenet
export CAPTION_PROVIDER=vitgpt2
export EMBED_DEVICE=cuda
export CAPTION_DEVICE=cuda
```

RTX3090:

```bash
export FACE_EMBED_PROVIDER=lvface
export CAPTION_PROVIDER=qwen2.5-vl
export EMBED_DEVICE=cuda
export CAPTION_DEVICE=cuda
```

Re-run validate and warmup after switching.

## 10) Troubleshooting
- facenet-pytorch: ensure torch/torchvision versions match and suit your CUDA.
- onnxruntime-gpu: if CUDA provider isn’t detected, it falls back to CPU.
- Slow I/O: avoid `/mnt/c` for DB, derived/, and models/ if possible.
- External caption subprocess: activate its venv and run `python inference_backend.py --help` to verify.

## 11) Quick checklist
- [ ] Repo + models on WSL filesystem (or accept `/mnt/c` slowdown)
- [ ] Venv created, core+ML requirements installed
- [ ] GPU wheels (torch/onnxruntime-gpu) installed if using CUDA
- [ ] External repos present and usable
- [ ] Env vars set
- [ ] validate-lvface, validate-caption, warmup pass
- [ ] API reachable at 127.0.0.1:8000
