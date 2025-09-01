param(
    [switch]$TestOnly
)

Write-Host "=== RTX 3090 EXTERNAL MODEL CONFIGURATION ===" -ForegroundColor Cyan

# RTX 3090 Configuration (following start-dev-multiproc pattern)
$env:CUDA_VISIBLE_DEVICES = '0'  # Make RTX 3090 the primary GPU (index 0)
$env:EMBED_DEVICE = 'cuda:0'     # RTX 3090 as cuda:0
$env:CAPTION_DEVICE = 'cuda:0'   # RTX 3090 as cuda:0
$env:FACE_EMBED_PROVIDER = 'lvface'
$env:CAPTION_PROVIDER = 'blip2'
$env:LVFACE_EXTERNAL_DIR = 'C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace'
$env:CAPTION_EXTERNAL_DIR = 'C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels'
$env:LVFACE_MODEL_NAME = 'LVFace-B_Glint360K.onnx'
$env:CAPTION_MODEL = 'auto'

Write-Host "🎯 Configuration:" -ForegroundColor Green
Write-Host "  CUDA_VISIBLE_DEVICES: $($env:CUDA_VISIBLE_DEVICES) (RTX 3090 as primary)" -ForegroundColor Cyan
Write-Host "  EMBED_DEVICE: $($env:EMBED_DEVICE)" -ForegroundColor Cyan
Write-Host "  CAPTION_DEVICE: $($env:CAPTION_DEVICE)" -ForegroundColor Cyan
Write-Host "  LVFace Dir: $($env:LVFACE_EXTERNAL_DIR)" -ForegroundColor Cyan
Write-Host "  Caption Dir: $($env:CAPTION_EXTERNAL_DIR)" -ForegroundColor Cyan

# Test LVFace configuration
Write-Host ""
Write-Host "🔍 Testing LVFace Configuration..." -ForegroundColor Yellow
$lvfaceDir = $env:LVFACE_EXTERNAL_DIR
$lvfaceVenv = Join-Path $lvfaceDir ".venv-lvface-311\Scripts\python.exe"
$lvfaceInference = Join-Path $lvfaceDir "inference.py"

if (Test-Path $lvfaceDir) {
    Write-Host "✅ LVFace directory exists: $lvfaceDir" -ForegroundColor Green
    
    if (Test-Path $lvfaceVenv) {
        Write-Host "✅ LVFace venv exists: $lvfaceVenv" -ForegroundColor Green
        
        if (Test-Path $lvfaceInference) {
            Write-Host "✅ LVFace inference.py exists" -ForegroundColor Green
            
            if (-not $TestOnly) {
                Write-Host "🚀 Testing LVFace GPU loading..." -ForegroundColor Yellow
                & $lvfaceVenv $lvfaceInference --test-gpu --device cuda:0
            }
        } else {
            Write-Host "❌ LVFace inference.py missing: $lvfaceInference" -ForegroundColor Red
        }
    } else {
        Write-Host "❌ LVFace venv missing: $lvfaceVenv" -ForegroundColor Red
    }
} else {
    Write-Host "❌ LVFace directory missing: $lvfaceDir" -ForegroundColor Red
}

# Test Caption configuration  
Write-Host ""
Write-Host "🔍 Testing BLIP2 Configuration..." -ForegroundColor Yellow
$captionDir = $env:CAPTION_EXTERNAL_DIR
$captionVenv = Join-Path $captionDir ".venv\Scripts\python.exe"
$captionInference = Join-Path $captionDir "inference_backend.py"

if (Test-Path $captionDir) {
    Write-Host "✅ Caption directory exists: $captionDir" -ForegroundColor Green
    
    if (Test-Path $captionVenv) {
        Write-Host "✅ Caption venv exists: $captionVenv" -ForegroundColor Green
        
        if (Test-Path $captionInference) {
            Write-Host "✅ Caption inference_backend.py exists" -ForegroundColor Green
            
            if (-not $TestOnly) {
                Write-Host "🚀 Testing BLIP2 GPU loading..." -ForegroundColor Yellow
                $env:DEVICE = 'cuda:0'
                & $captionVenv $captionInference --test-gpu
            }
        } else {
            Write-Host "❌ Caption inference_backend.py missing: $captionInference" -ForegroundColor Red
        }
    } else {
        Write-Host "❌ Caption venv missing: $captionVenv" -ForegroundColor Red
    }
} else {
    Write-Host "❌ Caption directory missing: $captionDir" -ForegroundColor Red
}

Write-Host ""
Write-Host "💡 Next Steps:" -ForegroundColor Yellow
Write-Host "1. Fix any missing components above" -ForegroundColor Gray
Write-Host "2. Run this script without -TestOnly to test GPU loading" -ForegroundColor Gray
Write-Host "3. Update start-ai-monitoring.ps1 with correct CUDA_VISIBLE_DEVICES=0" -ForegroundColor Gray
Write-Host "4. Restart backend with corrected configuration" -ForegroundColor Gray
