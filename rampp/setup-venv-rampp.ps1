param(
    [string]$PythonVersion = "3.10",
    [string]$PythonExe = "",
    [string]$VenvPath = ".venv-rampp"
)

$ErrorActionPreference = "Stop"

function Resolve-PythonExe {
    param([string]$Version, [string]$ExplicitExe)
    if ($ExplicitExe) { return $ExplicitExe }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $probe = py -$Version -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $probe) { return $probe.Trim() }
        } catch {}
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return (Get-Command python).Source
    }
    throw "No Python executable found."
}

$resolvedPy = Resolve-PythonExe -Version $PythonVersion -ExplicitExe $PythonExe
Write-Host "Using Python: $resolvedPy" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath (Join-Path $VenvPath "Scripts\python.exe"))) {
    & $resolvedPy -m venv $VenvPath
}

$venvPy = Join-Path $VenvPath "Scripts\python.exe"
& $venvPy -m pip install --upgrade pip setuptools wheel
& $venvPy -m pip install -r ".\requirements.txt"

Write-Host "venv-rampp ready: $venvPy" -ForegroundColor Green
