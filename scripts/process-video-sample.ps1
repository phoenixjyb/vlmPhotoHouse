param(
    [string]$SourceRoot = 'E:\01_INCOMING\Jane',
    [bool]$SceneDetect = $true,
    [int]$WorkerSteps = 400
)

$ErrorActionPreference = 'Stop'

Write-Host "SourceRoot: $SourceRoot"
if (-not (Test-Path -LiteralPath $SourceRoot)) {
    Write-Error "SourceRoot not found: $SourceRoot"
    exit 1
}

# Pick a random video
$exts = @('.mp4','.mov','.mkv','.avi','.m4v')
$files = Get-ChildItem -Path $SourceRoot -Recurse -File | Where-Object { $exts -contains $_.Extension.ToLower() }
if (-not $files) {
    Write-Error "No video files under $SourceRoot"
    exit 2
}
$pick = $files | Get-Random -Count 1
Write-Host "Picked: $($pick.FullName)"

# Stage into workspace
$ws = (Get-Location).Path
$sampleDir = Join-Path $ws 'sample_video'
$derivedDir = Join-Path $ws 'derived'
New-Item -ItemType Directory -Force -Path $sampleDir | Out-Null
New-Item -ItemType Directory -Force -Path $derivedDir | Out-Null
Copy-Item -LiteralPath $pick.FullName -Destination $sampleDir -Force

# Env vars for the backend
$env:VIDEO_ENABLED = 'true'
if ($SceneDetect) { $env:VIDEO_SCENE_DETECT = 'true' }
$env:ORIGINALS_PATH = $sampleDir
$env:DERIVED_PATH = $derivedDir
$env:AUTO_MIGRATE = 'false'
$env:ENABLE_INLINE_WORKER = 'false'

# Ingest via CLI
Push-Location 'backend'
try {
    # Resolve Python executable (prefer repo .venv, fallback to PATH)
    $pyExe = "..\.venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $pyExe)) { $pyExe = 'python' }

    & $pyExe -m app.cli ingest-scan '..\sample_video'
    if ($LASTEXITCODE -ne 0) { throw "ingest-scan failed with exit code $LASTEXITCODE" }

    # Create a temporary worker script to avoid quoting issues
    $py = @"
from app.main import reinit_executor_for_tests, executor
reinit_executor_for_tests()
import time
steps = $WorkerSteps
for _ in range(steps):
    worked = executor.run_once()
    if not worked:
        time.sleep(0.02)
print('worker-finished')
"@
    $tmpPy = Join-Path (Get-Location) 'run_worker_tmp.py'
    Set-Content -LiteralPath $tmpPy -Value $py -NoNewline -Encoding UTF8
    & $pyExe $tmpPy
    Remove-Item -LiteralPath $tmpPy -Force -ErrorAction SilentlyContinue
}
finally {
    Pop-Location
}

Write-Host "Done. Staged file: $($pick.Name)"
