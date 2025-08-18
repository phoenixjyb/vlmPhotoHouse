param(
    [string]$LvfaceDir = 'C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace',
    [string]$CaptionDir = 'C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels',
    [string]$LvfaceModelName = '',
    [int]$ApiPort = 8000,
    [switch]$UseWindowsTerminal,
    [switch]$KillExisting
)

$ErrorActionPreference = 'Stop'

function Resolve-BackendPython {
    $backend = Join-Path $PSScriptRoot '..' | Join-Path -ChildPath 'backend'
    $py = Join-Path $backend '..' | Join-Path -ChildPath '.venv/Scripts/python.exe'
    if (Test-Path -LiteralPath $py) { return $py }
    return 'python'
}

function Test-DirExists([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Name not found: $Path"
    }
}

function Get-LVFaceModelName([string]$Dir) {
    if ($LvfaceModelName) { return $LvfaceModelName }
    $models = Join-Path $Dir 'models'
    if (Test-Path -LiteralPath $models) {
        $onnx = Get-ChildItem -LiteralPath $models -Filter '*.onnx' -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($onnx) { return $onnx.Name }
    }
    # Fallback sensible default
    return 'LVFace-B_Glint360K.onnx'
}

Write-Host "Starting dev multiprocess setup (tmux-style)" -ForegroundColor Cyan

if ($UseWindowsTerminal -and $KillExisting) {
    # Close any existing Windows Terminal instances for a fresh session
    try {
        $wt = Get-Process -Name WindowsTerminal -ErrorAction SilentlyContinue
        if ($wt) {
            Write-Host "Closing existing Windows Terminal instances..." -ForegroundColor Yellow
            $wt | Stop-Process -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
        }
    } catch { }
}

Test-DirExists -Path $LvfaceDir -Name 'LVFaceDir'
Test-DirExists -Path $CaptionDir -Name 'CaptionDir'

# Environment for backend
$env:FACE_EMBED_PROVIDER = 'lvface'
$env:LVFACE_EXTERNAL_DIR = $LvfaceDir
$env:LVFACE_MODEL_NAME = Get-LVFaceModelName -Dir $LvfaceDir
$env:CAPTION_PROVIDER = 'blip2'
$env:CAPTION_EXTERNAL_DIR = $CaptionDir
$env:CAPTION_MODEL = 'auto'
$env:ENABLE_INLINE_WORKER = 'true'

# Optional: video flags can be enabled by the user in their session if needed

$backendRoot = Join-Path $PSScriptRoot '..' | Join-Path -ChildPath 'backend'
$pyExe = Resolve-BackendPython

Write-Host "LVFace: $($env:LVFACE_EXTERNAL_DIR) (model: $($env:LVFACE_MODEL_NAME))" -ForegroundColor DarkCyan
Write-Host "Caption: $($env:CAPTION_EXTERNAL_DIR) (provider: $($env:CAPTION_PROVIDER))" -ForegroundColor DarkCyan
Write-Host "Backend Python: $pyExe" -ForegroundColor DarkCyan

# Quick validations
Push-Location $backendRoot
try {
    & $pyExe -m app.cli validate-lvface
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "validate-lvface exited with code $LASTEXITCODE. Continuing, but face embeddings may fall back to stub."
    }
    & $pyExe -m app.cli validate-caption
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "validate-caption exited with code $LASTEXITCODE. Continuing, but captions may fall back to stub."
    }
} finally {
    Pop-Location
}

function Start-ApiTab {
    $content = @(
        "Set-Location -LiteralPath `"$backendRoot`"",
        "& `"$pyExe`" -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort --reload"
    ) -join "`n"
    $path = Join-Path $env:TEMP "api-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    if ($UseWindowsTerminal) {
        return @{ File = $path; Dir = $backendRoot }
    } else {
        Start-Process pwsh -ArgumentList @('-NoExit','-File', $path) -WorkingDirectory $backendRoot
        return $null
    }
}

function Start-LVFaceShell {
    $activate = ".venv\\Scripts\\Activate.ps1"
    $content = @(
        "Set-Location -LiteralPath `"$LvfaceDir`"",
        "if (Test-Path `"$activate`") { . `"$activate`" } else { Write-Warning `"$activate not found in $LvfaceDir`" }",
        "Write-Host `"LVFace venv activated. Ready.`" -ForegroundColor Green"
    ) -join "`n"
    $path = Join-Path $env:TEMP "lvface-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    if ($UseWindowsTerminal) {
        return @{ File = $path; Dir = $LvfaceDir }
    } else {
        Start-Process pwsh -ArgumentList @('-NoExit','-File', $path) -WorkingDirectory $LvfaceDir
        return $null
    }
}

function Start-CaptionShell {
    $activate = ".venv\\Scripts\\Activate.ps1"
    $content = @(
        "Set-Location -LiteralPath `"$CaptionDir`"",
        "if (Test-Path `"$activate`") { . `"$activate`" } else { Write-Warning `"$activate not found in $CaptionDir`" }",
        "Write-Host `"Caption venv activated (BLIP2). Ready.`" -ForegroundColor Green"
    ) -join "`n"
    $path = Join-Path $env:TEMP "caption-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    if ($UseWindowsTerminal) {
        return @{ File = $path; Dir = $CaptionDir }
    } else {
        Start-Process pwsh -ArgumentList @('-NoExit','-File', $path) -WorkingDirectory $CaptionDir
        return $null
    }
}

# Launch
$apiSpec = Start-ApiTab
$lvSpec = Start-LVFaceShell
$capSpec = Start-CaptionShell

if ($UseWindowsTerminal) {
    # Build a single WT chain so panes open in the same window (pass as array)
    $wtArgs = @(
        'new-tab','-d', $apiSpec.Dir, 'pwsh','-NoExit','-File', $apiSpec.File,
        ';','split-pane','-H','-d', $lvSpec.Dir,  'pwsh','-NoExit','-File', $lvSpec.File,
        ';','split-pane','-V','-d', $capSpec.Dir, 'pwsh','-NoExit','-File', $capSpec.File
    )
    Start-Process wt -ArgumentList $wtArgs
}

Write-Host "Launched: API (port $ApiPort), LVFace shell, Caption shell." -ForegroundColor Green
Write-Host "Tip: Use -UseWindowsTerminal for a single window with panes (requires Windows Terminal)." -ForegroundColor Yellow
