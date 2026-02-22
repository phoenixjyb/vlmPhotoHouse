#!/usr/bin/env pwsh
<#
.SYNOPSIS
    GPU-Optimized Startup Script for VLM Photo Engine
.DESCRIPTION
    Ensures all GPU-intensive services use RTX 3090 while keeping P2000 free for display.
    This script configures the environment before launching the main startup script.
.PARAMETER Preset
    Service preset configuration (RTX3090, LowVRAM, CPU)
.PARAMETER UseWindowsTerminal
    Use Windows Terminal for service windows
.PARAMETER KillExisting
    Kill existing service processes before starting
#>

param(
    [string]$Preset = 'RTX3090',
    [switch]$UseWindowsTerminal,
    [switch]$KillExisting,
    [switch]$NoCleanup = $false,
    [switch]$RunPreCheck
)

Write-Host "🎯 GPU-Optimized VLM Photo Engine Launcher" -ForegroundColor Cyan
Write-Host "Target: RTX 3090 for AI tasks, P2000 for display" -ForegroundColor Yellow
Write-Host ""

# Set default values for switches
if (-not $PSBoundParameters.ContainsKey('UseWindowsTerminal')) { $UseWindowsTerminal = $true }
if (-not $PSBoundParameters.ContainsKey('KillExisting')) { $KillExisting = $true }
if (-not $PSBoundParameters.ContainsKey('RunPreCheck')) { $RunPreCheck = $true }

# Step 1: Configure GPU environment
Write-Host "🔧 Step 1: Configuring GPU environment..." -ForegroundColor Green

try {
    & ".\set-gpu-env.ps1" -Persistent:$false
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ GPU environment configuration failed!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ Error running GPU configuration: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 2: Validate GPU configuration with Python
Write-Host "🔍 Step 2: Validating GPU configuration..." -ForegroundColor Green

try {
    $pythonExe = ".\.venv\Scripts\python.exe"
    if (Test-Path $pythonExe) {
        # Run comprehensive GPU validation
        Write-Host "  📊 Running GPU device mapping validation..." -ForegroundColor Gray
        $gpuValidation = & $pythonExe ".\tools\configure_gpu.py" --status 2>&1
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Python GPU validation failed!" -ForegroundColor Red
            Write-Host "GPU validation output:" -ForegroundColor Yellow
            Write-Host $gpuValidation -ForegroundColor Yellow
            exit 1
        }
        
        # Additional cross-check: Verify RTX 3090 is at expected PyTorch device
        Write-Host "  🔍 Cross-checking PyTorch device mapping..." -ForegroundColor Gray
        $pytorchCheck = & $pythonExe -c "import torch; print(f'PyTorch CUDA available: {torch.cuda.is_available()}'); [print(f'cuda:{i} = {torch.cuda.get_device_name(i)}') for i in range(torch.cuda.device_count())] if torch.cuda.is_available() else None" 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✅ PyTorch device mapping:" -ForegroundColor Green
            $pytorchCheck | ForEach-Object {
                if ($_ -match "cuda:(\d+) = (.*)RTX 3090") {
                    Write-Host "    🎯 $_ (Target device)" -ForegroundColor Green
                } elseif ($_ -match "cuda:(\d+) = (.*)") {
                    Write-Host "    ⚪ $_" -ForegroundColor Gray
                } else {
                    Write-Host "    $_" -ForegroundColor Gray
                }
            }
        } else {
            Write-Host "  ⚠️ Could not verify PyTorch device mapping" -ForegroundColor Yellow
        }
        
        # Final validation: Test inference script GPU detection
        Write-Host "  🧪 Testing inference script GPU detection..." -ForegroundColor Gray
        $inferenceTest = & $pythonExe -c "import sys; sys.path.insert(0, 'C:/Users/yanbo/wSpace/vlm-photo-engine/vlmCaptionModels'); from inference import _gpu_device, validate_rtx3090_usage; print(f'Inference script detected RTX 3090 at: cuda:{_gpu_device}'); validate_rtx3090_usage(); print('✅ Inference validation passed')" 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✅ Inference script validation passed" -ForegroundColor Green
        } else {
            Write-Host "  ❌ Inference script validation failed!" -ForegroundColor Red
            Write-Host "$inferenceTest" -ForegroundColor Yellow
            exit 1
        }
        
    } else {
        Write-Host "⚠️  Python virtual environment not found, skipping Python GPU validation" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  Could not validate GPU configuration with Python: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""

# Step 3: Launch main startup script with GPU-optimized settings
Write-Host "🚀 Step 3: Launching multi-service startup..." -ForegroundColor Green

$startupParams = @{
    'Preset' = $Preset
    'UseWindowsTerminal' = $UseWindowsTerminal
    'KillExisting' = $KillExisting
    'NoCleanup' = $NoCleanup
    'RunPreCheck' = $RunPreCheck
}

try {
    & ".\start-multi-proc.ps1" @startupParams
} catch {
    Write-Host "❌ Error launching services: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅ GPU-optimized services launched successfully!" -ForegroundColor Green
Write-Host "🎯 RTX 3090: AI processing tasks" -ForegroundColor Cyan
Write-Host "💻 P2000: Display and system tasks" -ForegroundColor Gray
