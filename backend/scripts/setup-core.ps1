param(
  [string]$Python = "python"
)
if (-not (Test-Path .venv)) {
  & $Python -m venv .venv
}
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements-core.txt
Write-Host 'Core environment ready.'
