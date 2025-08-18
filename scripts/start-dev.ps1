# Starts the API using the repo venv and validates external caption models in a separate venv
# Usage: run from anywhere: powershell -ExecutionPolicy Bypass -File scripts/start-dev.ps1 [-Port 8001] [-Host 127.0.0.1] [-Reload]
param(
  [int]$Port = 8002,
  [string]$Host = '127.0.0.1',
  [switch]$Reload
)

$ErrorActionPreference = 'Stop'

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ERR ] $msg" -ForegroundColor Red }

# Determine repo root (this script lives in scripts/)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

# Load .env if present to pick up CAPTION_EXTERNAL_DIR, etc.
function Import-DotEnv([string]$Path) {
  if (-not (Test-Path $Path)) { return }
  Get-Content -Raw -Path $Path | ForEach-Object {
    $_ -split "`n" | ForEach-Object {
      $line = $_.Trim()
      if (-not $line) { return }
      if ($line.StartsWith('#')) { return }
      $kv = $line -split '=', 2
      if ($kv.Length -eq 2) {
        $name = $kv[0].Trim()
        $val  = $kv[1].Trim()
        # Remove optional surrounding quotes
        if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
          $val = $val.Substring(1, $val.Length-2)
        }
        $env:$name = $val
      }
    }
  }
}

if (Test-Path "$RepoRoot/.env") { Write-Info "Loading .env"; Import-DotEnv "$RepoRoot/.env" }
if (Test-Path "$RepoRoot/.env.caption") { Write-Info "Loading .env.caption"; Import-DotEnv "$RepoRoot/.env.caption" }

# Validate backend venv
$BackendPython = Join-Path $RepoRoot ".venv/Scripts/python.exe"
if (-not (Test-Path $BackendPython)) {
  Write-Err ".venv not found at $BackendPython. Create it and install backend requirements."
  exit 1
}

# Validate external caption models venv if configured
$CaptionDir = $env:CAPTION_EXTERNAL_DIR
if ($CaptionDir) {
  $CaptionPython = Join-Path $CaptionDir ".venv/Scripts/python.exe"
  $InferenceBackend = Join-Path $CaptionDir "inference_backend.py"
  $Inference = Join-Path $CaptionDir "inference.py"
  if (-not (Test-Path $CaptionPython)) { Write-Warn "Caption external python not found: $CaptionPython" }
  if (-not (Test-Path $InferenceBackend) -and -not (Test-Path $Inference)) { Write-Warn "Caption inference script missing in $CaptionDir (expected inference_backend.py or inference.py)" }
  Write-Info "CAPTION_EXTERNAL_DIR=$CaptionDir"
} else {
  Write-Warn "CAPTION_EXTERNAL_DIR not set. Built-in stub/builtin caption providers will be used."
}

# Set API env defaults (can be overridden via .env)
if (-not $env:RUN_MODE) { $env:RUN_MODE = 'api' }
if (-not $env:PYTHONPATH) { $env:PYTHONPATH = (Join-Path $RepoRoot 'backend') }
if (-not $env:VECTOR_INDEX_AUTOLOAD) { $env:VECTOR_INDEX_AUTOLOAD = '1' }
if (-not $env:VECTOR_INDEX_REBUILD_ON_DEMAND_ONLY) { $env:VECTOR_INDEX_REBUILD_ON_DEMAND_ONLY = '0' }
if (-not $env:EMBED_DEVICE) { $env:EMBED_DEVICE = 'cpu' }
if (-not $env:EMBED_MODEL_IMAGE) { $env:EMBED_MODEL_IMAGE = 'clip-ViT-B-32' }
if (-not $env:EMBED_MODEL_TEXT) { $env:EMBED_MODEL_TEXT = 'clip-ViT-B-32' }

Write-Info "Starting API with $BackendPython"
$args = @(
  '-m','uvicorn','app.main:app','--host', $Host,'--port',$Port.ToString()
)
if ($Reload) { $args += '--reload' }

# Launch in foreground to show logs
& $BackendPython @args
