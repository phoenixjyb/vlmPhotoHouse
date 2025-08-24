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
    [switch]$KillExisting,  # Deprecated - now always kills existing instances
    [switch]$NoCleanup     # Skip cleanup of existing instances/ports
)

$ErrorActionPreference = 'Stop'

function Resolve-BackendPython {
    $backend = Join-Path $PSScriptRoot '..' | Join-Path -ChildPath 'backend'
    # Use optimized VLM Photo Engine environment (Python 3.12.10 + PyTorch 2.8.0+cu126)
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

# Always kill existing Windows Terminal instances for a fresh session (unless -NoCleanup)
if (-not $NoCleanup) {
    try {
        Write-Host "🔄 Cleaning up existing Windows Terminal instances..." -ForegroundColor Yellow
        $wt = Get-Process -Name WindowsTerminal -ErrorAction SilentlyContinue
        if ($wt) {
            $wt | Stop-Process -Force -ErrorAction SilentlyContinue
            Write-Host "✅ Closed $($wt.Count) existing Windows Terminal instance(s)" -ForegroundColor Green
            Start-Sleep -Seconds 2  # Give processes time to fully terminate
        } else {
            Write-Host "✅ No existing Windows Terminal instances found" -ForegroundColor Green
        }
    } catch { 
        Write-Warning "Could not check/close existing Windows Terminal instances: $($_.Exception.Message)"
    }

    # Clean up any processes using our target ports
    try {
        Write-Host "🔄 Checking for services on target ports..." -ForegroundColor Yellow
        $portsToCheck = @($ApiPort, $VoicePort, 8000)  # Include common alternative ports
        foreach ($port in $portsToCheck) {
            try {
                $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
                if ($connections) {
                    foreach ($conn in $connections) {
                        $process = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
                        if ($process) {
                            Write-Host "🔴 Stopping process '$($process.ProcessName)' on port $port" -ForegroundColor Red
                            $process | Stop-Process -Force -ErrorAction SilentlyContinue
                        }
                    }
                }
            } catch { }
        }
        Write-Host "✅ Port cleanup completed" -ForegroundColor Green
    } catch {
        Write-Warning "Could not perform port cleanup: $($_.Exception.Message)"
    }
} else {
    Write-Host "⚠️ Skipping cleanup due to -NoCleanup flag" -ForegroundColor Yellow
}

if ($UseWindowsTerminal -and $KillExisting) {
    # This block is now redundant as we always clean up above
    Write-Host "Note: -KillExisting flag is redundant as we always clean up existing instances" -ForegroundColor Gray
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
            $effectiveCaption = 'blip2'
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

# RTX 3090 Voice Service Configuration
if ($Preset -eq 'RTX3090') {
    # Enable RTX 3090 optimizations for voice services
    $env:TTS_DEVICE = 'cuda:0'
    $env:ASR_DEVICE = 'cuda:0'
    $env:CUDA_VISIBLE_DEVICES = '0'
    Write-Host "Voice services configured for RTX 3090 (cuda:0)" -ForegroundColor DarkCyan
}

# Device selection
if ($effectiveUseGpu) {
    if ($Preset -eq 'RTX3090') {
        # RTX 3090 is GPU 0, Quadro P2000 is GPU 1
        $env:EMBED_DEVICE = 'cuda:0'
        $env:CAPTION_DEVICE = 'cuda:0'
    } else {
        $env:EMBED_DEVICE = 'cuda'
        $env:CAPTION_DEVICE = 'cuda'
    }
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
    # Use isolated LVFace environment from workload-specific matrix
    $lvfaceActivate = ".venv-lvface-311\\Scripts\\Activate.ps1"
    $content = @(
        "Set-Location -LiteralPath `"$LvfaceDir`"",
        "# Using isolated LVFace environment (Python 3.11.9 + PyTorch 2.6.0+cu124)",
        "if (Test-Path `"$lvfaceActivate`") { . `"$lvfaceActivate`" } else { Write-Warning `"$lvfaceActivate not found in $LvfaceDir`" }",
        "Write-Host `"LVFace isolated venv activated (CUDA 12.4 compatible). Ready.`" -ForegroundColor Green"
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
    # Use optimized ASR environment from workload-specific matrix
    $asrActivate = ".venv-asr-311\\Scripts\\Activate.ps1"
    $content = @(
        "Set-Location -LiteralPath `"$VoiceDir`"",
        "# Using optimized ASR environment (Python 3.11.9 + PyTorch 2.8.0+cu126)",
        "if (Test-Path `"$asrActivate`") { . `"$asrActivate`" } else { Write-Warning `"$asrActivate not found in $VoiceDir`" }",
        "if (Test-Path '.\\.venv-asr-311\\Scripts\\python.exe') { `$py = '.\\.venv-asr-311\\Scripts\\python.exe' } else { `$py = 'python' }",
        "Write-Host 'Starting LLMyTranslate service with RTX 3090 optimized ASR...' -ForegroundColor Cyan",
        "if (Test-Path '.\\src\\main.py') {",
        "  & `$py -m uvicorn src.main:app --host 127.0.0.1 --port $VoicePort",
        "} elseif (Test-Path '.\\run.py') {",
        "  & `$py run.py",
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

function Start-TTSPane {
    # Use optimized TTS environment from workload-specific matrix
    $ttsActivate = ".venv-tts\\Scripts\\Activate.ps1"
    $content = @(
        "Set-Location -LiteralPath `"$VoiceDir`"",
        "# Using optimized TTS environment (Python 3.12.10 + PyTorch 2.8.0+cu126)",
        "if (Test-Path `"$ttsActivate`") { . `"$ttsActivate`" } else { Write-Warning `"$ttsActivate not found in $VoiceDir`" }",
        "if (Test-Path '.\\.venv-tts\\Scripts\\python.exe') { `$py = '.\\.venv-tts\\Scripts\\python.exe' } else { `$py = 'python' }",
        "Write-Host 'RTX 3090 TTS Environment Ready (Coqui TTS 0.27.0)' -ForegroundColor Green",
        "Write-Host 'Available commands:' -ForegroundColor Yellow",
        "Write-Host '  Test TTS: & `$py tts_subprocess_rtx3090.py test_rtx3090.json' -ForegroundColor Gray",
        "Write-Host '  Server mode: & `$py -m uvicorn tts_server:app --port 8002' -ForegroundColor Gray"
    ) -join "`n"
    $path = Join-Path $env:TEMP "tts-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    if ($UseWindowsTerminal) {
        return @{ File = $path; Dir = $VoiceDir }
    } else {
        Start-Process pwsh -ArgumentList @('-NoExit','-File', $path) -WorkingDirectory $VoiceDir
        return $null
    }
}

# Launch - 2x2 Grid Layout
$apiSpec = Start-ApiTab
$lvSpec = Start-LVFaceShell  
$voiceSpec = Start-VoicePane
$ttsSpec = Start-TTSPane

if ($UseWindowsTerminal) {
    # Build a clean 2x2 grid layout for optimized workload-specific environments
    # Create 2x2 grid: Start with one pane, split horizontally for top row, then split each vertically
    # Top Left: VLM Photo Engine API | Top Right: Voice Service (ASR)
    # Bottom Left: LVFace Environment | Bottom Right: TTS Environment
    $wtArgs = @(
        'new-tab', '--title', "`"VLM Photo Engine`"", '-d', "`"$($apiSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($apiSpec.File)`"",
        ';', 'split-pane', '-H', '--title', "`"Voice Service (ASR)`"", '-d', "`"$($voiceSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($voiceSpec.File)`"",
        ';', 'move-focus', 'left',
        ';', 'split-pane', '-V', '--title', "`"LVFace Environment`"", '-d', "`"$($lvSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($lvSpec.File)`"",
        ';', 'move-focus', 'up', ';', 'move-focus', 'right',
        ';', 'split-pane', '-V', '--title', "`"TTS Environment`"", '-d', "`"$($ttsSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($ttsSpec.File)`""
    )
    Write-Host "Executing Windows Terminal with args: $($wtArgs -join ' ')" -ForegroundColor Gray
    Start-Process wt -ArgumentList $wtArgs
}

Write-Host "🎯 Launched 2x2 Grid Layout:" -ForegroundColor Green
Write-Host "  Top Left: VLM Photo Engine (port $ApiPort)" -ForegroundColor Cyan  
Write-Host "  Top Right: Voice Service ASR (port $VoicePort)" -ForegroundColor Cyan
Write-Host "  Bottom Left: LVFace Environment" -ForegroundColor Cyan
Write-Host "  Bottom Right: TTS Environment (RTX 3090)" -ForegroundColor Cyan
Write-Host "✅ All workload-specific optimized environments ready (RTX 3090 + CUDA 12.6/12.4)" -ForegroundColor Green
Write-Host "🧹 Previous instances automatically cleaned up for fresh start" -ForegroundColor Gray
Write-Host "Tip: Use -NoCleanup to skip automatic cleanup of existing instances." -ForegroundColor Yellow
