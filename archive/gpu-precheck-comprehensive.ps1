param(
    [switch]$SkipTests
)

Write-Host "=== COMPREHENSIVE GPU PRE-CHECK SYSTEM ===" -ForegroundColor Cyan
Write-Host "Verifying RTX 3090 across all environments before AI inference" -ForegroundColor Yellow

# Step 1: nvidia-smi baseline
Write-Host ""
Write-Host "📊 Step 1: nvidia-smi GPU Detection" -ForegroundColor Green
try {
    $gpuInfo = nvidia-smi --query-gpu=index,name,memory.total,memory.used --format=csv,noheader,nounits
    $rtx3090Index = $null
    $quadroIndex = $null
    
    Write-Host "Available GPUs:" -ForegroundColor White
    foreach ($line in $gpuInfo) {
        $parts = $line.Split(',')
        $index = $parts[0].Trim()
        $name = $parts[1].Trim()
        $totalMem = $parts[2].Trim()
        $usedMem = $parts[3].Trim()
        
        Write-Host "  GPU $index`: $name ($totalMem MB total, $usedMem MB used)" -ForegroundColor Cyan
        
        if ($name -like "*RTX 3090*") {
            $rtx3090Index = $index
        } elseif ($name -like "*Quadro*") {
            $quadroIndex = $index
        }
    }
    
    if ($null -eq $rtx3090Index) {
        Write-Host "❌ RTX 3090 not found!" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "🎯 RTX 3090 detected at nvidia-smi index: $rtx3090Index" -ForegroundColor Green
    Write-Host "📋 Quadro detected at nvidia-smi index: $quadroIndex" -ForegroundColor Gray
    
} catch {
    Write-Host "❌ nvidia-smi failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Step 2: Test PyTorch mappings across environments
$environments = @(
    @{
        Name = "Main VLM Environment"
        Python = ".\.venv\Scripts\python.exe"
        Path = "."
    },
    @{
        Name = "LVFace Environment"
        Python = "C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace\.venv-lvface-311\Scripts\python.exe"
        Path = "C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace"
    },
    @{
        Name = "BLIP2 Caption Environment"
        Python = "C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels\.venv\Scripts\python.exe"
        Path = "C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels"
    }
)

# Test script for PyTorch GPU detection
$torchTestScript = @"
import os
import sys

def test_gpu_mapping(cuda_visible_devices):
    os.environ['CUDA_VISIBLE_DEVICES'] = str(cuda_visible_devices)
    
    try:
        import torch
        print(f'CUDA_VISIBLE_DEVICES: {cuda_visible_devices}')
        print(f'PyTorch version: {torch.__version__}')
        print(f'CUDA available: {torch.cuda.is_available()}')
        
        if torch.cuda.is_available():
            count = torch.cuda.device_count()
            print(f'Device count: {count}')
            
            for i in range(count):
                name = torch.cuda.get_device_name(i)
                props = torch.cuda.get_device_properties(i)
                memory_gb = props.total_memory / (1024**3)
                print(f'  cuda:{i} -> {name} ({memory_gb:.1f} GB)')
                
                # Test memory allocation
                try:
                    device = torch.device(f'cuda:{i}')
                    x = torch.randn(100, 100).to(device)
                    print(f'    ✅ Memory allocation successful')
                except Exception as e:
                    print(f'    ❌ Memory allocation failed: {e}')
            
            return True
        else:
            print('❌ CUDA not available')
            return False
            
    except ImportError as e:
        print(f'❌ PyTorch import failed: {e}')
        return False
    except Exception as e:
        print(f'❌ GPU test failed: {e}')
        return False

# Test both configurations
print('=== Testing CUDA_VISIBLE_DEVICES=0 (should show RTX 3090) ===')
rtx_success = test_gpu_mapping('0')

print()
print('=== Testing CUDA_VISIBLE_DEVICES=1 (should show Quadro) ===')  
quadro_success = test_gpu_mapping('1')

print()
if rtx_success:
    print('✅ CUDA_VISIBLE_DEVICES=0 gives RTX 3090 access')
else:
    print('❌ CUDA_VISIBLE_DEVICES=0 failed')
    
print(f'Environment test complete')
"@

Write-Host ""
Write-Host "🧪 Step 2: PyTorch GPU Mapping Tests" -ForegroundColor Green

$testResults = @{}

foreach ($env in $environments) {
    Write-Host ""
    Write-Host "Testing: $($env.Name)" -ForegroundColor Yellow
    
    if (-not (Test-Path $env.Python)) {
        Write-Host "  ❌ Python not found: $($env.Python)" -ForegroundColor Red
        $testResults[$env.Name] = "Missing"
        continue
    }
    
    try {
        Push-Location $env.Path
        $result = & $env.Python -c $torchTestScript 2>&1
        Write-Host $result -ForegroundColor White
        
        if ($result -like "*CUDA_VISIBLE_DEVICES=0 gives RTX 3090*") {
            $testResults[$env.Name] = "Success"
            Write-Host "  ✅ Environment supports RTX 3090" -ForegroundColor Green
        } else {
            $testResults[$env.Name] = "Failed"
            Write-Host "  ❌ Environment has GPU issues" -ForegroundColor Red
        }
    } catch {
        Write-Host "  ❌ Test execution failed: $($_.Exception.Message)" -ForegroundColor Red
        $testResults[$env.Name] = "Error"
    } finally {
        Pop-Location
    }
}

# Step 3: Determine optimal configuration
Write-Host ""
Write-Host "📋 Step 3: Results Summary" -ForegroundColor Green

$allSuccess = $true
foreach ($env in $environments) {
    $status = $testResults[$env.Name]
    $color = switch ($status) {
        "Success" { "Green" }
        "Missing" { "Yellow" }
        default { "Red" }
    }
    Write-Host "  $($env.Name): $status" -ForegroundColor $color
    
    if ($status -ne "Success") {
        $allSuccess = $false
    }
}

Write-Host ""
if ($allSuccess) {
    Write-Host "🎯 OPTIMAL CONFIGURATION DETERMINED:" -ForegroundColor Green
    Write-Host "  CUDA_VISIBLE_DEVICES=0  (for RTX 3090 access)" -ForegroundColor Cyan
    Write-Host "  EMBED_DEVICE=cuda:0     (RTX 3090)" -ForegroundColor Cyan
    Write-Host "  CAPTION_DEVICE=cuda:0   (RTX 3090)" -ForegroundColor Cyan
    
    # Export configuration
    $env:CUDA_VISIBLE_DEVICES = "0"
    $env:EMBED_DEVICE = "cuda:0"
    $env:CAPTION_DEVICE = "cuda:0"
    $env:FACE_EMBED_PROVIDER = "lvface"
    $env:CAPTION_PROVIDER = "blip2"
    $env:LVFACE_EXTERNAL_DIR = "C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace"
    $env:CAPTION_EXTERNAL_DIR = "C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels"
    
    Write-Host ""
    Write-Host "✅ Environment configured for RTX 3090 AI processing!" -ForegroundColor Green
    
} else {
    Write-Host "❌ CONFIGURATION ISSUES DETECTED:" -ForegroundColor Red
    Write-Host "  Some environments cannot access RTX 3090 properly" -ForegroundColor Yellow
    Write-Host "  Review the test results above and fix missing/failed environments" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "💡 Next Steps:" -ForegroundColor Yellow
Write-Host "1. Fix any failed environments above" -ForegroundColor Gray
Write-Host "2. Use CUDA_VISIBLE_DEVICES=0 for RTX 3090 access" -ForegroundColor Gray
Write-Host "3. Start backend with verified configuration" -ForegroundColor Gray
Write-Host "4. Monitor nvidia-smi for actual GPU utilization" -ForegroundColor Gray
