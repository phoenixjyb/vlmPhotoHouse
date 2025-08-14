#!/usr/bin/env bash
set -euo pipefail
python=${PYTHON:-python3}
if [ ! -d .venv ]; then
  "$python" -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements-core.txt
# GPU extras: allow override of torch index (e.g. export TORCH_INDEX)
if [ -n "${TORCH_INDEX:-}" ]; then
  pip install --index-url "$TORCH_INDEX" torch torchvision
fi
pip install -r backend/requirements-ml.txt
echo 'Core + ML environment ready.'
