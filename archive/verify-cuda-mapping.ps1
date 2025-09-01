param(
    [string]$PhysicalGpuId = "1"  # RTX 3090 physical ID
)

Write-Host "=== CUDA DEVICE MAPPING VERIFICATION ===" -ForegroundColor Cyan

# Set CUDA_VISIBLE_DEVICES to only show RTX 3090
$env:CUDA_VISIBLE_DEVICES = $PhysicalGpuId
Write-Host "🔧 Set CUDA_VISIBLE_DEVICES=$PhysicalGpuId (RTX 3090 only)" -ForegroundColor Yellow

# Test what CUDA sees
Write-Host ""
Write-Host "🔍 Testing CUDA device mapping..." -ForegroundColor Yellow

$testScript = @"
import os
print(f"CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES', 'Not set')}")

try:
    import torch
    print(f"PyTorch CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        device_count = torch.cuda.device_count()
        print(f"CUDA device count: {device_count}")
        for i in range(device_count):
            name = torch.cuda.get_device_name(i)
            print(f"  cuda:{i} -> {name}")
            
        # Test memory allocation on cuda:0
        try:
            device = torch.device('cuda:0')
            x = torch.randn(100, 100).to(device)
            print(f"✅ Successfully allocated tensor on cuda:0")
            print(f"✅ cuda:0 is: {torch.cuda.get_device_name(0)}")
        except Exception as e:
            print(f"❌ Failed to use cuda:0: {e}")
    else:
        print("❌ CUDA not available to PyTorch")
except ImportError:
    print("❌ PyTorch not available")
    
try:
    import onnxruntime as ort
    providers = ort.get_available_providers()
    print(f"ONNX Runtime providers: {providers}")
    if 'CUDAExecutionProvider' in providers:
        print("✅ ONNX Runtime CUDA available")
    else:
        print("❌ ONNX Runtime CUDA not available")
except ImportError:
    print("❌ ONNX Runtime not available")
"@

# Test with main environment
Write-Host "Testing with main environment:" -ForegroundColor Cyan
try {
    $result = .\.venv\Scripts\python.exe -c $testScript
    Write-Host $result -ForegroundColor White
} catch {
    Write-Host "❌ Main environment test failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Test with LVFace environment
Write-Host ""
Write-Host "Testing with LVFace environment:" -ForegroundColor Cyan
$lvfaceVenv = "C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace\.venv-lvface-311\Scripts\python.exe"
if (Test-Path $lvfaceVenv) {
    try {
        $result = & $lvfaceVenv -c $testScript
        Write-Host $result -ForegroundColor White
    } catch {
        Write-Host "❌ LVFace environment test failed: $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host "❌ LVFace environment not found: $lvfaceVenv" -ForegroundColor Red
}

# Test with Caption environment  
Write-Host ""
Write-Host "Testing with Caption environment:" -ForegroundColor Cyan
$captionVenv = "C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels\.venv\Scripts\python.exe"
if (Test-Path $captionVenv) {
    try {
        $result = & $captionVenv -c $testScript
        Write-Host $result -ForegroundColor White
    } catch {
        Write-Host "❌ Caption environment test failed: $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host "❌ Caption environment not found: $captionVenv" -ForegroundColor Red
}

Write-Host ""
Write-Host "🎯 Conclusion:" -ForegroundColor Yellow
Write-Host "If all environments show 'cuda:0 -> NVIDIA GeForce RTX 3090'," -ForegroundColor Gray
Write-Host "then our assumption that RTX 3090 becomes cuda:0 is CORRECT." -ForegroundColor Gray
Write-Host "If not, we need to adjust our device configuration!" -ForegroundColor Gray
