#!/usr/bin/env python3
"""
Test External Subprocess Model GPU Access
Specifically tests if LVFace and BLIP2 subprocess can access RTX 3090
"""
import os
import sys
import subprocess
import traceback

# Set up environment for RTX 3090
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
os.environ['EMBED_DEVICE'] = 'cuda:0'
os.environ['CAPTION_DEVICE'] = 'cuda:0'
os.environ['FACE_EMBED_PROVIDER'] = 'lvface'
os.environ['CAPTION_PROVIDER'] = 'blip2'
os.environ['LVFACE_EXTERNAL_DIR'] = r'C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace'
os.environ['CAPTION_EXTERNAL_DIR'] = r'C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels'

print("🔍 Testing External Model RTX 3090 Access")
print("=" * 60)

def test_lvface_gpu_access():
    """Test if LVFace external environment can see RTX 3090"""
    print("\n🎯 Testing LVFace External Environment:")
    
    lvface_python = r"C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace\.venv-lvface-311\Scripts\python.exe"
    
    if not os.path.exists(lvface_python):
        print(f"❌ LVFace Python not found: {lvface_python}")
        return False
    
    test_script = """
import os
print(f"CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES', 'Not set')}")

try:
    import torch
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    
    if torch.cuda.is_available():
        device_count = torch.cuda.device_count()
        print(f"Device count: {device_count}")
        
        for i in range(device_count):
            name = torch.cuda.get_device_name(i)
            props = torch.cuda.get_device_properties(i)
            memory_gb = props.total_memory / (1024**3)
            print(f"  cuda:{i} -> {name} ({memory_gb:.1f} GB)")
            
            if "RTX 3090" in name:
                # Test actual allocation
                try:
                    device = torch.device(f'cuda:{i}')
                    x = torch.randn(1000, 1000).to(device)
                    print(f"  ✅ RTX 3090 allocation successful!")
                    del x
                    torch.cuda.empty_cache()
                except Exception as e:
                    print(f"  ❌ RTX 3090 allocation failed: {e}")
    else:
        print("❌ CUDA not available in LVFace environment")
        
except ImportError:
    print("❌ PyTorch not available in LVFace environment")
except Exception as e:
    print(f"❌ LVFace GPU test failed: {e}")
"""
    
    try:
        # Pass environment variables to subprocess
        env = os.environ.copy()
        result = subprocess.run([
            lvface_python, "-c", test_script
        ], capture_output=True, text=True, env=env, timeout=30)
        
        print("LVFace Environment Output:")
        print(result.stdout)
        if result.stderr:
            print("LVFace Errors:")
            print(result.stderr)
        
        return "RTX 3090 allocation successful" in result.stdout
        
    except Exception as e:
        print(f"❌ LVFace test execution failed: {e}")
        return False

def test_blip2_gpu_access():
    """Test if BLIP2 external environment can see RTX 3090"""
    print("\n📝 Testing BLIP2 External Environment:")
    
    blip2_python = r"C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels\.venv\Scripts\python.exe"
    
    if not os.path.exists(blip2_python):
        print(f"❌ BLIP2 Python not found: {blip2_python}")
        return False
    
    test_script = """
import os
print(f"CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES', 'Not set')}")

try:
    import torch
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    
    if torch.cuda.is_available():
        device_count = torch.cuda.device_count()
        print(f"Device count: {device_count}")
        
        for i in range(device_count):
            name = torch.cuda.get_device_name(i)
            props = torch.cuda.get_device_properties(i)
            memory_gb = props.total_memory / (1024**3)
            print(f"  cuda:{i} -> {name} ({memory_gb:.1f} GB)")
            
            if "RTX 3090" in name:
                # Test actual allocation
                try:
                    device = torch.device(f'cuda:{i}')
                    x = torch.randn(1000, 1000).to(device)
                    print(f"  ✅ RTX 3090 allocation successful!")
                    del x
                    torch.cuda.empty_cache()
                except Exception as e:
                    print(f"  ❌ RTX 3090 allocation failed: {e}")
    else:
        print("❌ CUDA not available in BLIP2 environment")
        
except ImportError:
    print("❌ PyTorch not available in BLIP2 environment")
except Exception as e:
    print(f"❌ BLIP2 GPU test failed: {e}")
"""
    
    try:
        # Pass environment variables to subprocess
        env = os.environ.copy()
        result = subprocess.run([
            blip2_python, "-c", test_script
        ], capture_output=True, text=True, env=env, timeout=30)
        
        print("BLIP2 Environment Output:")
        print(result.stdout)
        if result.stderr:
            print("BLIP2 Errors:")
            print(result.stderr)
        
        return "RTX 3090 allocation successful" in result.stdout
        
    except Exception as e:
        print(f"❌ BLIP2 test execution failed: {e}")
        return False

if __name__ == "__main__":
    print(f"Main Environment CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES')}")
    
    lvface_success = test_lvface_gpu_access()
    blip2_success = test_blip2_gpu_access()
    
    print("\n" + "=" * 60)
    print("📊 External Model RTX 3090 Access Summary:")
    print(f"  LVFace Environment: {'✅ SUCCESS' if lvface_success else '❌ FAILED'}")
    print(f"  BLIP2 Environment:  {'✅ SUCCESS' if blip2_success else '❌ FAILED'}")
    
    if lvface_success and blip2_success:
        print("\n🎯 All external models can access RTX 3090!")
    else:
        print("\n⚠️  Some external models cannot access RTX 3090")
        print("   Environment variables may not be propagating to subprocesses")
    
    # Exit code for monitoring
    sys.exit(0 if (lvface_success and blip2_success) else 1)
