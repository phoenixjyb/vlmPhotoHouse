#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Configure GPU environment for RTX 3090 usage
.DESCRIPTION
    Sets environment variables to force all GPU-intensive tasks to use RTX 3090
    while leaving P2000 free for display and system tasks.
.PARAMETER GpuDevice
    GPU device ID to use (default: auto-detect RTX 3090)
.PARAMETER Persistent
    Make environment changes persistent for current session
#>

param(
    [int]$GpuDevice = -1,  # Auto-detect by default
    [switch]$Persistent = $false
)

Write-Host "🎯 GPU Environment Configuration Tool" -ForegroundColor Cyan
Write-Host "Purpose: Force RTX 3090 usage, keep P2000 for display" -ForegroundColor Yellow
Write-Host ""

# Auto-detect RTX 3090 if not specified
if ($GpuDevice -eq -1) {
    Write-Host "🔍 Auto-detecting RTX 3090..." -ForegroundColor Green
    
    try {
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
        
        $GpuDevice = $rtx3090Index
        Write-Host "✅ RTX 3090 detected at nvidia-smi GPU index: $GpuDevice" -ForegroundColor Green
        
        # CRITICAL: Cross-validate with PyTorch device mapping
        Write-Host "🔍 Cross-validating with PyTorch device mapping..." -ForegroundColor Yellow
        try {
            # This requires Python/PyTorch to be available
            $pytorchMapping = python -c "import torch; [print(f'{i}:{torch.cuda.get_device_name(i)}') for i in range(torch.cuda.device_count())]" 2>$null
            if ($pytorchMapping) {
                Write-Host "PyTorch device mapping:" -ForegroundColor Gray
                $pytorchRTX3090Index = -1
                $pytorchMapping | ForEach-Object {
                    $parts = $_ -split ":"
                    $torchIndex = [int]$parts[0]
                    $torchName = $parts[1]
                    
                    if ($torchName -match "RTX 3090") {
                        $pytorchRTX3090Index = $torchIndex
                        Write-Host "  🎯 PyTorch cuda:$torchIndex = $torchName" -ForegroundColor Green
                    } else {
                        Write-Host "  ⚪ PyTorch cuda:$torchIndex = $torchName" -ForegroundColor Gray
                    }
                }
                
                if ($pytorchRTX3090Index -ne $rtx3090Index) {
                    Write-Host "⚠️  WARNING: Device index mismatch!" -ForegroundColor Yellow
                    Write-Host "  nvidia-smi index: $rtx3090Index" -ForegroundColor Yellow
                    Write-Host "  PyTorch index: $pytorchRTX3090Index" -ForegroundColor Yellow
                    Write-Host "  Using PyTorch index for compatibility: $pytorchRTX3090Index" -ForegroundColor Yellow
                    $GpuDevice = $pytorchRTX3090Index
                }
            }
        } catch {
            Write-Host "⚠️  Could not cross-validate with PyTorch (PyTorch may not be installed)" -ForegroundColor Yellow
        }
        
    } catch {
        Write-Host "❌ Error detecting GPU: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

# Display current GPU status
Write-Host ""
Write-Host "📊 Current GPU Status:" -ForegroundColor Cyan
try {
    $gpuInfo = nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free --format=csv,noheader,nounits
    $gpuLines = $gpuInfo -split "`n"
    
    foreach ($line in $gpuLines) {
        if ($line.Trim()) {
            $parts = $line -split ","
            $index = $parts[0].Trim()
            $name = $parts[1].Trim()
            $total = $parts[2].Trim()
            $used = $parts[3].Trim()
            $free = $parts[4].Trim()
            
            $color = if ($index -eq $GpuDevice) { "Green" } else { "Gray" }
            $indicator = if ($index -eq $GpuDevice) { "🎯" } else { "⚪" }
            
            Write-Host "  $indicator GPU $index`: $name" -ForegroundColor $color
            Write-Host "    Memory: ${used}MB/${total}MB used (${free}MB free)" -ForegroundColor $color
        }
    }
} catch {
    Write-Host "⚠️  Could not get GPU status" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🔧 Setting GPU Environment Variables:" -ForegroundColor Green

# Set environment variables
$envVars = @{
    "PYTORCH_CUDA_DEVICE" = "$GpuDevice"
    "CUDA_DEVICE_ORDER" = "PCI_BUS_ID"
    "TORCH_CUDA_ARCH_LIST" = "8.6"  # RTX 3090 compute capability
    "PYTORCH_CUDA_ALLOC_CONF" = "max_split_size_mb:1024,expandable_segments:True"
}

foreach ($var in $envVars.GetEnumerator()) {
    $name = $var.Key
    $value = $var.Value
    
    if ($Persistent) {
        [Environment]::SetEnvironmentVariable($name, $value, "User")
        Write-Host "  ✅ $name = $value (persistent)" -ForegroundColor Green
    } else {
        Set-Item -Path "Env:$name" -Value $value
        Write-Host "  ✅ $name = $value (session)" -ForegroundColor White
    }
}

Write-Host ""
Write-Host "✅ GPU environment configured successfully!" -ForegroundColor Green
Write-Host "🎯 All GPU tasks will now use RTX 3090 (GPU $GpuDevice)" -ForegroundColor Cyan
Write-Host "💡 P2000 (GPU $((1-$GpuDevice))) reserved for display tasks" -ForegroundColor Gray

if (-not $Persistent) {
    Write-Host ""
    Write-Host "⚠️  Note: Changes are for current session only" -ForegroundColor Yellow
    Write-Host "💡 Use -Persistent flag to make changes permanent" -ForegroundColor Gray
}

Write-Host ""
Write-Host "🚀 Ready to launch GPU-intensive processes!" -ForegroundColor Green
