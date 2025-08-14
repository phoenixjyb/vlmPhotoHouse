param(
  [string]$Python = "python",
  [string]$TorchIndex = ""
)
if (-not (Test-Path .venv)) {
  & $Python -m venv .venv
}
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements-core.txt
if ($TorchIndex -ne "") {
  pip install --index-url $TorchIndex torch torchvision
}
pip install -r backend/requirements-ml.txt
Write-Host 'Core + ML environment ready.'
