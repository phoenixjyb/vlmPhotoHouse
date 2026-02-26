param(
    [string]$VenvPath = ".venv-rampp",
    [string]$Wheelhouse = "",
    [string]$TorchIndexUrl = "https://download.pytorch.org/whl/cu121",
    [string]$RamRepoPath = "",
    [string]$RamPackageSpec = "git+https://github.com/xinyu1205/recognize-anything.git",
    [switch]$SkipTorch,
    [switch]$SkipRamPackage
)

$ErrorActionPreference = "Stop"

$venvPy = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
    throw "venv python not found: $venvPy. Run setup-venv-rampp.ps1 first."
}

Write-Host "Using venv: $venvPy" -ForegroundColor Cyan
& $venvPy -m pip install --upgrade pip setuptools wheel
if (Test-Path -LiteralPath ".\requirements-rampp.txt") {
    & $venvPy -m pip install -r ".\requirements-rampp.txt"
}

if (-not $SkipTorch) {
    if ($Wheelhouse -and (Test-Path -LiteralPath $Wheelhouse)) {
        Write-Host "Installing torch from local wheelhouse: $Wheelhouse" -ForegroundColor Yellow
        & $venvPy -m pip install --no-index --find-links "$Wheelhouse" torch torchvision torchaudio
    } else {
        Write-Host "Installing torch from index: $TorchIndexUrl" -ForegroundColor Yellow
        & $venvPy -m pip install torch torchvision torchaudio --index-url "$TorchIndexUrl"
    }
}

if (-not $SkipRamPackage) {
    if ($RamRepoPath -and (Test-Path -LiteralPath $RamRepoPath)) {
        Write-Host "Installing RAM++ from local repo path: $RamRepoPath" -ForegroundColor Yellow
        & $venvPy -m pip install -e "$RamRepoPath"
    } else {
        Write-Host "Installing RAM++ package spec: $RamPackageSpec" -ForegroundColor Yellow
        & $venvPy -m pip install "$RamPackageSpec"
    }
}

Write-Host "RAM++ install step complete." -ForegroundColor Green
Write-Host "Next: set RAMPP_MODE=script and RAMPP_TAG_SCRIPT to adapter_rampp.py." -ForegroundColor Green
