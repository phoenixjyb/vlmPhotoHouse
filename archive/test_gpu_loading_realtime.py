"""
Real-time GPU loading test with nvidia-smi monitoring
Loads model and keeps it in memory while monitoring GPU usage
"""
import os
import sys
import time
import threading
import subprocess
from datetime import datetime

# Set RTX 3090 environment
os.environ['CUDA_VISIBLE_DEVICES'] = '0'

def monitor_gpu_usage(duration_seconds=60):
    """Monitor GPU usage in background thread"""
    print("🔍 Starting GPU monitoring thread...")
    
    for i in range(duration_seconds):
        try:
            result = subprocess.run([
                "nvidia-smi", 
                "--query-gpu=index,name,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits"
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                timestamp = datetime.now().strftime("%H:%M:%S")
                lines = result.stdout.strip().split('\n')
                
                for line in lines:
                    if 'RTX 3090' in line:
                        parts = [p.strip() for p in line.split(',')]
                        gpu_index = parts[0]
                        gpu_name = parts[1]
                        memory_used = parts[2]
                        gpu_util = parts[3]
                        
                        if int(memory_used) > 0 or int(gpu_util) > 0:
                            print(f"🎯 [{timestamp}] RTX 3090: {memory_used}MiB memory, {gpu_util}% util")
                        else:
                            print(f"💤 [{timestamp}] RTX 3090: idle")
                        break
        except Exception as e:
            print(f"⚠️  GPU monitoring error: {e}")
        
        time.sleep(1)
    
    print("📊 GPU monitoring thread finished")

def test_model_loading():
    """Test loading and keeping model in GPU memory"""
    print("🚀 Starting PyTorch GPU loading test...")
    
    try:
        import torch
        print(f"PyTorch version: {torch.__version__}")
        print(f"CUDA available: {torch.cuda.is_available()}")
        print(f"CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES')}")
        
        if not torch.cuda.is_available():
            print("❌ CUDA not available!")
            return False
            
        device = torch.device('cuda:0')
        print(f"Using device: {device}")
        print(f"Device name: {torch.cuda.get_device_name(0)}")
        
        # Start GPU monitoring in background
        monitor_thread = threading.Thread(target=monitor_gpu_usage, args=(60,))
        monitor_thread.daemon = True
        monitor_thread.start()
        
        print("\n🔄 Loading large tensors to GPU...")
        
        # Load progressively larger tensors
        tensors = []
        for i, size in enumerate([1000, 2000, 5000, 10000]):
            print(f"📈 Loading tensor {i+1}: {size}x{size} matrix...")
            
            tensor = torch.randn(size, size, device=device)
            tensors.append(tensor)
            
            # Force GPU computation to ensure memory allocation
            result = torch.mm(tensor, tensor)
            memory_allocated = torch.cuda.memory_allocated() / (1024**3)
            memory_reserved = torch.cuda.memory_reserved() / (1024**3)
            
            print(f"   Memory allocated: {memory_allocated:.2f}GB")
            print(f"   Memory reserved: {memory_reserved:.2f}GB")
            
            # Sleep to allow monitoring to catch it
            print(f"   Waiting 5 seconds for GPU monitoring...")
            time.sleep(5)
        
        print("\n🎯 All tensors loaded! Keeping in memory for 30 seconds...")
        print("💡 Check nvidia-smi output above for RTX 3090 usage")
        
        # Keep tensors alive for 30 seconds
        for i in range(30):
            # Perform some computation to keep GPU active
            if i % 5 == 0:
                for j, tensor in enumerate(tensors):
                    _ = torch.mm(tensor[:100, :100], tensor[:100, :100])
                
                memory_allocated = torch.cuda.memory_allocated() / (1024**3)
                print(f"⚡ [{datetime.now().strftime('%H:%M:%S')}] Active computation: {memory_allocated:.2f}GB allocated")
            
            time.sleep(1)
        
        print("\n🧹 Cleaning up tensors...")
        del tensors
        torch.cuda.empty_cache()
        
        final_memory = torch.cuda.memory_allocated() / (1024**3)
        print(f"✅ Cleanup complete. Final memory: {final_memory:.2f}GB")
        
        # Wait for monitoring thread to finish
        monitor_thread.join(timeout=5)
        
        return True
        
    except Exception as e:
        print(f"❌ Model loading test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🔬 RTX 3090 Real-time GPU Loading Test")
    print("=" * 60)
    
    success = test_model_loading()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ Test completed successfully")
        print("💡 Check the monitoring output above to see RTX 3090 usage")
    else:
        print("❌ Test failed")
    print("=" * 60)
    
    sys.exit(0 if success else 1)
