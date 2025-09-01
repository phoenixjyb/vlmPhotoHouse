param(
    [switch]$TestOnly
)

Write-Host "=== DYNAMIC RTX 3090 GPU DETECTION ===" -ForegroundColor Cyan

# Function to detect RTX 3090 GPU ID
function Get-RTX3090-GpuId {
    try {
        $gpuInfo = nvidia-smi --query-gpu=index,name --format=csv,noheader,nounits
        foreach ($line in $gpuInfo) {
            $parts = $line.Split(',')
            $index = $parts[0].Trim()
            $name = $parts[1].Trim()
            
            if ($name -like "*RTX 3090*") {
                Write-Host "🎯 Found RTX 3090 at GPU index: $index" -ForegroundColor Green
                return $index
            }
        }
        Write-Host "❌ RTX 3090 not found!" -ForegroundColor Red
        return $null
    } catch {
        Write-Host "❌ Error detecting GPU: $($_.Exception.Message)" -ForegroundColor Red
        return $null
    }
}

# Detect RTX 3090
$rtx3090Id = Get-RTX3090-GpuId
if ($null -eq $rtx3090Id) {
    Write-Host "❌ Cannot proceed without RTX 3090 detection" -ForegroundColor Red
    exit 1
}

Write-Host "🔧 Configuring for RTX 3090 at GPU $rtx3090Id..." -ForegroundColor Yellow

# Dynamic GPU Configuration
$env:CUDA_VISIBLE_DEVICES = $rtx3090Id.ToString()  # Make RTX 3090 the only visible GPU
$env:EMBED_DEVICE = 'cuda:0'                       # First (and only) visible GPU
$env:CAPTION_DEVICE = 'cuda:0'                     # First (and only) visible GPU
$env:FACE_EMBED_PROVIDER = 'lvface'
$env:CAPTION_PROVIDER = 'blip2'
$env:LVFACE_EXTERNAL_DIR = 'C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace'
$env:CAPTION_EXTERNAL_DIR = 'C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels'
$env:LVFACE_MODEL_NAME = 'LVFace-B_Glint360K.onnx'
$env:CAPTION_MODEL = 'auto'

Write-Host ""
Write-Host "🎯 Dynamic GPU Configuration Applied:" -ForegroundColor Green
Write-Host "  RTX 3090 Physical Index: $rtx3090Id" -ForegroundColor Cyan
Write-Host "  CUDA_VISIBLE_DEVICES: $($env:CUDA_VISIBLE_DEVICES) (hide other GPUs)" -ForegroundColor Cyan
Write-Host "  EMBED_DEVICE: $($env:EMBED_DEVICE) (RTX 3090 as cuda:0)" -ForegroundColor Cyan
Write-Host "  CAPTION_DEVICE: $($env:CAPTION_DEVICE) (RTX 3090 as cuda:0)" -ForegroundColor Cyan

# Verify GPU visibility
Write-Host ""
Write-Host "🔍 Verifying GPU Visibility..." -ForegroundColor Yellow
try {
    $visibleGpus = $env:CUDA_VISIBLE_DEVICES
    Write-Host "✅ CUDA will see GPU $visibleGpus as cuda:0 (RTX 3090)" -ForegroundColor Green
} catch {
    Write-Host "❌ GPU verification failed" -ForegroundColor Red
}

# Test external model paths
Write-Host ""
Write-Host "🔍 Testing External Model Paths..." -ForegroundColor Yellow

# LVFace test
$lvfaceDir = $env:LVFACE_EXTERNAL_DIR
$lvfaceVenv = Join-Path $lvfaceDir ".venv-lvface-311\Scripts\python.exe"
$lvfaceInference = Join-Path $lvfaceDir "inference.py"

Write-Host "LVFace Configuration:" -ForegroundColor White
if (Test-Path $lvfaceDir) {
    Write-Host "  ✅ Directory: $lvfaceDir" -ForegroundColor Green
    if (Test-Path $lvfaceVenv) {
        Write-Host "  ✅ Python: $lvfaceVenv" -ForegroundColor Green
        if (Test-Path $lvfaceInference) {
            Write-Host "  ✅ Inference: $lvfaceInference" -ForegroundColor Green
        } else {
            Write-Host "  ❌ Missing: $lvfaceInference" -ForegroundColor Red
        }
    } else {
        Write-Host "  ❌ Missing venv: $lvfaceVenv" -ForegroundColor Red
    }
} else {
    Write-Host "  ❌ Missing directory: $lvfaceDir" -ForegroundColor Red
}

# Caption test
$captionDir = $env:CAPTION_EXTERNAL_DIR
$captionVenv = Join-Path $captionDir ".venv\Scripts\python.exe"
$captionInference = Join-Path $captionDir "inference_backend.py"

Write-Host "BLIP2 Configuration:" -ForegroundColor White
if (Test-Path $captionDir) {
    Write-Host "  ✅ Directory: $captionDir" -ForegroundColor Green
    if (Test-Path $captionVenv) {
        Write-Host "  ✅ Python: $captionVenv" -ForegroundColor Green
        if (Test-Path $captionInference) {
            Write-Host "  ✅ Inference: $captionInference" -ForegroundColor Green
        } else {
            Write-Host "  ❌ Missing: $captionInference" -ForegroundColor Red
        }
    } else {
        Write-Host "  ❌ Missing venv: $captionVenv" -ForegroundColor Red
    }
} else {
    Write-Host "  ❌ Missing directory: $captionDir" -ForegroundColor Red
}

if (-not $TestOnly) {
    Write-Host ""
    Write-Host "🚀 Testing GPU Model Loading..." -ForegroundColor Yellow
    
    # Test LVFace GPU loading
    if ((Test-Path $lvfaceVenv) -and (Test-Path $lvfaceInference)) {
        Write-Host "Testing LVFace on RTX 3090..." -ForegroundColor Cyan
        try {
            $result = & $lvfaceVenv $lvfaceInference --device cuda:0 --test 2>&1
            Write-Host "LVFace test result: $result" -ForegroundColor White
        } catch {
            Write-Host "LVFace test failed: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    
    # Test BLIP2 GPU loading
    if ((Test-Path $captionVenv) -and (Test-Path $captionInference)) {
        Write-Host "Testing BLIP2 on RTX 3090..." -ForegroundColor Cyan
        try {
            $result = & $captionVenv $captionInference --device cuda:0 --test 2>&1
            Write-Host "BLIP2 test result: $result" -ForegroundColor White
        } catch {
            Write-Host "BLIP2 test failed: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "📋 Environment Variables Set:" -ForegroundColor Yellow
Write-Host "  CUDA_VISIBLE_DEVICES=$($env:CUDA_VISIBLE_DEVICES)" -ForegroundColor Gray
Write-Host "  EMBED_DEVICE=$($env:EMBED_DEVICE)" -ForegroundColor Gray
Write-Host "  CAPTION_DEVICE=$($env:CAPTION_DEVICE)" -ForegroundColor Gray
Write-Host "  FACE_EMBED_PROVIDER=$($env:FACE_EMBED_PROVIDER)" -ForegroundColor Gray
Write-Host "  CAPTION_PROVIDER=$($env:CAPTION_PROVIDER)" -ForegroundColor Gray

Write-Host ""
Write-Host "🎯 Ready to use RTX 3090 for AI processing!" -ForegroundColor Green
