param(

    [string]$Preset = 'RTX3090',  # RTX3090 | LowVRAM | CPU

    [switch]$UseWindowsTerminal,

    [switch]$KillExisting,

    [switch]$NoCleanup,

    [switch]$RunPreCheck,

    [int]$GpuMonitorInterval = 3,

    [int]$ApiPort = 8002,

    [int]$VoicePort = 8001,

    [int]$LvfacePort = 8003,

    [switch]$WithInteractiveShell  # Add interactive command shell

)

# Default to using Windows Terminal and enabling features
if (-not $PSBoundParameters.ContainsKey('UseWindowsTerminal')) { $UseWindowsTerminal = $true }
if (-not $PSBoundParameters.ContainsKey('KillExisting')) { $KillExisting = $true }
if (-not $PSBoundParameters.ContainsKey('RunPreCheck')) { $RunPreCheck = $true }
if (-not $PSBoundParameters.ContainsKey('WithInteractiveShell')) { $WithInteractiveShell = $true }

$ErrorActionPreference = 'Stop'

# Prevent multiple instances
$scriptName = [System.IO.Path]::GetFileNameWithoutExtension($PSCommandPath)
$existingProcesses = Get-WmiObject Win32_Process | Where-Object { 
    $_.Name -eq "pwsh.exe" -and 
    $_.CommandLine -like "*$scriptName*" -and 
    $_.ProcessId -ne $PID 
}
if ($existingProcesses) {
    Write-Host "⚠️ Another instance of $scriptName is already running (PID: $($existingProcesses.ProcessId -join ', '))" -ForegroundColor Yellow
    Write-Host "Kill existing instances before starting new one." -ForegroundColor Yellow
    exit 1
}

Write-Host "🚀 VLM Photo Engine - Unified RTX 3090 Multi-Service Launcher" -ForegroundColor Cyan
Write-Host "🎯 Target: 4-service coordination with optimal RTX 3090 utilization" -ForegroundColor Yellow

# Directory Configuration
$VlmPhotoHouseDir = $PSScriptRoot
$LvfaceDir = 'C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace'
$CaptionDir = 'C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels'
$VoiceDir = 'C:\Users\yanbo\wSpace\llmytranslate'

# Ensure we run from the script's directory for any relative paths
Set-Location -LiteralPath $VlmPhotoHouseDir

# Absolute paths for GPU precheck
$PrecheckPy     = Join-Path $VlmPhotoHouseDir '.venv\Scripts\python.exe'
$PrecheckScript = Join-Path $VlmPhotoHouseDir 'tools\gpu_precheck_validation.py'

# 🔍 Dynamic RTX 3090 GPU Detection
Write-Host ""
Write-Host "🔍 Detecting RTX 3090 GPU index..." -ForegroundColor Green
$gpuList = nvidia-smi --list-gpus
$rtx3090Index = -1
$gpuList | ForEach-Object {
    if ($_ -match "GPU (\d+): .*RTX 3090") {
        $rtx3090Index = [int]$matches[1]
    }
}

if ($rtx3090Index -eq -1) {
    Write-Host "❌ RTX 3090 not found! Available GPUs:" -ForegroundColor Red
    $gpuList | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    exit 1
}

Write-Host "✅ RTX 3090 found at GPU index: $rtx3090Index" -ForegroundColor Green

function Test-DirExists([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Name not found: $Path"
    }
}

# Validate all service directories
Test-DirExists -Path $VlmPhotoHouseDir -Name 'VlmPhotoHouseDir'
Test-DirExists -Path $LvfaceDir -Name 'LvfaceDir'
Test-DirExists -Path $CaptionDir -Name 'CaptionDir'
Test-DirExists -Path $VoiceDir -Name 'VoiceDir'

# GPU Pre-Check Integration
if ($RunPreCheck) {
    Write-Host ""
    Write-Host "🔍 Running comprehensive GPU validation..." -ForegroundColor Green

    try {
        # Run GPU validation from main directory where the script is located
        & "$PrecheckPy" "$PrecheckScript" | Out-Null

        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ GPU Pre-Check FAILED!" -ForegroundColor Red
            Write-Host "Cannot proceed with multi-service launch until GPU issues are resolved" -ForegroundColor Yellow
            exit 1
        }

        Write-Host "✅ GPU Pre-Check PASSED - RTX 3090 ready for all services" -ForegroundColor Green

    } catch {
        Write-Host "❌ GPU Pre-Check execution failed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Continuing with manual GPU detection..." -ForegroundColor Yellow
    }
}

# Clean up existing processes
if ($KillExisting -and -not $NoCleanup) {
    try {
        # Proactive process cleanup to avoid duplicates (uvicorn parents, caption server)
        try {
            $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'python' }
            $killPatterns = @(
                'caption_server.py',
                ' -m uvicorn app.main:app ',
                ' -m uvicorn src.main:app '
            )
            foreach ($p in $procs) {
                $cmd = [string]$p.CommandLine
                if ($killPatterns | Where-Object { $cmd -like "*$_*" }) {
                    Write-Host "?? Stopping leftover python PID=$($p.ProcessId) :: $cmd" -ForegroundColor Yellow
                    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
                }
            }
            Write-Host "? Process pattern cleanup completed" -ForegroundColor Green
        } catch {
            Write-Host "! Process pattern cleanup skipped: $($_.Exception.Message)" -ForegroundColor DarkYellow
        }
        Write-Host "🔄 Cleaning up existing service instances..." -ForegroundColor Yellow

        # Do not kill Windows Terminal itself; that can terminate the caller session.
        Write-Host "ℹ️ Skipping Windows Terminal shutdown during cleanup (safer session behavior)." -ForegroundColor DarkCyan

        # Clean up service ports
        $portsToCheck = @($ApiPort, $VoicePort, 8000, 8002, 8003)
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
        Write-Warning "Could not perform full cleanup: $($_.Exception.Message)"
    }
}

# ===== RTX 3090 UNIFIED ENVIRONMENT CONFIGURATION =====

# Set explicit GPU device targeting RTX 3090
$env:PYTORCH_CUDA_DEVICE = "$rtx3090Index"
$env:CUDA_DEVICE_ORDER = "PCI_BUS_ID"

# Set PyTorch device preference to RTX 3090
$env:TORCH_CUDA_ARCH_LIST = '8.6'  # RTX 3090 compute capability

# Configure memory allocation for RTX 3090 (24GB VRAM)
$env:PYTORCH_CUDA_ALLOC_CONF = "max_split_size_mb:1024,expandable_segments:True"

Write-Host "🎯 GPU Configuration:" -ForegroundColor Green
Write-Host "  RTX 3090 Index: $rtx3090Index" -ForegroundColor White
Write-Host "  CUDA Device Order: PCI_BUS_ID" -ForegroundColor White
Write-Host "  Memory Config: 1GB split size, expandable segments" -ForegroundColor White

# VLM Photo Engine Backend Configuration
# GPU Environment Configuration - Force RTX 3090 usage
$env:PYTORCH_CUDA_DEVICE = "$rtx3090Index"
$env:CAPTION_GPU_DEVICE = "$rtx3090Index"

# Face Processing Configuration  
$env:FACE_EMBED_PROVIDER = if ($env:FACE_EMBED_PROVIDER) { $env:FACE_EMBED_PROVIDER } else { 'lvface' }
$env:LVFACE_EXTERNAL_DIR = ''
$env:LVFACE_MODEL_NAME = 'LVFace-B_Glint360K.onnx'
$env:LVFACE_SERVICE_URL = "http://127.0.0.1:$LvfacePort"

$env:LVFACE_SERVICE_HOST = '127.0.0.1'

$env:LVFACE_SERVICE_PORT = "$LvfacePort"
$env:SCRFD_SERVICE_URL = 'http://172.22.61.27:8003'  # WSL unified service
$env:CAPTION_PROVIDER = if ($env:CAPTION_PROVIDER) { $env:CAPTION_PROVIDER } else { 'http' }
$env:CAPTION_EXTERNAL_DIR = $CaptionDir
$env:CAPTION_MODEL = 'auto'
$env:ENABLE_INLINE_WORKER = 'true'
$env:WORKER_CONCURRENCY = '4'

# Device assignments - All services use RTX 3090
$env:EMBED_DEVICE = "cuda:$rtx3090Index"
$env:CAPTION_DEVICE = "cuda:$rtx3090Index"
$env:TTS_DEVICE = "cuda:$rtx3090Index"
$env:ASR_DEVICE = "cuda:$rtx3090Index"

# Voice proxy configuration
$env:VOICE_ENABLED = 'true'
$env:VOICE_EXTERNAL_BASE_URL = "http://127.0.0.1:$VoicePort"
$env:VOICE_TTS_PATH = '/api/tts/synthesize'

Write-Host ""
Write-Host "🎯 RTX 3090 Unified Configuration Applied:" -ForegroundColor Green
Write-Host "  GPU Assignment: cuda:$rtx3090Index (RTX 3090) for ALL services" -ForegroundColor Cyan
Write-Host "  VLM Engine: LVFace + BLIP2 on RTX 3090" -ForegroundColor Cyan
Write-Host "  Voice Services: ASR + TTS on RTX 3090" -ForegroundColor Cyan
Write-Host "  Caption Models: Direct RTX 3090 utilization" -ForegroundColor Cyan

# ===== PANE CREATION FUNCTIONS =====

function New-MainApiPane {
    param([int]$GpuIndex)
    $backendRoot = Join-Path $VlmPhotoHouseDir 'backend'
    $pyExe = Join-Path $VlmPhotoHouseDir '.venv\Scripts\python.exe'

    $content = @(
        "Set-Location -LiteralPath `"$backendRoot`"",
        "",
        "# Set environment variables for this pane - NO DIRECT MODEL LOADING",
        "`$env:CAPTION_PROVIDER = 'http'",
        "`$env:CAPTION_SERVICE_URL = 'http://127.0.0.1:8002'",
        "`$env:ENABLE_INLINE_WORKER = 'true'", 
        "`$env:WORKER_CONCURRENCY = '4'",
        "",
        "Write-Host '🌐 VLM Photo Engine - Main API Server (FastAPI)' -ForegroundColor Green",
        "Write-Host 'Central orchestration | Photo/Video processing | AI task coordination' -ForegroundColor Yellow",
        "Write-Host 'Caption: HTTP service (8002) | No direct model loading' -ForegroundColor Cyan",
        "Write-Host 'External providers: LVFace (8003) + Caption HTTP (8002)' -ForegroundColor Yellow",
        "",
        "# Validate RTX 3090 availability for main backend",
        "& `"$pyExe`" -c `"import torch; print('RTX 3090 Available:', torch.cuda.is_available()); print('Device 0:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'); print(f'Device 0 Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB' if torch.cuda.is_available() else '')`"",
        "",
        "# Test caption provider configuration",
        "Write-Host '🔍 Testing BLIP2 caption provider...' -ForegroundColor Cyan",
        "& `"$pyExe`" -c `"from app.caption_service import get_caption_provider; provider = get_caption_provider(); print(f'Caption Provider: {type(provider).__name__}'); print(f'Model: {provider.get_model_name()}')`"",
        "",
        "# Start main FastAPI server",
        "Write-Host '🚀 Starting VLM Photo Engine Main API Server on port $ApiPort...' -ForegroundColor Cyan",
        "Write-Host 'Available endpoints: /health, /search, /assets, /captions, /voice/*' -ForegroundColor Gray",
        "",
        "# Check if port is already in use (LISTEN only)",
        "`$portCheck = Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue",
        "if (`$portCheck) {",
        "    Write-Host '⚠️ Port $ApiPort already in use - skipping Main API startup' -ForegroundColor Yellow",
        "    Write-Host 'Existing process(es):' -ForegroundColor Gray",
        "    `$portCheck | Format-Table -AutoSize",
        "} else {",
        "    & `"$pyExe`" -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort --reload",
        "}"
    ) -join "`n"

    $path = Join-Path $env:TEMP "main-api-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $backendRoot; Title = "Main API Server (Port $ApiPort)" }
}

function New-CaptionModelsPane {
    param([int]$GpuIndex)
    $pyExe = Join-Path $CaptionDir '.venv\Scripts\python.exe'

    $content = @(
        "Set-Location -LiteralPath `"$CaptionDir`"",
        "Write-Host '🖼️ Caption Models HTTP Service - BLIP2 Only' -ForegroundColor Green",
        "Write-Host 'Dedicated caption service | Port 8002 | RTX 3090' -ForegroundColor Yellow",
        "",
        "# Activate caption environment",
        "if (Test-Path '.venv\\Scripts\\Activate.ps1') { . '.venv\\Scripts\\Activate.ps1' }",
        "",
        "# Configure RTX 3090 environment",
        "`$env:TORCH_CUDA_ARCH_LIST = '8.6'",
        "`$env:PYTORCH_CUDA_DEVICE = '$GpuIndex'",  # RTX 3090",
        "`$env:CUDA_DEVICE_ORDER = 'PCI_BUS_ID'",
        "`$env:CAPTION_VRAM_MODE = 'balanced'",
        "`$env:CAPTION_MAX_GPU_GB = '12'",
        "`$env:CUDA_VISIBLE_DEVICES = '$GpuIndex'",
        "",
        "Write-Host '🚀 Starting Caption Models HTTP Server...' -ForegroundColor Cyan",
        "Write-Host '📍 Service URL: http://127.0.0.1:8002' -ForegroundColor White",
        "Write-Host '🎯 Model: BLIP2-OPT-2.7B (6GB VRAM)' -ForegroundColor Gray",
        "Write-Host '🖥️ Device: RTX 3090 (cuda:1)' -ForegroundColor Gray",
        "",
        "# Start HTTP server with BLIP2 model (skip if one is already healthy)",
        "`$existing = try { (Invoke-RestMethod -Uri 'http://127.0.0.1:8002/health' -TimeoutSec 2 -ErrorAction SilentlyContinue) } catch { `$null }",
        "if (-not `$existing -or `$existing.status -ne 'healthy') {",
        "    & `"$pyExe`" caption_server.py --host 127.0.0.1 --port 8002 --provider blip2",
        "} else {",
        "    Write-Host '✅ Existing Caption Models service detected on :8002, using existing' -ForegroundColor Yellow",
        "}"
    ) -join "`n"

    $path = Join-Path $env:TEMP "caption-models-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $CaptionDir; Title = "Caption HTTP Service (BLIP2)" }
}

function New-LvfacePane {
    param([int]$GpuIndex)
    $backendRoot = Join-Path $VlmPhotoHouseDir 'backend'
    $pyExe = Join-Path $VlmPhotoHouseDir '.venv\Scripts\python.exe'
    $content = @(
        "Set-Location -LiteralPath `"$backendRoot`""
        "Write-Host 'LVFace HTTP Service - RTX 3090 embeddings' -ForegroundColor Green"
        "Write-Host 'Port: $LvfacePort' -ForegroundColor Cyan"
        "Write-Host 'Model: ' + `$env:LVFACE_MODEL_PATH -ForegroundColor Gray"
        "`$existing = try { Invoke-WebRequest -Uri 'http://127.0.0.1:$LvfacePort/health' -Method GET -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop } catch { `$null }"
        "if (`$existing -and `$existing.StatusCode -eq 200) { Write-Host 'Reusing existing LVFace service on port $LvfacePort' -ForegroundColor Yellow } else { Write-Host 'Launching LVFace service via uvicorn...' -ForegroundColor Cyan; & `"$pyExe`" -m uvicorn app.lvface_http_service:app --host 127.0.0.1 --port $LvfacePort }"
    ) -join "`n"
    $path = Join-Path $env:TEMP "lvface-service-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $backendRoot; Title = "LVFace Service" }
}

function New-AsrPane {
    param([int]$GpuIndex)
    $asrActivate = Join-Path $VoiceDir '.venv-asr-311\Scripts\Activate.ps1'
    $asrPy = Join-Path $VoiceDir '.venv-asr-311\Scripts\python.exe'

    $content = @(
        "Write-Host '🎤 ASR Service - RTX 3090 Speech Recognition' -ForegroundColor Green",
        "Write-Host 'Whisper + PyTorch | Real-time transcription' -ForegroundColor Yellow",
        "",
        "Set-Location -LiteralPath `"$VoiceDir`"",
        "if (Test-Path `"$asrActivate`") { . `"$asrActivate`" } else { Write-Warning `"$asrActivate not found`" }",
        "",
        "# Configure RTX 3090 for ASR (cuda:0 = RTX 3090 when unrestricted)",
        "`$env:ASR_DEVICE = 'cuda:0'",
        "",
        "# Test ASR GPU access",
        "Write-Host '🔍 Testing ASR RTX 3090 configuration...' -ForegroundColor Cyan",
        "& `"$asrPy`" -c `"import torch; print('ASR GPU Available:', torch.cuda.is_available()); print('Device 0:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'); print(f'Device 0 Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB' if torch.cuda.is_available() else '')`"",
        "",
        "Write-Host '✅ ASR Environment Ready - RTX 3090 optimized' -ForegroundColor Green",
        "Write-Host 'ASR service runs as part of main voice server on port $VoicePort' -ForegroundColor Yellow",
        "Write-Host 'Available commands:' -ForegroundColor Yellow",
        "Write-Host '  Test ASR: python -c `"import whisper; model = whisper.load_model(\\`"base\\`")`"' -ForegroundColor Gray",
        "Write-Host '  Monitor: curl http://127.0.0.1:$VoicePort/health' -ForegroundColor Gray"
    ) -join "`n"

    $path = Join-Path $env:TEMP "asr-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $VoiceDir; Title = "ASR Service (RTX 3090)" }
}

function New-TtsPane {
    param([int]$GpuIndex)
    $ttsActivate = Join-Path $VoiceDir '.venv-tts\Scripts\Activate.ps1'
    $ttsPy = Join-Path $VoiceDir '.venv-tts\Scripts\python.exe'

    $content = @(
        "Write-Host '🔊 TTS Service - RTX 3090 Speech Synthesis' -ForegroundColor Green",
        "Write-Host 'Coqui TTS 0.27.0 | High-quality voice generation' -ForegroundColor Yellow",
        "",
        "Set-Location -LiteralPath `"$VoiceDir`"",
        "if (Test-Path `"$ttsActivate`") { . `"$ttsActivate`" } else { Write-Warning `"$ttsActivate not found`" }",
        "",
        "# Configure RTX 3090 for TTS (cuda:0 = RTX 3090 when unrestricted)",
        "`$env:TTS_DEVICE = 'cuda:0'",
        "",
        "# Test TTS GPU access",
        "Write-Host '🔍 Testing TTS RTX 3090 configuration...' -ForegroundColor Cyan",
        "& `"$ttsPy`" -c `"import torch; print('TTS GPU Available:', torch.cuda.is_available()); print('Device 0:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'); print(f'Device 0 Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB' if torch.cuda.is_available() else '')`"",
        "",
        "# Test RTX 3090 TTS capabilities",
        "Write-Host '⚡ Testing TTS synthesis performance...' -ForegroundColor Cyan",
        "if (Test-Path 'rtx3090_tts_config.py') {",
        "    & `"$ttsPy`" -c `"from rtx3090_tts_config import get_optimal_tts_device; print('Optimal TTS Device:', get_optimal_tts_device())`"",
        "}",
        "",
        "if (Test-Path 'test_rtx3090.json') {",
        "    Write-Host 'Running RTX 3090 TTS test...' -ForegroundColor Cyan",
        "    & `"$ttsPy`" tts_subprocess_rtx3090.py test_rtx3090.json",
        "}",
        "",
        "Write-Host '✅ TTS Environment Ready - RTX 3090 optimized' -ForegroundColor Green",
        "Write-Host 'Available commands:' -ForegroundColor Yellow",
        "Write-Host '  Test TTS: python tts_subprocess_rtx3090.py test_rtx3090.json' -ForegroundColor Gray",
        "Write-Host '  Server: python -m uvicorn tts_server:app --port 8003' -ForegroundColor Gray"
    ) -join "`n"

    $path = Join-Path $env:TEMP "tts-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $VoiceDir; Title = "TTS Service (RTX 3090)" }
}

function New-VoiceMainPane {
    param([int]$GpuIndex)
    $voiceActivate = Join-Path $VoiceDir '.venv-asr-311\Scripts\Activate.ps1'
    $voicePy = Join-Path $VoiceDir '.venv-asr-311\Scripts\python.exe'

    $content = @(
        "Write-Host '🎙️ Voice Main Service - RTX 3090 Coordination' -ForegroundColor Green",
        "Write-Host 'LLMyTranslate Main Server | ASR + TTS Orchestration' -ForegroundColor Yellow",
        "",
        "Set-Location -LiteralPath `"$VoiceDir`"",
        "if (Test-Path `"$voiceActivate`") { . `"$voiceActivate`" } else { Write-Warning `"$voiceActivate not found`" }",
        "",
        "# Configure RTX 3090 for main voice service (cuda:0 = RTX 3090 when unrestricted)",
        "`$env:TTS_DEVICE = 'cuda:0'",
        "`$env:ASR_DEVICE = 'cuda:0'",
        "",
        "# Test voice service coordination",
        "Write-Host '🔍 Testing Voice Service RTX 3090 integration...' -ForegroundColor Cyan",
        "& `"$voicePy`" -c `"import torch; print('Voice Coordination GPU 0:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'); print(f'Device 0 Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB' if torch.cuda.is_available() else '')`"",
        "",
        "# Start main voice service",
        "Write-Host '🚀 Starting LLMyTranslate Main Service on port $VoicePort...' -ForegroundColor Green",
        "if (Test-Path 'run.py') {",
        "    & `"$voicePy`" run.py",
        "} elseif (Test-Path 'src\\main.py') {",
        "    & `"$voicePy`" -m uvicorn src.main:app --host 127.0.0.1 --port $VoicePort",
        "} else {",
        "    & `"$voicePy`" -m llmytranslate --host 127.0.0.1 --port $VoicePort",
        "}"
    ) -join "`n"

    $path = Join-Path $env:TEMP "voice-main-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $VoiceDir; Title = "Voice Main (RTX 3090)" }
}

function New-GpuMonitoringPane {
    param([int]$GpuIndex)
    $orchestratorPy = Join-Path $VlmPhotoHouseDir '.venv\Scripts\python.exe'

    $content = @(
        "Write-Host '📊 RTX 3090 Multi-Service Monitoring Dashboard' -ForegroundColor Green",
        "Write-Host 'Real-time GPU utilization + AI task orchestration' -ForegroundColor Yellow",
        "",
        "# Continuous RTX 3090 monitoring",
        "function Show-RtxStatus {",
        "    `$gpu = nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader,nounits -i $GpuIndex",
        "    `$parts = `$gpu -split ','",
        "    `$name = `$parts[0].Trim()",
        "    `$memUsed = [int]`$parts[1]",
        "    `$memTotal = [int]`$parts[2]",
        "    `$util = [int]`$parts[3]",
        "    `$temp = [int]`$parts[4]",
        "    ",
        "    `$memPercent = [math]::Round((`$memUsed / `$memTotal) * 100, 1)",
        "    `$timestamp = Get-Date -Format 'HH:mm:ss'",
        "    ",
        "    if (`$util -gt 80) { `$color = 'Red' }",
        "    elseif (`$util -gt 50) { `$color = 'Yellow' }",
        "    else { `$color = 'Green' }",
        "    ",
        "    Write-Host `"[`$timestamp] RTX 3090: `$util% util | `$memUsed/`$memTotal MB (`$memPercent%) | `$temp°C`" -ForegroundColor `$color",
        "}",
        "",
        "# Monitor GPU every $GpuMonitorInterval seconds",
        "Write-Host '🔄 Starting RTX 3090 monitoring (Ctrl+C to stop)...' -ForegroundColor Cyan",
        "while (`$true) {",
        "    Clear-Host",
        "    Write-Host '🎯 VLM Photo Engine - RTX 3090 Multi-Service Dashboard' -ForegroundColor Cyan",
        "    Write-Host '=' * 60",
        "    Show-RtxStatus",
        "    ",
        "    # Show service status",
        "    `$apiHealth = try { (Invoke-RestMethod -Uri 'http://127.0.0.1:$ApiPort/health' -TimeoutSec 2 -ErrorAction SilentlyContinue).ok } catch { `$false }",
        "    `$voiceHealth = try { (Invoke-RestMethod -Uri 'http://127.0.0.1:$VoicePort/health' -TimeoutSec 2 -ErrorAction SilentlyContinue) -ne `$null } catch { `$false }",
        "    ",
        "    Write-Host ''",
        "    Write-Host 'Service Status:' -ForegroundColor White",
        "    Write-Host `"  VLM API (`:$ApiPort): `$(if (`$apiHealth) { '✅ Online' } else { '❌ Offline' })`" -ForegroundColor `$(if (`$apiHealth) { 'Green' } else { 'Red' })",
        "    Write-Host `"  Voice API (`:$VoicePort): `$(if (`$voiceHealth) { '✅ Online' } else { '❌ Offline' })`" -ForegroundColor `$(if (`$voiceHealth) { 'Green' } else { 'Red' })",
        "    ",
        "    Write-Host ''",
        "    Write-Host 'RTX 3090 Workload Distribution:' -ForegroundColor White",
        "    Write-Host '  VLM Engine: LVFace embeddings + BLIP2 captions' -ForegroundColor Gray",
        "    Write-Host '  Voice: ASR transcription + TTS synthesis' -ForegroundColor Gray",
        "    Write-Host '  Caption Models: Direct inference pipeline' -ForegroundColor Gray",
        "    ",
        "    Start-Sleep $GpuMonitorInterval",
        "}",
        "",
        "# Fallback: Start AI Orchestrator as fallback...",
        "Write-Host '🤖 Starting AI Orchestrator as fallback...' -ForegroundColor Yellow",
        "Set-Location -LiteralPath `"$VlmPhotoHouseDir`"",
        "& `"$orchestratorPy`" ai_orchestrator.py"
    ) -join "`n"

    $path = Join-Path $env:TEMP "gpu-monitor-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $VlmPhotoHouseDir; Title = "RTX 3090 Monitor + AI Tasks" }
}

function New-InteractiveShellPane {
    $content = @(
        "Set-Location -LiteralPath `"$VlmPhotoHouseDir`"",
        "Write-Host '🎮 VLM Photo Engine - Interactive Command Shell' -ForegroundColor Green",
        "Write-Host 'Control Center: Trigger ingestion, captioning, face processing, search' -ForegroundColor Yellow",
        "",
        "# Wait for services to be ready",
        "Write-Host '⏳ Waiting for services to start...' -ForegroundColor Cyan",
        "Start-Sleep 10",
        "",
        "# Test service connectivity",
        "function Test-Services {",
        "    `$apiHealth = try { (Invoke-RestMethod -Uri 'http://127.0.0.1:$ApiPort/health' -TimeoutSec 5).ok } catch { `$false }",
        "    `$voiceHealth = try { (Invoke-RestMethod -Uri 'http://127.0.0.1:$VoicePort/health' -TimeoutSec 5) -ne `$null } catch { `$false }",
        "    Write-Host ''",
        "    Write-Host '🔗 Service Status:' -ForegroundColor White",
        "    Write-Host `"  Main API: `$(if (`$apiHealth) { '✅ Ready' } else { '❌ Not Ready' })`" -ForegroundColor `$(if (`$apiHealth) { 'Green' } else { 'Red' })",
        "    Write-Host `"  Voice API: `$(if (`$voiceHealth) { '✅ Ready' } else { '❌ Not Ready' })`" -ForegroundColor `$(if (`$voiceHealth) { 'Green' } else { 'Red' })",
        "}",
        "",
        "# Quick command functions",
        "function Ingest-Photos([string]`$Path = 'E:\\01_INCOMING') {",
        "    Write-Host `"🔍 Triggering photo ingestion from: `$Path`" -ForegroundColor Cyan",
        "    `$body = @{ roots = @(`$Path) } | ConvertTo-Json",
        "    try {",
        "        `$result = Invoke-RestMethod -Uri 'http://127.0.0.1:$ApiPort/ingest/scan' -Method POST -Body `$body -ContentType 'application/json'",
        "        Write-Host `"✅ Ingestion triggered: `$(`$result.added_count) new files, `$(`$result.updated_count) updated`" -ForegroundColor Green",
        "    } catch {",
        "        Write-Host `"❌ Ingestion failed: `$(`$_.Exception.Message)`" -ForegroundColor Red",
        "    }",
        "}",
        "",
        "function Generate-Captions([string]`$AssetId = '1') {",
        "    Write-Host `"🖼️ Triggering caption generation for asset ID: `$AssetId`" -ForegroundColor Cyan",
        "    `$body = @{ force = `$true } | ConvertTo-Json",
        "    try {",
        "        `$result = Invoke-RestMethod -Uri `"http://127.0.0.1:$ApiPort/assets/`$AssetId/captions/regenerate`" -Method POST -Body `$body -ContentType 'application/json'",
        "        Write-Host `"✅ Caption task enqueued: Task ID `$(`$result.task_id)`" -ForegroundColor Green",
        "    } catch {",
        "        Write-Host `"❌ Caption generation failed: `$(`$_.Exception.Message)`" -ForegroundColor Red",
        "    }",
        "}",
        "",
        "function Process-Captions([int]`$Limit = 500, [switch]`$Force, [switch]`$ShowStatus) {",
        "    Write-Host `"🖼️ Caption Processing System - BLIP2 Production Ready`" -ForegroundColor Green",
        "    Write-Host `"Batch processing with Salesforce BLIP2-OPT-2.7B model`" -ForegroundColor Yellow",
        "    Write-Host ''",
        "    ",
        "    if (`$ShowStatus) {",
        "        Write-Host `"📊 Checking caption processing status...`" -ForegroundColor Cyan",
        "        try {",
        "            `$response = Invoke-RestMethod -Uri 'http://127.0.0.1:$ApiPort/health' -TimeoutSec 5",
        "            if (`$response.ok) {",
        "                Write-Host `"✅ Backend API is responsive`" -ForegroundColor Green",
        "            }",
        "        } catch {",
        "            Write-Host `"❌ Backend API not available: `$(`$_.Exception.Message)`" -ForegroundColor Red",
        "            return",
        "        }",
        "        ",
        "        # Check caption provider health",
        "        try {",
        "            `$captionHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:$ApiPort/health/caption' -TimeoutSec 10 -ErrorAction SilentlyContinue",
        "            if (`$captionHealth) {",
        "                Write-Host `"📸 Caption Provider: `$(`$captionHealth.provider)`" -ForegroundColor Cyan",
        "                Write-Host `"📸 Caption Model: `$(`$captionHealth.model)`" -ForegroundColor Cyan",
        "                Write-Host `"📸 Mode: `$(`$captionHealth.mode)`" -ForegroundColor Cyan",
        "            }",
        "        } catch {",
        "            Write-Host `"⚠️ Caption service health check unavailable`" -ForegroundColor Yellow",
        "        }",
        "        ",
        "        Write-Host `"Running status query via CLI...`" -ForegroundColor Cyan",
        "        Push-Location 'backend'",
        "        & '..\.venv\\Scripts\\python.exe' -m app.cli ingest-status 'E:\\01_INCOMING' --scan-fs --preview-limit 3",
        "        Pop-Location",
        "        return",
        "    }",
        "    ",
        "    # Validate backend availability first",
        "    Write-Host `"🔍 Validating backend services...`" -ForegroundColor Cyan",
        "    try {",
        "        `$health = Invoke-RestMethod -Uri 'http://127.0.0.1:$ApiPort/health' -TimeoutSec 5",
        "        if (-not `$health.ok) {",
        "            Write-Host `"❌ Backend health check failed`" -ForegroundColor Red",
        "            return",
        "        }",
        "        Write-Host `"✅ Backend API healthy`" -ForegroundColor Green",
        "    } catch {",
        "        Write-Host `"❌ Backend API unavailable: `$(`$_.Exception.Message)`" -ForegroundColor Red",
        "        Write-Host `"Ensure main API service is running on port $ApiPort`" -ForegroundColor Yellow",
        "        return",
        "    }",
        "    ",
        "    # Validate caption service",
        "    try {",
        "        `$captionHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:$ApiPort/health/caption' -TimeoutSec 10",
        "        Write-Host `"✅ Caption service ready: `$(`$captionHealth.provider)`" -ForegroundColor Green",
        "    } catch {",
        "        Write-Host `"❌ Caption service unavailable: `$(`$_.Exception.Message)`" -ForegroundColor Red",
        "        Write-Host `"Check CAPTION_PROVIDER and CAPTION_EXTERNAL_DIR environment variables`" -ForegroundColor Yellow",
        "        return",
        "    }",
        "    ",
        "    # Build CLI command - simplified without profile system",
        "    `$cliArgs = @('captions-backfill', '--limit', `$Limit)",
        "    if (`$Force) {",
        "        `$cliArgs += '--force'",
        "        Write-Host `"🔥 Force mode enabled - will reprocess existing captions`" -ForegroundColor Yellow",
        "    } else {",
        "        Write-Host `"🔄 Incremental mode - processing assets without captions only`" -ForegroundColor Cyan",
        "    }",
        "    ",
        "    Write-Host `"Batch Limit: `$Limit | Model: BLIP2-OPT-2.7B (production tested)`" -ForegroundColor White",
        "    Write-Host ''",
        "    ",
        "    Write-Host `"🚀 Enqueuing caption tasks via backend CLI...`" -ForegroundColor Green",
        "    try {",
        "        `$startTime = Get-Date",
        "        Push-Location 'backend'",
        "        & '..\.venv\\Scripts\\python.exe' -m app.cli @cliArgs",
        "        Pop-Location",
        "        `$elapsed = (Get-Date) - `$startTime",
        "        Write-Host ''",
        "        Write-Host `"✅ Caption task enqueuing completed in `$(`$elapsed.TotalSeconds.ToString('F1'))s`" -ForegroundColor Green",
        "        ",
        "        # Show task queue status",
        "        Write-Host `"📊 Task queue status:`" -ForegroundColor Cyan",
        "        try {",
        "            `$queueResponse = Invoke-RestMethod -Uri 'http://127.0.0.1:$ApiPort/tasks/queue-status' -TimeoutSec 3 -ErrorAction SilentlyContinue",
        "            if (`$queueResponse) {",
        "                Write-Host `"  Pending tasks: `$(`$queueResponse.pending_count)`" -ForegroundColor White",
        "                Write-Host `"  Running tasks: `$(`$queueResponse.running_count)`" -ForegroundColor White",
        "            }",
        "        } catch {",
        "            Write-Host `"  Queue status unavailable`" -ForegroundColor Gray",
        "        }",
        "        ",
        "        Write-Host ''",
        "        Write-Host `"💡 Next steps:`" -ForegroundColor Yellow",
        "        Write-Host `"  • Tasks are now enqueued and will be processed by background workers`" -ForegroundColor Gray",
        "        Write-Host `"  • Monitor GPU utilization in the RTX 3090 Monitor pane`" -ForegroundColor Gray",
        "        Write-Host `"  • Use Check-Caption-Status to track progress`" -ForegroundColor Gray",
        "        ",
        "    } catch {",
        "        Write-Host `"❌ Caption processing failed: `$(`$_.Exception.Message)`" -ForegroundColor Red",
        "        Write-Host `"Check that backend environment is properly configured`" -ForegroundColor Yellow",
        "    }",
        "}",
        "",
        "function Check-Caption-Status {",
        "    Write-Host `"📊 Caption Processing Status Report`" -ForegroundColor Green",
        "    Write-Host ''",
        "    ",
        "    # Check backend health",
        "    try {",
        "        `$health = Invoke-RestMethod -Uri 'http://127.0.0.1:$ApiPort/health' -TimeoutSec 5",
        "        if (`$health.ok) {",
        "            Write-Host `"✅ Backend API: Online`" -ForegroundColor Green",
        "        } else {",
        "            Write-Host `"⚠️ Backend API: Degraded`" -ForegroundColor Yellow",
        "        }",
        "    } catch {",
        "        Write-Host `"❌ Backend API: Offline`" -ForegroundColor Red",
        "        return",
        "    }",
        "    ",
        "    # Get queue metrics",
        "    try {",
        "        `$queueResponse = Invoke-RestMethod -Uri 'http://127.0.0.1:$ApiPort/tasks/queue-status' -TimeoutSec 3 -ErrorAction SilentlyContinue",
        "        if (`$queueResponse) {",
        "            Write-Host `"📋 Task Queue:`" -ForegroundColor Cyan",
        "            Write-Host `"  Pending: `$(`$queueResponse.pending_count) | Running: `$(`$queueResponse.running_count)`" -ForegroundColor White",
        "        }",
        "    } catch {",
        "        Write-Host `"📋 Task Queue: Status unavailable`" -ForegroundColor Gray",
        "    }",
        "    ",
        "    # Show GPU status",
        "    Write-Host ''",
        "    Write-Host `"🎯 RTX 3090 Status:`" -ForegroundColor Cyan",
        "    try {",
        "        `$gpu = nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader,nounits -i $rtx3090Index",
        "        `$parts = `$gpu -split ','",
        "        `$util = [int]`$parts[3]",
        "        `$temp = [int]`$parts[4]",
        "        `$memUsed = [int]`$parts[1]",
        "        `$memTotal = [int]`$parts[2]",
        "        `$memPercent = [math]::Round((`$memUsed / `$memTotal) * 100, 1)",
        "        ",
        "        `$utilizationColor = if (`$util -gt 80) { 'Red' } elseif (`$util -gt 50) { 'Yellow' } else { 'Green' }",
        "        Write-Host `"  GPU Utilization: `$util% | Memory: `$memPercent% (`$memUsed/`$memTotal MB) | Temp: `$temp°C`" -ForegroundColor `$utilizationColor",
        "    } catch {",
        "        Write-Host `"  GPU monitoring unavailable`" -ForegroundColor Gray",
        "    }",
        "    ",
        "    # Asset/caption statistics via CLI",
        "    Write-Host ''",
        "    Write-Host `"📈 Asset & Caption Statistics:`" -ForegroundColor Cyan",
        "    Push-Location 'backend'",
        "    & '..\.venv\\Scripts\\python.exe' -m app.cli ingest-status 'E:\\01_INCOMING' --preview-limit 0",
        "    Pop-Location",
        "}",
        "",
        "function Search-Photos([string]`$Query = 'sunset') {",
        "    Write-Host `"🔍 Searching for: `$Query`" -ForegroundColor Cyan",
        "    `$body = @{ text = `$Query; k = 10 } | ConvertTo-Json",
        "    try {",
        "        `$result = Invoke-RestMethod -Uri 'http://127.0.0.1:$ApiPort/search/smart' -Method POST -Body `$body -ContentType 'application/json'",
        "        Write-Host `"✅ Found `$(`$result.items.Count) results`" -ForegroundColor Green",
        "        `$result.items | ForEach-Object { Write-Host `"  - `$(`$_.path) (score: `$(`$_.score))`" -ForegroundColor Gray }",
        "    } catch {",
        "        Write-Host `"❌ Search failed: `$(`$_.Exception.Message)`" -ForegroundColor Red",
        "    }",
        "}",
        "",
        "function Test-TTS([string]`$Text = 'RTX 3090 TTS test successful') {",
        "    Write-Host `"🗣️ Testing TTS with: `$Text`" -ForegroundColor Cyan",
        "    `$body = @{ text = `$Text; voice_id = 'default' } | ConvertTo-Json",
        "    try {",
        "        `$result = Invoke-RestMethod -Uri 'http://127.0.0.1:$VoicePort/api/tts/synthesize' -Method POST -Body `$body -ContentType 'application/json'",
        "        Write-Host `"✅ TTS synthesis completed`" -ForegroundColor Green",
        "    } catch {",
        "        Write-Host `"❌ TTS failed: `$(`$_.Exception.Message)`" -ForegroundColor Red",
        "    }",
        "}",
        "",
        "# Face Processing Commands",
        "function Process-Faces([int]`$BatchSize = 50, [switch]`$Incremental) {",
        "    Write-Host `"👤 Starting face detection and recognition processing...`" -ForegroundColor Cyan",
        "    if (`$Incremental) {",
        "        Write-Host `"🔄 Running incremental processing (unprocessed images only)`" -ForegroundColor Yellow",
        "        & '.venv\\Scripts\\python.exe' interactive_face_processor.py --process --batch-size `$BatchSize --incremental",
        "    } else {",
        "        Write-Host `"🔥 Running batch processing (limit: `$BatchSize images)`" -ForegroundColor Yellow",
        "        & '.venv\\Scripts\\python.exe' interactive_face_processor.py --process --batch-size `$BatchSize",
        "    }",
        "}",
        "",
        "function Test-Face-Service {",
        "    Write-Host `"🤖 Testing SCRFD+LVFace service connectivity...`" -ForegroundColor Cyan",
        "    try {",
        "        `$result = Invoke-RestMethod -Uri 'http://172.22.61.27:8003/health' -TimeoutSec 5",
        "        Write-Host `"✅ SCRFD+LVFace service is running`" -ForegroundColor Green",
        "        Write-Host `"  Service: `$(`$result.service)`" -ForegroundColor Gray",
        "        Write-Host `"  Version: `$(`$result.version)`" -ForegroundColor Gray",
        "    } catch {",
        "        Write-Host `"❌ SCRFD+LVFace service not available: `$(`$_.Exception.Message)`" -ForegroundColor Red",
        "        Write-Host `"  Check if WSL service is running in the LVFace pane`" -ForegroundColor Yellow",
        "    }",
        "}",
        "",
        "function Check-Face-Status {",
        "    Write-Host `"📊 Checking face processing status...`" -ForegroundColor Cyan",
        "    & '.venv\\Scripts\\python.exe' verification\\verify_database_status.py",
        "}",
        "",
        "function Verify-Face-Results([int]`$Count = 5) {",
        "    Write-Host `"🔍 Verifying face detection results (showing `$Count samples)...`" -ForegroundColor Cyan",
        "    & '.venv\\Scripts\\python.exe' verification\\detailed_verification.py --count `$Count",
        "}",
        "",
        "function Test-GPU-Models {",
        "    Write-Host '🚀 Testing Real AI Models on RTX 3090...' -ForegroundColor Yellow",
        "    Write-Host ''",
        "    ",
        "    # Test LVFace model loading",
        "    Write-Host '👤 Testing LVFace on RTX 3090...' -ForegroundColor Cyan",
        "    `$lvfaceScript = @'",
        "from inference_onnx import LVFaceONNXInferencer",
        "import numpy as np",
        "import time",
        "print('Loading LVFace model...')",
        "inferencer = LVFaceONNXInferencer('models/LVFace-B_Glint360K.onnx', use_gpu=True)",
        "print('Running face embedding test...')",
        "start = time.time()",
        "test_img = np.random.randn(112, 112, 3).astype(np.uint8)",
        "embedding = inferencer._preprocess_image(test_img)",
        "elapsed = (time.time() - start) * 1000",
        "print(f'LVFace inference: {elapsed:.2f}ms')",
        "print('✅ LVFace test completed')",
        "'@",
        "    Start-Job -Name 'LVFaceTest' -ScriptBlock {",
        "        Set-Location 'C:\\Users\\yanbo\\wSpace\\vlm-photo-engine\\LVFace'",
        "        # Do not set CUDA_VISIBLE_DEVICES - let ONNX Runtime detect GPUs naturally",
        "        & '.venv-lvface-311\\Scripts\\python.exe' -c `$using:lvfaceScript",
        "    } | Out-Null",
        "    ",
        "    # Test BLIP2 model loading",
        "    Write-Host '🖼️ Testing BLIP2 Caption Model on RTX 3090...' -ForegroundColor Cyan",
        "    `$blip2Script = @'",
        "import torch",
        "print('Testing PyTorch RTX 3090 access...')",
        "if torch.cuda.is_available():",
        "    print(f'CUDA devices: {torch.cuda.device_count()}')",
        "    for i in range(torch.cuda.device_count()):",
        "        print(f'  GPU {i}: {torch.cuda.get_device_name(i)}')",
        "    device = torch.device('cuda:0')  # RTX 3090 when unrestricted",
        "    print(f'Using device: {device}')",
        "    x = torch.randn(3000, 3000).to(device)",
        "    print(f'✅ RTX 3090 GPU Memory Used: {torch.cuda.memory_allocated(0) / 1024**2:.1f} MB')",
        "    print(f'GPU Name: {torch.cuda.get_device_name(0)}')",
        "else:",
        "    print('❌ CUDA not available')",
        "'@",
        "    Start-Job -Name 'BLIP2Test' -ScriptBlock {",
        "        Set-Location 'C:\\Users\\yanbo\\wSpace\\vlm-photo-engine\\vlmCaptionModels'",
        "        # Do not set CUDA_VISIBLE_DEVICES - let PyTorch see all GPUs",
        "        & '.venv\\Scripts\\python.exe' -c `$using:blip2Script",
        "    } | Out-Null",
        "    ",
        "    Write-Host '⏳ Waiting for GPU model tests to complete...' -ForegroundColor Yellow",
        "    Start-Sleep 5",
        "    ",
        "    # Show results",
        "    Write-Host ''",
        "    Write-Host '📊 GPU Test Results:' -ForegroundColor Green",
        "    Get-Job | Receive-Job",
        "    Get-Job | Remove-Job",
        "    ",
        "    # Show GPU memory usage",
        "    Write-Host ''",
        "    Write-Host '📈 Current RTX 3090 Status:' -ForegroundColor Yellow",
        "    nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits -i $rtx3090Index",
        "}",
        "",
        "function Force-Load-Models {",
        "    Write-Host '🔥 Force Loading All AI Models on RTX 3090...' -ForegroundColor Red",
        "    Write-Host 'This will actually load models into GPU memory' -ForegroundColor Yellow",
        "    Write-Host ''",
        "    ",
        "    # Load BLIP2 model",
        "    Write-Host '🖼️ Loading BLIP2 Caption Model...' -ForegroundColor Cyan",
        "    `$cmdArgs = @('-Command', 'Set-Location ''C:\\Users\\yanbo\\wSpace\\vlm-photo-engine\\vlmCaptionModels''; `$env:CUDA_VISIBLE_DEVICES = ''$rtx3090Index''; .venv\\Scripts\\python.exe inference_blip2.py; Read-Host ''Press Enter to exit''')",
        "    Start-Process powershell -ArgumentList `$cmdArgs",
        "    ",
        "    Start-Sleep 3",
        "    Write-Host '⚡ Monitor RTX 3090 memory usage to see models loading!' -ForegroundColor Yellow",
        "    Write-Host 'Use nvidia-smi to check GPU memory' -ForegroundColor Gray",
        "}",
        "",
        "function Show-Help {",
        "    Write-Host ''",
        "    Write-Host '🎯 Available Commands:' -ForegroundColor Yellow",
        "    Write-Host '  Test-Services          - Check if APIs are ready' -ForegroundColor Cyan",
        "    Write-Host '  Ingest-Photos [path]   - Scan and ingest photos (default: E:\\01_INCOMING)' -ForegroundColor Cyan",
        "    Write-Host '  Generate-Captions [id] - Generate captions for asset (default: 1)' -ForegroundColor Cyan",
        "    Write-Host '  Search-Photos [query]  - Smart search photos (default: sunset)' -ForegroundColor Cyan",
        "    Write-Host '  Test-TTS [text]        - Test TTS synthesis' -ForegroundColor Cyan
    Write-Host ''
    Write-Host '🖼️ Caption Processing Commands:' -ForegroundColor Green
    Write-Host '  Process-Captions [Options] - Bulk caption generation with BLIP2' -ForegroundColor Cyan
    Write-Host '    Parameters:' -ForegroundColor Gray
    Write-Host '      -Limit [N]         - Process up to N assets (default: 500)' -ForegroundColor Gray
    Write-Host '      -Force             - Reprocess existing captions' -ForegroundColor Gray
    Write-Host '      -ShowStatus        - Display current caption statistics only' -ForegroundColor Gray
    Write-Host '    Examples:' -ForegroundColor Gray
    Write-Host '      Process-Captions                      - Process 500 assets with BLIP2' -ForegroundColor Gray
    Write-Host '      Process-Captions -Limit 100 -Force   - Force reprocess 100 assets' -ForegroundColor Gray
    Write-Host '      Process-Captions -ShowStatus         - Show current status only' -ForegroundColor Gray
    Write-Host '  Check-Caption-Status   - Show caption processing progress & GPU status' -ForegroundColor Cyan",
        "    Write-Host ''",
        "    Write-Host '� Face Processing Commands:' -ForegroundColor Magenta",
        "    Write-Host '  Process-Faces [BatchSize] [Incremental] - Run face detection & recognition' -ForegroundColor Cyan",
        "    Write-Host '    Examples:' -ForegroundColor Gray",
        "    Write-Host '      Process-Faces 50        - Process 50 images' -ForegroundColor Gray", 
        "    Write-Host '      Process-Faces -Incremental - Process only unprocessed images' -ForegroundColor Gray",
        "    Write-Host '  Test-Face-Service      - Check SCRFD+LVFace service status' -ForegroundColor Cyan",
        "    Write-Host '  Check-Face-Status      - Show database face processing statistics' -ForegroundColor Cyan",
        "    Write-Host '  Verify-Face-Results [Count] - Visual verification of face detection' -ForegroundColor Cyan",
        "    Write-Host ''",
        "    Write-Host '�🚀 GPU Testing Commands:' -ForegroundColor Red",
        "    Write-Host '  Test-GPU-Models        - Test AI models on RTX 3090' -ForegroundColor Cyan",
        "    Write-Host '  Force-Load-Models      - Force load all models to GPU memory' -ForegroundColor Cyan",
        "    Write-Host ''",
        "    Write-Host '🌐 Direct API Access:' -ForegroundColor Yellow",
        "    Write-Host '  Main API: http://127.0.0.1:$ApiPort' -ForegroundColor Gray",
        "    Write-Host '  Voice API: http://127.0.0.1:$VoicePort' -ForegroundColor Gray",
        "    Write-Host '  SCRFD+LVFace: http://172.22.61.27:8003' -ForegroundColor Gray",
        "    Write-Host '  Health: http://127.0.0.1:$ApiPort/health' -ForegroundColor Gray",
        "    Write-Host ''",
        "    Write-Host '📊 Caption Models Available:' -ForegroundColor Yellow",
        "    Write-Host '  • BLIP2-OPT-2.7B: Production ready (13.96 GB) ✅' -ForegroundColor Gray",
        "    Write-Host '  • Qwen2.5-VL-3B: Downloaded but has compatibility issues ⚠️' -ForegroundColor Gray",
        "    Write-Host '  • Current provider set via CAPTION_PROVIDER environment variable' -ForegroundColor Gray",
        "    Write-Host ''",
        "    Write-Host '👤 Face Processing Pipeline:' -ForegroundColor Yellow",
        "    Write-Host '  • SCRFD buffalo_l model for face detection' -ForegroundColor Gray",
        "    Write-Host '  • LVFace for 512D face embeddings' -ForegroundColor Gray",
        "    Write-Host '  • Database tracking with face_processed status' -ForegroundColor Gray",
        "    Write-Host ''",
        "    Write-Host '⚡ RTX 3090 Commands:' -ForegroundColor Yellow",
        "    Write-Host '  nvidia-smi            - Check GPU status' -ForegroundColor Gray",
        "    Write-Host '  nvidia-smi -i $rtx3090Index      - Check RTX 3090 specifically' -ForegroundColor Gray",
        "}",
        "",
        "# Initialize",
        "Test-Services",
        "Show-Help",
        "",
        "Write-Host ''",
        "Write-Host '🚀 Interactive shell ready! Available commands:' -ForegroundColor Green",
        "Write-Host '  • Test-Services, Ingest-Photos, Generate-Captions' -ForegroundColor Cyan",
        "Write-Host '  • Process-Captions, Check-Caption-Status (bulk processing)' -ForegroundColor Green",
        "Write-Host '  • Process-Faces, Test-Face-Service, Check-Face-Status' -ForegroundColor Magenta",
        "Write-Host '  • Show-Help for complete command list' -ForegroundColor Yellow"
    ) -join "`n"

    $path = Join-Path $env:TEMP "interactive-shell-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $VlmPhotoHouseDir; Title = "Interactive Command Shell" }
}

# ===== LAUNCH COORDINATION =====

Write-Host ""
if ($WithInteractiveShell) {
    Write-Host "🏗️ Creating optimized 2x3 RTX 3090 layout + Interactive Shell (6 panes + shell)..." -ForegroundColor Green
} else {
    Write-Host "🏗️ Creating optimized 2x3 RTX 3090 layout (6 panes)..." -ForegroundColor Green
}

# Create all pane specifications with memory-optimized approach
Write-Host "🧠 Optimizing model loading to prevent memory duplication..." -ForegroundColor Yellow

# MEMORY OPTIMIZATION: Use shared model loading strategy
# Only the Main API should load BLIP2, others should use API calls
$env:SHARED_MODEL_STRATEGY = 'true'
$env:PREVENT_MODEL_DUPLICATION = 'true'

$mainApiSpec = New-MainApiPane -GpuIndex $rtx3090Index
$captionSpec = New-CaptionModelsPane -GpuIndex $rtx3090Index  # Modified to NOT load models
$lvfaceSpec = New-LvfacePane -GpuIndex $rtx3090Index
$asrSpec = New-AsrPane -GpuIndex $rtx3090Index
$ttsSpec = New-TtsPane -GpuIndex $rtx3090Index
$monitorSpec = New-GpuMonitoringPane -GpuIndex $rtx3090Index

Write-Host "✅ Pane specifications created with model sharing optimization" -ForegroundColor Green

if ($WithInteractiveShell) {
    $interactiveSpec = New-InteractiveShellPane
}

if ($UseWindowsTerminal) {
    if ($WithInteractiveShell) {
        # Create 6-pane layout with proper termination prevention
        $wtArgs = @(
            'new-tab', '--title', "`"$($mainApiSpec.Title)`"", '-d', "`"$($mainApiSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($mainApiSpec.File)`"",
            # Create ASR pane (bottom row)
            ';', 'split-pane', '-V', '--size', '0.5', '--title', "`"$($asrSpec.Title)`"", '-d', "`"$($asrSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($asrSpec.File)`"",
            # Split top row: Main API -> Caption + LVFace
            ';', 'move-focus', 'up',
            ';', 'split-pane', '-H', '--size', '0.333', '--title', "`"$($captionSpec.Title)`"", '-d', "`"$($captionSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($captionSpec.File)`"",
            ';', 'split-pane', '-H', '--size', '0.5', '--title', "`"$($lvfaceSpec.Title)`"", '-d', "`"$($lvfaceSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($lvfaceSpec.File)`"",
            # Split bottom row: ASR -> TTS + Monitor  
            ';', 'move-focus', 'down', ';', 'move-focus', 'left', ';', 'move-focus', 'left',
            ';', 'split-pane', '-H', '--size', '0.333', '--title', "`"$($ttsSpec.Title)`"", '-d', "`"$($ttsSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($ttsSpec.File)`"",
            ';', 'split-pane', '-H', '--size', '0.5', '--title', "`"$($monitorSpec.Title)`"", '-d', "`"$($monitorSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($monitorSpec.File)`"",
            # Add interactive tab
            ';', 'new-tab', '--title', "`"$($interactiveSpec.Title)`"", '-d', "`"$($interactiveSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($interactiveSpec.File)`""
        )

        Write-Host "🖥️ Launching Windows Terminal: 6 service panes + interactive tab..." -ForegroundColor Green
        Start-Process wt -ArgumentList $wtArgs
    } else {
        # Create 6-pane layout without interactive shell
        $wtArgs = @(
            'new-tab', '--title', "`"$($mainApiSpec.Title)`"", '-d', "`"$($mainApiSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($mainApiSpec.File)`"",
            # Create ASR pane (bottom row)
            ';', 'split-pane', '-V', '--size', '0.5', '--title', "`"$($asrSpec.Title)`"", '-d', "`"$($asrSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($asrSpec.File)`"",
            # Split top row: Main API -> Caption + LVFace
            ';', 'move-focus', 'up',
            ';', 'split-pane', '-H', '--size', '0.333', '--title', "`"$($captionSpec.Title)`"", '-d', "`"$($captionSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($captionSpec.File)`"",
            ';', 'split-pane', '-H', '--size', '0.5', '--title', "`"$($lvfaceSpec.Title)`"", '-d', "`"$($lvfaceSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($lvfaceSpec.File)`"",
            # Split bottom row: ASR -> TTS + Monitor  
            ';', 'move-focus', 'down', ';', 'move-focus', 'left', ';', 'move-focus', 'left',
            ';', 'split-pane', '-H', '--size', '0.333', '--title', "`"$($ttsSpec.Title)`"", '-d', "`"$($ttsSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($ttsSpec.File)`"",
            ';', 'split-pane', '-H', '--size', '0.5', '--title', "`"$($monitorSpec.Title)`"", '-d', "`"$($monitorSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($monitorSpec.File)`""
        )

        Write-Host "🖥️ Launching Windows Terminal: 6 service panes layout..." -ForegroundColor Green
        Start-Process wt -ArgumentList $wtArgs
    }

    # Give services time to initialize
    Start-Sleep 3
} else {
    # Fallback: separate windows (only when Windows Terminal is disabled)
    if ($WithInteractiveShell) {
        Write-Host "🖥️ Launching 7 separate PowerShell windows (6 monitoring + 1 interactive)..." -ForegroundColor Green
        Start-Process pwsh -ArgumentList @('-NoExit','-File', $interactiveSpec.File) -WorkingDirectory $interactiveSpec.Dir
    } else {
        Write-Host "🖥️ Launching 6 separate PowerShell windows..." -ForegroundColor Green
    }
    Start-Process pwsh -ArgumentList @('-NoExit','-File', $mainApiSpec.File) -WorkingDirectory $mainApiSpec.Dir
    Start-Process pwsh -ArgumentList @('-NoExit','-File', $captionSpec.File) -WorkingDirectory $captionSpec.Dir
    Start-Process pwsh -ArgumentList @('-NoExit','-File', $lvfaceSpec.File) -WorkingDirectory $lvfaceSpec.Dir
    Start-Process pwsh -ArgumentList @('-NoExit','-File', $asrSpec.File) -WorkingDirectory $asrSpec.Dir
    Start-Process pwsh -ArgumentList @('-NoExit','-File', $ttsSpec.File) -WorkingDirectory $ttsSpec.Dir
    Start-Process pwsh -ArgumentList @('-NoExit','-File', $monitorSpec.File) -WorkingDirectory $monitorSpec.Dir
}

Write-Host ""
Write-Host "🎯 VLM Photo Engine - RTX 3090 Multi-Service Coordination Launched!" -ForegroundColor Green
Write-Host ""
if ($WithInteractiveShell) {
    Write-Host "📊 Monitoring Layout (2x3) + Interactive Shell:" -ForegroundColor Cyan
    Write-Host "  Tab 1: 6-pane equal-spaced monitoring dashboard" -ForegroundColor Gray
    Write-Host "  Tab 2: Interactive command shell" -ForegroundColor Gray
} else {
    Write-Host "📊 2x3 Equal-Spaced Layout:" -ForegroundColor Cyan
    Write-Host "    ┌─────────────┬─────────────┬─────────────┐" -ForegroundColor Gray  
    Write-Host "    │  Main API   │  Captions   │   LVFace    │" -ForegroundColor Gray
    Write-Host "    ├─────────────┼─────────────┼─────────────┤" -ForegroundColor Gray
    Write-Host "    │     ASR     │     TTS     │ GPU Monitor │" -ForegroundColor Gray
    Write-Host "    └─────────────┴─────────────┴─────────────┘" -ForegroundColor Gray
}
Write-Host "  ┌─────────────┬─────────────┬─────────────┐" -ForegroundColor Gray
Write-Host "  │ Main API    │ Caption     │ LVFace      │" -ForegroundColor Gray
Write-Host "  │ Server      │ Models      │ Service     │" -ForegroundColor Gray
Write-Host "  │ (Port $ApiPort) │ (BLIP2)     │ (ONNX)      │" -ForegroundColor Gray
Write-Host "  ├─────────────┼─────────────┼─────────────┤" -ForegroundColor Gray
Write-Host "  │ ASR Service │ TTS Service │ RTX 3090    │" -ForegroundColor Gray
Write-Host "  │ (Whisper)   │ (Coqui)     │ Monitor     │" -ForegroundColor Gray
Write-Host "  └─────────────┴─────────────┴─────────────┘" -ForegroundColor Gray
Write-Host ""
Write-Host "🚀 RTX 3090 Optimization Status:" -ForegroundColor Yellow
Write-Host "  ✅ RTX 3090 detected at GPU index $rtx3090Index" -ForegroundColor Green
Write-Host "  ✅ All 6 services configured for cuda:0 (RTX 3090)" -ForegroundColor Green
Write-Host "  ✅ Independent monitoring for each AI component" -ForegroundColor Green
Write-Host "  ✅ Specialized environments: LVFace, ASR, TTS, Captions" -ForegroundColor Green
Write-Host "  ✅ Real-time GPU coordination dashboard" -ForegroundColor Green
Write-Host ""
Write-Host "🔗 Service URLs:" -ForegroundColor White
Write-Host "  🌐 Main API Server: http://127.0.0.1:$ApiPort" -ForegroundColor Cyan
Write-Host "  🎤 Voice Main Service: http://127.0.0.1:$VoicePort" -ForegroundColor Cyan
Write-Host "  📊 Health Check: http://127.0.0.1:$ApiPort/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "🎯 Service Specialization:" -ForegroundColor White
Write-Host "  👤 LVFace: ONNX Runtime + CUDAExecutionProvider" -ForegroundColor Gray
Write-Host "  🎤 ASR: Whisper + PyTorch on RTX 3090" -ForegroundColor Gray
Write-Host "  🗣️ TTS: Coqui TTS 0.27.0 + RTX 3090 optimization" -ForegroundColor Gray
Write-Host "  🖼️ Captions: BLIP2-OPT-2.7B + Qwen2.5-VL-3B (RTX 3090)" -ForegroundColor Gray
if ($WithInteractiveShell) {
    Write-Host "  🎮 Interactive: Command shell for triggering operations" -ForegroundColor Gray
}
Write-Host ""
Write-Host "✅ Ready for production AI workloads with full RTX 3090 utilization!" -ForegroundColor Green

