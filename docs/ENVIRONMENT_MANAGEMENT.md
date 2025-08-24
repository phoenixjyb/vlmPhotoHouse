# Environment Management Guide

Version: v1.0  
Date: 2025-08-24  
Author: VLM Photo Engine Team

## 1. Overview

This document provides guidance for managing multiple Python environments, CUDA versions, and model dependencies across the VLM Photo Engine ecosystem, including integration with LLMyTranslate voice services.

## 2. Environment Architecture

### Why CUDA 12.6?
Your system has **CUDA 12.6** installed (`nvcc --version`), which is the optimal choice because:

✅ **Performance**: 15-20% better performance vs CUDA 11.8  
✅ **RTX 3090 Optimization**: Latest GPU optimizations and memory management  
✅ **PyTorch 2.8.0 Support**: Full compatibility with latest PyTorch features  
✅ **Model Compatibility**: Better support for modern AI models (TTS, Vision, LLM)  
✅ **Future-Proof**: Latest CUDA features and bug fixes  

### Service Overview
| Service | Port | Python Version | PyTorch/CUDA | Primary Purpose |
|---------|------|---------------|--------------|-----------------|
| **VLM Photo Engine** | 8000 | 3.13 | PyTorch 2.8.0+cu126 | Main photo management API |
| **LLMyTranslate Main** | 8001 | 3.13 | PyTorch 2.8.0+cu126 | Translation & general AI services |
| **LLMyTranslate TTS** | 8002 | 3.12 | PyTorch 2.8.0+cu126 | RTX 3090 optimized TTS |

### Hardware Mapping
```
RTX 3090 (cuda:0) - 25.8GB VRAM
├── Primary: TTS Service (Python 3.12)
├── Secondary: VLM Photo Engine (face detection, embeddings)
└── Tertiary: LLMyTranslate Main (general AI tasks)

Quadro P2000 (cuda:1) - 4GB VRAM
└── Display output only
```

## 3. Environment Specifications

### 3.1 VLM Photo Engine Environment
**Location:** `C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv`

```powershell
# Setup
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Core Dependencies
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
pip install -r backend/requirements.txt
pip install -r backend/requirements-ml.txt

# Known Conflicts (warnings only, functional)
# facenet-pytorch 2.6.0 requires:
# - torch<2.3.0 (you have 2.8.0+cu126 - newer is better)
```

**Environment Variables:**
```powershell
$env:VOICE_ENABLED="true"
$env:VOICE_EXTERNAL_BASE_URL="http://127.0.0.1:8001"
$env:FACE_EMBED_PROVIDER="facenet"  # or lvface, insight, auto
$env:FACE_DETECT_PROVIDER="mtcnn"
$env:EMBED_DEVICE="cuda"
```

### 3.2 LLMyTranslate Main Environment
**Location:** `C:\Users\yanbo\wSpace\llmytranslate\.venv`

```powershell
# Setup
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Core Dependencies
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt
```

### 3.3 LLMyTranslate TTS Environment (RTX 3090 Optimized)
**Location:** `C:\Users\yanbo\wSpace\llmytranslate\.venv-tts`

```powershell
# Setup (Python 3.12 required for Coqui TTS compatibility)
python3.12 -m venv .venv-tts
.\.venv-tts\Scripts\Activate.ps1

# Core Dependencies
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
pip install TTS==0.22.0  # Coqui TTS
pip install librosa soundfile numpy
```

**RTX 3090 Configuration:**
```python
# C:\Users\yanbo\wSpace\llmytranslate\rtx3090_tts_config.py
import torch
import os

def configure_rtx3090_for_tts():
    """Configure RTX 3090 for optimal TTS performance"""
    if torch.cuda.is_available():
        # Force RTX 3090 (usually cuda:0)
        device = torch.device("cuda:0")
        print(f"RTX 3090 VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")
        return device
    return torch.device("cpu")
```

## 4. Startup Sequences

### 4.1 Development Startup (All Services)
```powershell
# Terminal 1: LLMyTranslate TTS Service (RTX 3090)
cd "C:\Users\yanbo\wSpace\llmytranslate"
.\.venv-tts\Scripts\Activate.ps1
python tts_subprocess_rtx3090.py

# Terminal 2: LLMyTranslate Main Service
cd "C:\Users\yanbo\wSpace\llmytranslate"
.\.venv\Scripts\Activate.ps1
python main.py  # or uvicorn command

# Terminal 3: VLM Photo Engine
cd "C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse"
.\.venv\Scripts\Activate.ps1
$env:VOICE_ENABLED="true"
$env:VOICE_EXTERNAL_BASE_URL="http://127.0.0.1:8001"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### 4.2 Production Startup Script
**Location:** `C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\scripts\start-dev-multiproc.ps1`

```powershell
# Enhanced version with voice integration
param(
    [string]$Preset = "RTX3090",
    [switch]$VoiceEnabled = $true
)

if ($VoiceEnabled) {
    Write-Host "🎤 Starting voice services..." -ForegroundColor Green
    
    # Start LLMyTranslate TTS (RTX 3090)
    Start-Process powershell -ArgumentList @(
        "-Command",
        "cd 'C:\Users\yanbo\wSpace\llmytranslate'; .\.venv-tts\Scripts\Activate.ps1; python tts_subprocess_rtx3090.py"
    )
    
    Start-Sleep 5  # Wait for TTS service
    
    # Set voice environment
    $env:VOICE_ENABLED = "true"
    $env:VOICE_EXTERNAL_BASE_URL = "http://127.0.0.1:8001"
}

# Continue with VLM Photo Engine startup...
```

## 5. Common Issues & Solutions

### 5.1 PyTorch Version Conflicts
**Problem:** Different services need different PyTorch versions
**Solution:** Use separate virtual environments

```powershell
# Check current PyTorch version
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.cuda.is_available())"

# Force reinstall with CUDA 12.6
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
```

### 5.2 CUDA Device Selection
**Problem:** Multiple GPUs, need specific device assignment
**Solution:** Explicit device configuration

```python
# In model loading code
import torch
device = torch.device("cuda:0")  # RTX 3090
# device = torch.device("cuda:1")  # Quadro P2000
```

### 5.3 Memory Management
**Problem:** RTX 3090 VRAM exhaustion with multiple models
**Solution:** Sequential loading and model sharing

```python
# Clear CUDA cache between models
torch.cuda.empty_cache()

# Monitor VRAM usage
print(f"VRAM Used: {torch.cuda.memory_allocated(0) / 1e9:.1f}GB")
print(f"VRAM Reserved: {torch.cuda.memory_reserved(0) / 1e9:.1f}GB")
```

### 5.4 Dependency Conflicts
**Problem:** Package version conflicts (e.g., facenet-pytorch)
**Solution:** Accept warnings for non-breaking conflicts

```
# These warnings are safe to ignore:
facenet-pytorch 2.6.0 requires torch<2.3.0,>=2.2.0, but you have torch 2.8.0+cu126
# Newer PyTorch versions have better performance and compatibility
```

## 6. Performance Optimization

### 6.1 RTX 3090 TTS Optimization
```python
# In tts_subprocess_rtx3090.py
def optimize_rtx3090_settings():
    torch.backends.cudnn.benchmark = True
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
```

### 6.2 Model Loading Strategies
- **Lazy Loading:** Load models on first use
- **Model Caching:** Keep frequently used models in VRAM
- **Batch Processing:** Group similar requests

### 6.3 GPU Scheduling
```
Priority Order:
1. TTS Service (real-time, user-facing)
2. Face Detection (photo processing)
3. Image Embeddings (background processing)
4. Caption Generation (lowest priority)
```

## 7. Monitoring & Diagnostics

### 7.1 Health Check Endpoints
```
VLM Photo Engine:     http://127.0.0.1:8000/voice/rtx3090-status
LLMyTranslate:        http://127.0.0.1:8001/docs
Voice Demo:           http://127.0.0.1:8000/voice/photo-demo
```

### 7.2 GPU Monitoring
```powershell
# PowerShell GPU monitoring
nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv

# Python GPU status
python -c "import torch; [print(f'GPU {i}: {torch.cuda.get_device_name(i)}') for i in range(torch.cuda.device_count())]"
```

## 8. Backup & Recovery

### 8.1 Environment Backup
```powershell
# Export package lists
pip freeze > requirements-backup.txt

# Backup environment variables
Get-ChildItem env: | Where-Object {$_.Name -like "*VOICE*" -or $_.Name -like "*FACE*"} > env-backup.txt
```

### 8.2 Quick Recovery
```powershell
# Recreate environment
python -m venv .venv-recovery
.\.venv-recovery\Scripts\Activate.ps1
pip install -r requirements-backup.txt
```

## 9. Best Practices

1. **Environment Isolation:** Always use separate virtual environments
2. **Version Pinning:** Pin exact versions in production
3. **CUDA Compatibility:** Match PyTorch CUDA version with system CUDA
4. **Resource Monitoring:** Monitor GPU memory and CPU usage
5. **Graceful Degradation:** Fallback to CPU when GPU unavailable
6. **Documentation:** Keep environment setup scripts updated

## 10. Future Considerations

- **Model Quantization:** Reduce VRAM usage with INT8/FP16
- **Multi-GPU Scaling:** Distribute models across multiple GPUs
- **Cloud Integration:** Hybrid local/cloud model deployment
- **Container Deployment:** Docker for consistent environments

---

**Quick Reference Commands:**
```powershell
# Check all Python environments
Get-ChildItem -Path "C:\Users\yanbo\wSpace\" -Recurse -Name "pyvenv.cfg"

# Check all running services
netstat -an | findstr ":800"

# Start complete stack
.\scripts\start-dev-multiproc.ps1 -Preset RTX3090 -VoiceEnabled
```
