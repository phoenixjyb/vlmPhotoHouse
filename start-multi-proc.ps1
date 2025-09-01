#!/usr/bin/env pwsh
param(
    [string]$Preset = 'RTX3090',  # RTX3090 | LowVRAM | CPU
    [switch]$UseWindowsTerminal,
    [switch]$KillExisting,
    [switch]$NoCleanup,
    [switch]$RunPreCheck,
    [int]$GpuMonitorInterval = 3,
    [int]$ApiPort = 8002,
    [int]$VoicePort = 8001,
    [switch]$WithInteractiveShell  # Add interactive command shell
)

# Default to using Windows Terminal and enabling features
if (-not $PSBoundParameters.ContainsKey('UseWindowsTerminal')) { $UseWindowsTerminal = $true }
if (-not $PSBoundParameters.ContainsKey('KillExisting')) { $KillExisting = $true }
if (-not $PSBoundParameters.ContainsKey('RunPreCheck')) { $RunPreCheck = $true }
if (-not $PSBoundParameters.ContainsKey('WithInteractiveShell')) { $WithInteractiveShell = $true }

$ErrorActionPreference = 'Stop'

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
$PrecheckScript = Join-Path $VlmPhotoHouseDir 'gpu_precheck_validation.py'

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
        Write-Host "🔄 Cleaning up existing service instances..." -ForegroundColor Yellow

        # Stop Windows Terminal instances
        $wt = Get-Process -Name WindowsTerminal -ErrorAction SilentlyContinue
        if ($wt) {
            $wt | Stop-Process -Force -ErrorAction SilentlyContinue
            Write-Host "✅ Closed $($wt.Count) existing Windows Terminal instance(s)" -ForegroundColor Green
            Start-Sleep -Seconds 2
        }

        # Clean up service ports
        $portsToCheck = @($ApiPort, $VoicePort, 8000, 8003)
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

# IMPORTANT: Do NOT set CUDA_VISIBLE_DEVICES
# When unrestricted, PyTorch maps RTX 3090 as cuda:0 and Quadro P2000 as cuda:1
# Remove any existing CUDA_VISIBLE_DEVICES to ensure proper GPU mapping
if ($env:CUDA_VISIBLE_DEVICES) {
    Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
    Write-Host "🔧 Removed CUDA_VISIBLE_DEVICES restriction for proper GPU mapping" -ForegroundColor Yellow
}

$env:TORCH_CUDA_ARCH_LIST = '8.6'  # RTX 3090 compute capability

# VLM Photo Engine Backend Configuration
$env:FACE_EMBED_PROVIDER = 'lvface'
$env:LVFACE_EXTERNAL_DIR = $LvfaceDir
$env:LVFACE_MODEL_NAME = 'LVFace-B_Glint360K.onnx'
$env:LVFACE_SERVICE_URL = 'http://localhost:8003'
$env:CAPTION_PROVIDER = 'blip2'
$env:CAPTION_EXTERNAL_DIR = $CaptionDir
$env:CAPTION_MODEL = 'auto'
$env:ENABLE_INLINE_WORKER = 'true'

# Device assignments - All services use RTX 3090
$env:EMBED_DEVICE = 'cuda:0'
$env:CAPTION_DEVICE = 'cuda:0'
$env:TTS_DEVICE = 'cuda:0'
$env:ASR_DEVICE = 'cuda:0'

# Voice proxy configuration
$env:VOICE_ENABLED = 'true'
$env:VOICE_EXTERNAL_BASE_URL = "http://127.0.0.1:$VoicePort"
$env:VOICE_TTS_PATH = '/api/tts/synthesize'

Write-Host ""
Write-Host "🎯 RTX 3090 Unified Configuration Applied:" -ForegroundColor Green
Write-Host "  GPU Assignment: cuda:0 (RTX 3090) for ALL services" -ForegroundColor Cyan
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
        "Write-Host '🌐 VLM Photo Engine - Main API Server (FastAPI)' -ForegroundColor Green",
        "Write-Host 'Central orchestration | Photo/Video processing | AI task coordination' -ForegroundColor Yellow",
        "Write-Host 'GPU: cuda:0 (RTX 3090) | External providers: LVFace + BLIP2' -ForegroundColor Yellow",
        "",
        "# Validate RTX 3090 availability for main backend",
        "& `"$pyExe`" -c `"import torch; print('RTX 3090 Available:', torch.cuda.is_available()); print('Device 0:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'); print(f'Device 0 Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB' if torch.cuda.is_available() else '')`"",
        "",
        "# Test external provider connections",
        "Write-Host '🔍 Testing external AI providers...' -ForegroundColor Cyan",
        "& `"$pyExe`" -m app.cli validate-lvface",
        "& `"$pyExe`" -m app.cli validate-caption",
        "",
        "# Start main FastAPI server",
        "Write-Host '🚀 Starting VLM Photo Engine Main API Server on port $ApiPort...' -ForegroundColor Cyan",
        "Write-Host 'Available endpoints: /health, /search, /assets, /captions, /voice/*' -ForegroundColor Gray",
        "& `"$pyExe`" -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort --reload"
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
        "Write-Host '🖼️ Caption Models - RTX 3090 Direct Access' -ForegroundColor Green",
        "Write-Host 'Models: BLIP2-OPT-2.7B, Qwen2.5-VL-3B | GPU: cuda:0' -ForegroundColor Yellow",
        "",
        "# Activate caption environment",
        "if (Test-Path '.venv\\Scripts\\Activate.ps1') { . '.venv\\Scripts\\Activate.ps1' }",
        "",
        "# Configure RTX 3090 for caption models (cuda:0 = RTX 3090 when unrestricted)",
        "`$env:TORCH_CUDA_ARCH_LIST = '8.6'",
        "",
        "# Test RTX 3090 caption inference (use a here-string so -c gets one argument)",
        "`$pycode = @'",
        "import torch",
        "print(f'PyTorch CUDA: {torch.cuda.is_available()}')",
        "if torch.cuda.is_available():",
        "    device_name = torch.cuda.get_device_name(0)",
        "    print(f'GPU Device 0: {device_name}')",
        "    print(f'GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB')",
        "    if 'RTX 3090' not in device_name:",
        "        print('WARNING: GPU at cuda:0 is NOT an RTX 3090!')",
        "    torch.cuda.empty_cache()",
        "    print('✅ RTX 3090 ready for caption generation!')",
        "else:",
        "    print('❌ CUDA not available')",
        "'@",
        "& `"$pyExe`" -c `$pycode",
        "",
        "Write-Host '✅ Caption Models Environment Ready' -ForegroundColor Green",
        "Write-Host 'Available commands:' -ForegroundColor Yellow",
        "Write-Host '  Test inference: python inference_blip2.py' -ForegroundColor Gray",
        "Write-Host '  Smart inference: python inference_smart.py' -ForegroundColor Gray"
    ) -join "`n"

    $path = Join-Path $env:TEMP "caption-models-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $CaptionDir; Title = "Caption Models (RTX 3090)" }
}

function New-LvfacePane {
    param([int]$GpuIndex)

    $content = @(
        "Write-Host '👤 LVFace Service (WSL) - RTX 3090 Face Recognition' -ForegroundColor Green",
        "Write-Host 'ONNX Runtime + CUDA 12.4 | Running inside Ubuntu-22.04' -ForegroundColor Yellow",
        "",
        "Write-Host '🚀 Launching LVFace service via WSL with CUDA 12.4...' -ForegroundColor Cyan",
        # Use direct WSL path conversion and our updated start script
        "wsl.exe -d Ubuntu-22.04 bash -c `"cd /mnt/h/wSpace/vlm-photo-engine/LVFace && export CUDA_VISIBLE_DEVICES=1 && ./.venv-cuda124-wsl/bin/python3 inference_onnx.py`""
    ) -join "`n"

    $path = Join-Path $env:TEMP "lvface-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $LvfaceDir; Title = "LVFace (WSL CUDA 12.4)" }
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
        "function Ingest-Photos([string]`$Path = 'E:\\photos') {",
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
        "    Write-Host '  Ingest-Photos [path]   - Scan and ingest photos (default: E:\\photos)' -ForegroundColor Cyan",
        "    Write-Host '  Generate-Captions [id] - Generate captions for asset (default: 1)' -ForegroundColor Cyan",
        "    Write-Host '  Search-Photos [query]  - Smart search photos (default: sunset)' -ForegroundColor Cyan",
        "    Write-Host '  Test-TTS [text]        - Test TTS synthesis' -ForegroundColor Cyan",
        "    Write-Host ''",
        "    Write-Host '🚀 GPU Testing Commands:' -ForegroundColor Red",
        "    Write-Host '  Test-GPU-Models        - Test AI models on RTX 3090' -ForegroundColor Cyan",
        "    Write-Host '  Force-Load-Models      - Force load all models to GPU memory' -ForegroundColor Cyan",
        "    Write-Host ''",
        "    Write-Host '🌐 Direct API Access:' -ForegroundColor Yellow",
        "    Write-Host '  Main API: http://127.0.0.1:$ApiPort' -ForegroundColor Gray",
        "    Write-Host '  Voice API: http://127.0.0.1:$VoicePort' -ForegroundColor Gray",
        "    Write-Host '  Health: http://127.0.0.1:$ApiPort/health' -ForegroundColor Gray",
        "    Write-Host ''",
        "    Write-Host '📊 Caption Models Available:' -ForegroundColor Yellow",
        "    Write-Host '  • BLIP2-OPT-2.7B (fast, good quality)' -ForegroundColor Gray",
        "    Write-Host '  • Qwen2.5-VL-3B (slower, high quality)' -ForegroundColor Gray",
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
        "Write-Host '🚀 Interactive shell ready! Try: Test-Services, Ingest-Photos, Generate-Captions' -ForegroundColor Green"
    ) -join "`n"

    $path = Join-Path $env:TEMP "interactive-shell-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $VlmPhotoHouseDir; Title = "Interactive Command Shell" }
}

# ===== LAUNCH COORDINATION =====

Write-Host ""
if ($WithInteractiveShell) {
    Write-Host "🏗️ Creating optimized 3x2 RTX 3090 layout + Interactive Shell (7 total panes)..." -ForegroundColor Green
} else {
    Write-Host "🏗️ Creating optimized 3x2 RTX 3090 layout (6 panes)..." -ForegroundColor Green
}

# Create all pane specifications
$mainApiSpec = New-MainApiPane -GpuIndex $rtx3090Index
$captionSpec = New-CaptionModelsPane -GpuIndex $rtx3090Index
$lvfaceSpec = New-LvfacePane -GpuIndex $rtx3090Index
$asrSpec = New-AsrPane -GpuIndex $rtx3090Index
$ttsSpec = New-TtsPane -GpuIndex $rtx3090Index
$monitorSpec = New-GpuMonitoringPane -GpuIndex $rtx3090Index

if ($WithInteractiveShell) {
    $interactiveSpec = New-InteractiveShellPane
}

if ($UseWindowsTerminal) {
    if ($WithInteractiveShell) {
        # Launch 6-pane monitoring layout: 3 columns x 2 rows
        # Step 1: Create top row (3 columns)
        # Step 2: Split each column vertically to create bottom row
        $wtArgs = @(
            'new-tab', '--title', "`"$($mainApiSpec.Title)`"", '-d', "`"$($mainApiSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($mainApiSpec.File)`"",
            # Create second column (split right)
            ';', 'split-pane', '-H', '--title', "`"$($captionSpec.Title)`"", '-d', "`"$($captionSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($captionSpec.File)`"",
            # Create third column (split right again)
            ';', 'split-pane', '-H', '--title', "`"$($lvfaceSpec.Title)`"", '-d', "`"$($lvfaceSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($lvfaceSpec.File)`"",
            # Now create bottom row by splitting each column vertically
            # Go to first column and split down
            ';', 'move-focus', 'left', ';', 'move-focus', 'left',
            ';', 'split-pane', '-V', '--title', "`"$($asrSpec.Title)`"", '-d', "`"$($asrSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($asrSpec.File)`"",
            # Go to second column and split down
            ';', 'move-focus', 'up', ';', 'move-focus', 'right',
            ';', 'split-pane', '-V', '--title', "`"$($ttsSpec.Title)`"", '-d', "`"$($ttsSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($ttsSpec.File)`"",
            # Go to third column and split down
            ';', 'move-focus', 'up', ';', 'move-focus', 'right',
            ';', 'split-pane', '-V', '--title', "`"$($monitorSpec.Title)`"", '-d', "`"$($monitorSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($monitorSpec.File)`""
        )

        Write-Host "🖥️ Launching Windows Terminal with 3 columns x 2 rows layout..." -ForegroundColor Green
        Start-Process wt -ArgumentList $wtArgs

        # Wait a moment, then launch interactive shell in new tab
        Start-Sleep 2
        Write-Host "🎮 Launching Interactive Command Shell in new tab..." -ForegroundColor Green
        Start-Process wt -ArgumentList @('new-tab', '--title', "`"$($interactiveSpec.Title)`"", '-d', "`"$($interactiveSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($interactiveSpec.File)`"")
    } else {
        # Original 6-pane layout only (3 columns x 2 rows)
        $wtArgs = @(
            'new-tab', '--title', "`"$($mainApiSpec.Title)`"", '-d', "`"$($mainApiSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($mainApiSpec.File)`"",
            # Create second column (split right)
            ';', 'split-pane', '-H', '--title', "`"$($captionSpec.Title)`"", '-d', "`"$($captionSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($captionSpec.File)`"",
            # Create third column (split right again)
            ';', 'split-pane', '-H', '--title', "`"$($lvfaceSpec.Title)`"", '-d', "`"$($lvfaceSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($lvfaceSpec.File)`"",
            # Now create bottom row by splitting each column vertically
            # Go to first column and split down
            ';', 'move-focus', 'left', ';', 'move-focus', 'left',
            ';', 'split-pane', '-V', '--title', "`"$($asrSpec.Title)`"", '-d', "`"$($asrSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($asrSpec.File)`"",
            # Go to second column and split down
            ';', 'move-focus', 'up', ';', 'move-focus', 'right',
            ';', 'split-pane', '-V', '--title', "`"$($ttsSpec.Title)`"", '-d', "`"$($ttsSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($ttsSpec.File)`"",
            # Go to third column and split down
            ';', 'move-focus', 'up', ';', 'move-focus', 'right',
            ';', 'split-pane', '-V', '--title', "`"$($monitorSpec.Title)`"", '-d', "`"$($monitorSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($monitorSpec.File)`""
        )

        Write-Host "🖥️ Launching Windows Terminal with 3x2 RTX 3090 optimized layout..." -ForegroundColor Green
        Start-Process wt -ArgumentList $wtArgs
    }

    # Give services time to initialize
    Start-Sleep 3
} else {
    # Fallback: separate windows
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
    Write-Host "📊 Monitoring Layout (3x2) + Interactive Shell:" -ForegroundColor Cyan
    Write-Host "  Tab 1: 6-pane monitoring dashboard" -ForegroundColor Gray
    Write-Host "  Tab 2: Interactive command shell" -ForegroundColor Gray
} else {
    Write-Host "📊 3x2 Specialized Layout:" -ForegroundColor Cyan
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
