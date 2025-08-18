param(
    [string]$LvfaceDir = 'C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace',
    [string]$CaptionDir = 'C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels',
    [string]$VoiceDir = 'C:\Users\yanbo\wSpace\llmytranslate',
    [string]$LvfaceModelName = '',
    [int]$ApiPort = 8002,
    [int]$VoicePort = 8001,
    [string]$CaptionProvider = 'blip2',
    [string]$FaceProvider = 'lvface',
    [string]$DbPath,
    [string]$Preset, # Optional: LowVRAM | RTX3090
    [switch]$Gpu,
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
if (Test-Path -LiteralPath $VoiceDir) {
    Write-Host "VoiceDir detected: $VoiceDir" -ForegroundColor DarkCyan
} else {
    Write-Warning "VoiceDir not found: $VoiceDir. Voice pane will still open but may warn."
}

# Resolve effective profile (preset -> explicit overrides)
$effectiveFace = $FaceProvider
$effectiveCaption = $CaptionProvider
$effectiveUseGpu = [bool]$Gpu
if ($Preset) {
    switch ($Preset.ToLowerInvariant()) {
        'lowvram' {
            $effectiveFace = 'facenet'
            $effectiveCaption = 'vitgpt2'
            $effectiveUseGpu = $true
        }
        'rtx3090' {
            $effectiveFace = 'lvface'
            $effectiveCaption = 'qwen2.5-vl'
            $effectiveUseGpu = $true
        }
        default {
            Write-Warning "Unknown preset '$Preset'. Ignoring preset."
        }
    }
    # Allow explicit flags to override preset
    if ($PSBoundParameters.ContainsKey('FaceProvider')) { $effectiveFace = $FaceProvider }
    if ($PSBoundParameters.ContainsKey('CaptionProvider')) { $effectiveCaption = $CaptionProvider }
    if ($PSBoundParameters.ContainsKey('Gpu')) { $effectiveUseGpu = [bool]$Gpu }
}

# Environment for backend (using effective values)
$env:FACE_EMBED_PROVIDER = $effectiveFace
$env:LVFACE_EXTERNAL_DIR = $LvfaceDir
$env:LVFACE_MODEL_NAME = Get-LVFaceModelName -Dir $LvfaceDir
$env:CAPTION_PROVIDER = $effectiveCaption
$env:CAPTION_EXTERNAL_DIR = $CaptionDir
$env:CAPTION_MODEL = 'auto'
$env:ENABLE_INLINE_WORKER = 'true'

# Voice proxy defaults (only set if not already present)
if (-not $env:VOICE_ENABLED) { $env:VOICE_ENABLED = 'true' }
if (-not $env:VOICE_EXTERNAL_BASE_URL) { $env:VOICE_EXTERNAL_BASE_URL = "http://127.0.0.1:$VoicePort" }
# Align TTS path with LLMyTranslate default
if (-not $env:VOICE_TTS_PATH) { $env:VOICE_TTS_PATH = '/api/tts/synthesize' }

# Device selection
if ($effectiveUseGpu) {
    $env:EMBED_DEVICE = 'cuda'
    $env:CAPTION_DEVICE = 'cuda'
} else {
    $env:EMBED_DEVICE = 'cpu'
    $env:CAPTION_DEVICE = 'cpu'
}

# Optional: video flags can be enabled by the user in their session if needed

$backendRoot = Join-Path $PSScriptRoot '..' | Join-Path -ChildPath 'backend'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pyExe = Resolve-BackendPython

Write-Host "LVFace: $($env:LVFACE_EXTERNAL_DIR) (model: $($env:LVFACE_MODEL_NAME))" -ForegroundColor DarkCyan
if ($Preset) {
    $gpuVal = if ($effectiveUseGpu) { 'on' } else { 'off' }
    Write-Host "Preset: $Preset applied (face=$effectiveFace, caption=$effectiveCaption, gpu=$gpuVal)" -ForegroundColor Gray
}
Write-Host "Face provider: $($env:FACE_EMBED_PROVIDER) device=$($env:EMBED_DEVICE)" -ForegroundColor DarkCyan
Write-Host "Caption: $($env:CAPTION_EXTERNAL_DIR) (provider: $($env:CAPTION_PROVIDER)) device=$($env:CAPTION_DEVICE)" -ForegroundColor DarkCyan
Write-Host "Backend Python: $pyExe" -ForegroundColor DarkCyan

# Database configuration (optional relocation)
if ($DbPath) {
    try {
        $dbDir = [System.IO.Path]::GetDirectoryName($DbPath)
        if ($dbDir -and -not (Test-Path -LiteralPath $dbDir)) {
            Write-Host "Creating DB directory: $dbDir" -ForegroundColor Yellow
            New-Item -ItemType Directory -Path $dbDir -Force | Out-Null
        }
        # Build sqlite URI (normalize to forward slashes)
        $dbUriPath = ($DbPath -replace '\\','/')
        if ($dbUriPath -match '^[A-Za-z]:') {
            $env:DATABASE_URL = "sqlite:///$dbUriPath"
        } else {
            # Assume it's already a unix-style absolute path or relative path
            if ($dbUriPath.StartsWith('/')) { $env:DATABASE_URL = "sqlite://$dbUriPath" } else { $env:DATABASE_URL = "sqlite:///$dbUriPath" }
        }
        Write-Host "Database: $($env:DATABASE_URL)" -ForegroundColor DarkCyan

        # If target DB doesn't exist, attempt to move an existing local DB
        if (-not (Test-Path -LiteralPath $DbPath)) {
            $src1 = Join-Path $backendRoot 'metadata.sqlite'
            $src2 = Join-Path $repoRoot 'metadata.sqlite'
            # Try an alternate path variant (e.g., migrate from E:\vlm-data to E:\VLM_DATA or vice versa)
            $altDbPath = $null
            try {
                $alt1 = $DbPath -replace 'VLM_DATA','vlm-data'
                $alt2 = $DbPath -replace 'vlm-data','VLM_DATA'
                foreach ($cand in @($alt1, $alt2)) {
                    if ($cand -and $cand -ne $DbPath -and (Test-Path -LiteralPath $cand)) { $altDbPath = $cand; break }
                }
            } catch { }
            $src = $null
            if (Test-Path -LiteralPath $src1) { $src = $src1 }
            elseif (Test-Path -LiteralPath $src2) { $src = $src2 }
            elseif ($altDbPath) { $src = $altDbPath }
            if ($src) {
                try {
                    Write-Host "Moving existing DB from $src to $DbPath" -ForegroundColor Yellow
                    Move-Item -LiteralPath $src -Destination $DbPath -Force
                } catch {
                    Write-Warning "Failed to move existing DB: $($_.Exception.Message). Will create a fresh DB at the new location."
                }
            }
        }
    } catch {
        Write-Warning "DB setup error: $($_.Exception.Message). Proceeding with default location."
    }
}

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
    # Warm up providers (loads models)
    & $pyExe -m app.cli warmup
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "warmup exited with code $LASTEXITCODE."
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
    "Write-Host `"Caption venv activated ($($env:CAPTION_PROVIDER)). Ready.`" -ForegroundColor Green"
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

function Start-VoicePane {
    $activate = ".venv\\Scripts\\Activate.ps1"
    $content = @(
        "Set-Location -LiteralPath `"$VoiceDir`"",
    "if (Test-Path `"$activate`") { . `"$activate`" } else { Write-Warning `"$activate not found in $VoiceDir`" }",
    "if (Test-Path '.\\.venv\\Scripts\\python.exe') { `$py = '.\\.venv\\Scripts\\python.exe' } else { `$py = 'python' }",
        "Write-Host 'Starting LLMyTranslate service...' -ForegroundColor Cyan",
        "if (Test-Path '.\\src\\main.py') {",
    "  & `$py -m uvicorn src.main:app --host 127.0.0.1 --port $VoicePort",
        "} else {",
    "  & `$py -m llmytranslate --host 127.0.0.1 --port $VoicePort",
        "}"
    ) -join "`n"
    $path = Join-Path $env:TEMP "voice-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    if ($UseWindowsTerminal) {
        return @{ File = $path; Dir = $VoiceDir }
    } else {
        Start-Process pwsh -ArgumentList @('-NoExit','-File', $path) -WorkingDirectory $VoiceDir
        return $null
    }
}

# Launch
$apiSpec = Start-ApiTab
$lvSpec = Start-LVFaceShell
$capSpec = Start-CaptionShell
$voiceSpec = Start-VoicePane

if ($UseWindowsTerminal) {
    # Build a single WT chain so panes open in the same window (pass as array)
    $wtArgs = @(
    'new-tab','-d', $apiSpec.Dir, 'pwsh','-NoExit','-File', $apiSpec.File,
    ';','split-pane','-H','-d', $lvSpec.Dir,  'pwsh','-NoExit','-File', $lvSpec.File,
    ';','split-pane','-V','-d', $capSpec.Dir, 'pwsh','-NoExit','-File', $capSpec.File,
    ';','split-pane','-V','-d', $voiceSpec.Dir, 'pwsh','-NoExit','-File', $voiceSpec.File
    )
    Start-Process wt -ArgumentList $wtArgs
}

Write-Host "Launched: API (port $ApiPort), LVFace shell, Caption shell, Voice service (port $VoicePort)." -ForegroundColor Green
Write-Host "Tip: Use -UseWindowsTerminal for a single window with panes (requires Windows Terminal)." -ForegroundColor Yellow
