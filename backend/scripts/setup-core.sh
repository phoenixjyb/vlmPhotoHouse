#!/usr/bin/env bash
set -euo pipefail
python=${PYTHON:-python3}
if [ ! -d .venv ]; then
  "$python" -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements-core.txt
echo 'Core environment ready.'
