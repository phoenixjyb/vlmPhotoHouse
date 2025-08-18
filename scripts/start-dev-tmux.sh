#!/usr/bin/env bash
set -euo pipefail

# tmux-based dev launcher for WSL/Linux
# Presets: LowVRAM (facenet + vitgpt2, gpu on), RTX3090 (lvface + qwen2.5-vl, gpu on)

PRESET=""
LVFACE_DIR="${HOME}/models/LVFace"
CAPTION_DIR="${HOME}/models/vlmCaptionModels"
FACE_PROVIDER="lvface"
CAPTION_PROVIDER="blip2"
GPU=0
API_PORT=8000

usage() {
  cat <<EOF
Usage: $0 [options]
  --preset {LowVRAM|RTX3090}
  --lvface-dir PATH
  --caption-dir PATH
  --face-provider NAME
  --caption-provider NAME
  --gpu | --no-gpu
  --api-port PORT

Examples:
  $0 --preset LowVRAM --lvface-dir "$HOME/models/LVFace" --caption-dir "$HOME/models/vlmCaptionModels"
  $0 --face-provider lvface --caption-provider qwen2.5-vl --gpu
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --preset) PRESET="$2"; shift 2;;
    --lvface-dir) LVFACE_DIR="$2"; shift 2;;
    --caption-dir) CAPTION_DIR="$2"; shift 2;;
    --face-provider) FACE_PROVIDER="$2"; shift 2;;
    --caption-provider) CAPTION_PROVIDER="$2"; shift 2;;
    --gpu) GPU=1; shift;;
    --no-gpu) GPU=0; shift;;
    --api-port) API_PORT="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown option: $1"; usage; exit 1;;
  esac
done

# Apply preset defaults
if [[ -n "$PRESET" ]]; then
  case "${PRESET,,}" in
    lowvram)
      FACE_PROVIDER="facenet"
      CAPTION_PROVIDER="vitgpt2"
      GPU=1
      ;;
    rtx3090)
      FACE_PROVIDER="lvface"
      CAPTION_PROVIDER="qwen2.5-vl"
      GPU=1
      ;;
    *)
      echo "Warning: unknown preset '$PRESET' (ignored)" >&2
      ;;
  esac
fi

# Effective devices
if [[ $GPU -eq 1 ]]; then
  EMBED_DEVICE="cuda"
  CAPTION_DEVICE="cuda"
else
  EMBED_DEVICE="cpu"
  CAPTION_DEVICE="cpu"
fi

# Resolve model name from LVFace models dir (pick first .onnx)
LVFACE_MODEL_NAME="LVFace-B_Glint360K.onnx"
if [[ -d "$LVFACE_DIR/models" ]]; then
  first=$(find "$LVFACE_DIR/models" -maxdepth 1 -type f -name '*.onnx' | head -n1 || true)
  if [[ -n "$first" ]]; then
    LVFACE_MODEL_NAME="$(basename "$first")"
  fi
fi

# Backend env
export FACE_EMBED_PROVIDER="$FACE_PROVIDER"
export LVFACE_EXTERNAL_DIR="$LVFACE_DIR"
export LVFACE_MODEL_NAME="$LVFACE_MODEL_NAME"
export CAPTION_PROVIDER="$CAPTION_PROVIDER"
export CAPTION_EXTERNAL_DIR="$CAPTION_DIR"
export CAPTION_MODEL="auto"
export ENABLE_INLINE_WORKER="true"
export EMBED_DEVICE="$EMBED_DEVICE"
export CAPTION_DEVICE="$CAPTION_DEVICE"

BACKEND_ROOT="$(cd "$(dirname "$0")/.." && pwd)/backend"
PY="$(cd "$(dirname "$0")/.." && pwd)/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

echo "Preset: ${PRESET:-none} | face=$FACE_EMBED_PROVIDER | caption=$CAPTION_PROVIDER | gpu=$([[ $GPU -eq 1 ]] && echo on || echo off)"
echo "LVFace: $LVFACE_EXTERNAL_DIR (model: $LVFACE_MODEL_NAME)"
echo "Caption: $CAPTION_EXTERNAL_DIR"
echo "Backend Python: $PY"

pushd "$BACKEND_ROOT" >/dev/null
set +e
$PY -m app.cli validate-lvface || echo "validate-lvface non-zero (continuing)"
$PY -m app.cli validate-caption || echo "validate-caption non-zero (continuing)"
$PY -m app.cli warmup || echo "warmup non-zero (continuing)"
set -e
popd >/dev/null

# Start tmux session with panes
SESSION="vlm-dev"
# Kill existing session
if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
fi

# Create session and first pane (API)
tmux new-session -d -s "$SESSION" "cd '$BACKEND_ROOT' && $PY -m uvicorn app.main:app --host 127.0.0.1 --port $API_PORT --reload"
# Split horizontally for LVFace pane
 tmux split-window -h "cd '$LVFACE_DIR'; if [[ -f .venv/bin/activate ]]; then source .venv/bin/activate; fi; exec bash"
# Split vertically for Caption pane
 tmux split-window -v "cd '$CAPTION_DIR'; if [[ -f .venv/bin/activate ]]; then source .venv/bin/activate; fi; exec bash"
# Select layout and attach
 tmux select-layout tiled
 tmux attach -t "$SESSION"
