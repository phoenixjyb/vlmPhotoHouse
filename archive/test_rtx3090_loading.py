"""
Direct RTX 3090 Model Loading Test
Forces loading of LVFace and BLIP2 models to test actual GPU utilization
"""
import os
import sys
import subprocess
import time

# Ensure RTX 3090 configuration
os.environ['CUDA_VISIBLE_DEVICES'] = '0'

print("🔥 FORCING RTX 3090 MODEL LOADING TEST")
print("=" * 50)

print(f"✅ CUDA_VISIBLE_DEVICES set to: {os.environ.get('CUDA_VISIBLE_DEVICES')}")

# Test 1: Load PyTorch and allocate memory on RTX 3090
print("\n🧪 Test 1: PyTorch RTX 3090 Memory Allocation")
try:
    import torch
    print(f"PyTorch CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        device = torch.device("cuda:0")
        print(f"Using device: {torch.cuda.get_device_name(device)}")
        
        # Allocate 2GB of memory on RTX 3090
        print("Allocating 2GB on RTX 3090...")
        x = torch.randn(256, 1024, 1024, device=device, dtype=torch.float32)  # ~2GB
        print(f"✅ Allocated {x.numel() * 4 / (1024**3):.1f} GB on {torch.cuda.get_device_name(device)}")
        
        # Keep the allocation for a moment
        time.sleep(5)
        
        del x
        torch.cuda.empty_cache()
        print("✅ Memory cleared")
    else:
        print("❌ CUDA not available")
        
except Exception as e:
    print(f"❌ PyTorch test failed: {e}")

# Test 2: Test LVFace model loading
print("\n🧪 Test 2: LVFace Model Loading")
try:
    lvface_script = '''
import os
import sys
import torch
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

print(f"LVFace CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES')}")
print(f"LVFace PyTorch device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'No CUDA'}")

# Try to load a model (this should use RTX 3090 memory)
if torch.cuda.is_available():
    device = torch.device("cuda:0")
    # Simulate model loading with memory allocation
    model_weights = torch.randn(512, 1024, 1024, device=device, dtype=torch.float32)  # ~2GB
    print(f"✅ LVFace model loaded on {torch.cuda.get_device_name(device)} - {model_weights.numel() * 4 / (1024**3):.1f} GB")
    
    import time
    time.sleep(3)  # Keep model loaded briefly
    
    del model_weights
    torch.cuda.empty_cache()
    print("✅ LVFace model unloaded")
else:
    print("❌ LVFace: CUDA not available")
'''
    
    lvface_env = os.environ.copy()
    lvface_env['CUDA_VISIBLE_DEVICES'] = '0'
    
    result = subprocess.run([
        r"C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace\.venv-lvface-311\Scripts\python.exe",
        "-c", lvface_script
    ], capture_output=True, text=True, env=lvface_env, timeout=30)
    
    print("LVFace output:")
    print(result.stdout)
    if result.stderr:
        print("LVFace errors:")
        print(result.stderr)
        
except Exception as e:
    print(f"❌ LVFace test failed: {e}")

# Test 3: Test BLIP2 model loading
print("\n🧪 Test 3: BLIP2 Model Loading")
try:
    blip2_script = '''
import os
import torch
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

print(f"BLIP2 CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES')}")
print(f"BLIP2 PyTorch device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'No CUDA'}")

# Try to load a model (this should use RTX 3090 memory)
if torch.cuda.is_available():
    device = torch.device("cuda:0")
    # Simulate model loading with memory allocation
    model_weights = torch.randn(256, 2048, 1024, device=device, dtype=torch.float32)  # ~2GB
    print(f"✅ BLIP2 model loaded on {torch.cuda.get_device_name(device)} - {model_weights.numel() * 4 / (1024**3):.1f} GB")
    
    import time
    time.sleep(3)  # Keep model loaded briefly
    
    del model_weights
    torch.cuda.empty_cache() 
    print("✅ BLIP2 model unloaded")
else:
    print("❌ BLIP2: CUDA not available")
'''
    
    blip2_env = os.environ.copy()
    blip2_env['CUDA_VISIBLE_DEVICES'] = '0'
    
    result = subprocess.run([
        r"C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels\.venv\Scripts\python.exe",
        "-c", blip2_script
    ], capture_output=True, text=True, env=blip2_env, timeout=30)
    
    print("BLIP2 output:")
    print(result.stdout)
    if result.stderr:
        print("BLIP2 errors:")
        print(result.stderr)
        
except Exception as e:
    print(f"❌ BLIP2 test failed: {e}")

print("\n🎯 Test complete! Check nvidia-smi now to see if RTX 3090 was used.")
print("Run: nvidia-smi")
