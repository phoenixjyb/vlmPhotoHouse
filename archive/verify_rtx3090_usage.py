"""
Real-time RTX 3090 Utilization Verification
Monitors actual GPU usage during AI processing to ensure RTX 3090 is being utilized
"""
import subprocess
import time
import json
from datetime import datetime

def get_gpu_stats():
    """Get current GPU utilization stats"""
    try:
        result = subprocess.run([
            "nvidia-smi", 
            "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,utilization.memory,temperature.gpu",
            "--format=csv,noheader,nounits"
        ], capture_output=True, text=True, check=True)
        
        gpus = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                parts = [p.strip() for p in line.split(',')]
                gpu_info = {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "memory_used_mb": int(parts[2]),
                    "memory_total_mb": int(parts[3]),
                    "gpu_utilization": int(parts[4]),
                    "memory_utilization": int(parts[5]),
                    "temperature": int(parts[6])
                }
                gpus.append(gpu_info)
        
        return gpus
    except Exception as e:
        print(f"Error getting GPU stats: {e}")
        return []

def check_pytorch_gpu_usage():
    """Check if PyTorch is actually using the GPU"""
    try:
        result = subprocess.run([
            r".\.venv\Scripts\python.exe", "-c", 
            """
import torch
import os
print(f"CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES', 'Not set')}")
print(f"PyTorch CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"Current device: {torch.cuda.current_device()}")
    print(f"Device name: {torch.cuda.get_device_name()}")
    print(f"Memory allocated: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
    print(f"Memory reserved: {torch.cuda.memory_reserved() / 1024**3:.2f} GB")
"""
        ], capture_output=True, text=True, timeout=10)
        
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
    except Exception as e:
        return f"PyTorch check failed: {e}"

def monitor_rtx3090_usage(duration_minutes=5):
    """Monitor RTX 3090 usage for specified duration"""
    print("🔍 RTX 3090 Real-Time Utilization Monitor")
    print("=" * 60)
    
    # Initial PyTorch check
    print("\n📋 PyTorch GPU Configuration:")
    pytorch_info = check_pytorch_gpu_usage()
    print(pytorch_info)
    
    print(f"\n🕒 Monitoring RTX 3090 for {duration_minutes} minutes...")
    print("Timestamp               | RTX 3090 GPU% | Memory GB | Temp°C | Status")
    print("-" * 75)
    
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    max_gpu_util = 0
    max_memory_used = 0
    rtx3090_active = False
    
    try:
        while time.time() < end_time:
            gpus = get_gpu_stats()
            rtx3090_gpu = None
            
            for gpu in gpus:
                if "RTX 3090" in gpu["name"]:
                    rtx3090_gpu = gpu
                    break
            
            if rtx3090_gpu:
                timestamp = datetime.now().strftime("%H:%M:%S")
                memory_gb = rtx3090_gpu["memory_used_mb"] / 1024
                gpu_util = rtx3090_gpu["gpu_utilization"]
                temp = rtx3090_gpu["temperature"]
                
                # Track maximums
                max_gpu_util = max(max_gpu_util, gpu_util)
                max_memory_used = max(max_memory_used, memory_gb)
                
                # Determine status
                if gpu_util > 50:
                    status = "🔥 ACTIVE"
                    rtx3090_active = True
                elif gpu_util > 10:
                    status = "⚡ LIGHT"
                    rtx3090_active = True
                elif memory_gb > 1.0:
                    status = "📊 LOADED"
                    rtx3090_active = True
                else:
                    status = "💤 IDLE"
                
                print(f"{timestamp}          | {gpu_util:5d}%    | {memory_gb:6.2f}    | {temp:4d}°C | {status}")
            else:
                print(f"{datetime.now().strftime('%H:%M:%S')}          | RTX 3090 not found!")
            
            time.sleep(5)  # Check every 5 seconds
            
    except KeyboardInterrupt:
        print("\n⚠️  Monitoring interrupted by user")
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 RTX 3090 Utilization Summary:")
    print(f"   Max GPU Utilization: {max_gpu_util}%")
    print(f"   Max Memory Used: {max_memory_used:.2f} GB")
    print(f"   RTX 3090 Active: {'✅ YES' if rtx3090_active else '❌ NO'}")
    
    if not rtx3090_active:
        print("\n⚠️  WARNING: RTX 3090 remained idle during monitoring!")
        print("   Check if AI processing is actually running and using GPU")
    elif max_gpu_util < 30:
        print("\n💡 RTX 3090 utilization is low (<30%)")
        print("   Consider checking if models are fully loaded on GPU")
    else:
        print("\n🎯 RTX 3090 is being utilized for AI processing!")
    
    return {
        "max_gpu_utilization": max_gpu_util,
        "max_memory_used_gb": max_memory_used,
        "rtx3090_active": rtx3090_active,
        "duration_minutes": duration_minutes
    }

if __name__ == "__main__":
    import sys
    
    # Default to 5 minutes, or use command line argument
    duration = 5
    if len(sys.argv) > 1:
        try:
            duration = int(sys.argv[1])
        except ValueError:
            print("Usage: python verify_rtx3090_usage.py [duration_minutes]")
            sys.exit(1)
    
    # Run the monitoring
    results = monitor_rtx3090_usage(duration)
    
    # Save results
    results["timestamp"] = datetime.now().isoformat()
    with open("rtx3090_usage_verification.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Results saved to: rtx3090_usage_verification.json")
    
    # Exit with status code
    sys.exit(0 if results["rtx3090_active"] else 1)
