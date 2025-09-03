#!/usr/bin/env python3
"""
GPU Usage Monitor for Face Detection Processing
Check which GPU is being used and monitor utilization
"""

import requests
import json
import time
import subprocess
import threading

def check_service_gpu_status():
    """Check which GPU the face detection service is using"""
    
    print("🔍 CHECKING FACE DETECTION SERVICE GPU USAGE")
    print("=" * 60)
    
    session = requests.Session()
    session.proxies = {'http': None, 'https': None}
    
    try:
        # Check service status
        response = session.get("http://172.22.61.27:8003/status", timeout=10)
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Service Status:")
            print(f"   Service: {status.get('service')}")
            print(f"   Providers: {status.get('providers', [])}")
            
            # Check if CUDA is in providers
            providers = status.get('providers', [])
            if 'CUDAExecutionProvider' in providers:
                print(f"   ✅ CUDA Provider Available")
                cuda_index = providers.index('CUDAExecutionProvider')
                print(f"   🎯 CUDA Provider Priority: {cuda_index + 1}")
            else:
                print(f"   ❌ CUDA Provider NOT Available - Using CPU!")
                
        else:
            print(f"❌ Service not responding: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Service connection error: {e}")
        return False
    
    # Test with actual image processing
    print(f"\n🧪 Testing GPU Usage During Processing...")
    
    try:
        test_path = "/mnt/c/Users/yanbo/wSpace/vlm-photo-engine/vlmPhotoHouse/face_detection_results/asset_3116_20230401_110655_faces.jpg"
        
        start_time = time.time()
        response = session.post(
            "http://172.22.61.27:8003/process_image",
            json={"image_path": test_path},
            timeout=30
        )
        end_time = time.time()
        
        if response.status_code == 200:
            result = response.json()
            faces = result.get('faces', 0)
            processing_time = end_time - start_time
            
            print(f"   ✅ Processing Test Results:")
            print(f"   Faces detected: {faces}")
            print(f"   Processing time: {processing_time:.3f}s")
            
            # Analyze processing speed
            if processing_time < 0.5:
                print(f"   🚀 Very fast processing - likely GPU accelerated")
            elif processing_time < 2.0:
                print(f"   ⚡ Moderate speed - possibly GPU with overhead")
            else:
                print(f"   🐌 Slow processing - likely CPU only")
                
        else:
            print(f"   ❌ Processing test failed: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Processing test error: {e}")
    
    return True

def monitor_gpu_utilization():
    """Monitor GPU utilization using nvidia-smi"""
    
    print(f"\n📊 GPU UTILIZATION MONITORING")
    print("=" * 60)
    
    try:
        # Run nvidia-smi to check GPU usage
        result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu', '--format=csv,noheader,nounits'], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            print(f"Current GPU Status:")
            
            for i, line in enumerate(lines):
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 6:
                    gpu_id, name, util, mem_used, mem_total, temp = parts
                    print(f"   GPU {gpu_id}: {name}")
                    print(f"      Utilization: {util}%")
                    print(f"      Memory: {mem_used}MB / {mem_total}MB")
                    print(f"      Temperature: {temp}°C")
                    
                    # Highlight which GPU is being used
                    if int(util) > 10:
                        print(f"      🔥 HIGH USAGE - This GPU is active!")
                    elif int(util) > 0:
                        print(f"      ⚡ Some usage detected")
                    else:
                        print(f"      💤 Idle")
                    print()
        else:
            print(f"❌ nvidia-smi failed: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        print(f"❌ nvidia-smi timeout")
    except FileNotFoundError:
        print(f"❌ nvidia-smi not found")
    except Exception as e:
        print(f"❌ GPU monitoring error: {e}")

def monitor_during_processing():
    """Monitor GPU usage during actual face processing"""
    
    print(f"\n🔄 MONITORING GPU DURING FACE PROCESSING")
    print("=" * 60)
    print("Starting GPU monitoring - process some images to see usage...")
    
    # Monitor GPU usage in a separate thread
    def gpu_monitor_thread():
        for i in range(10):  # Monitor for 10 cycles
            print(f"\n--- GPU Check {i+1}/10 ---")
            monitor_gpu_utilization()
            time.sleep(3)
    
    # Start monitoring
    monitor_thread = threading.Thread(target=gpu_monitor_thread)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    print(f"\n💡 Now run face processing in another terminal:")
    print(f"   .venv\\Scripts\\python.exe enhanced_face_orchestrator_unified.py --batch-size 10")
    print(f"\nWatch the GPU utilization above to see which GPU is active!")
    
    # Wait for monitoring to complete
    monitor_thread.join()

if __name__ == "__main__":
    # Check service GPU configuration
    service_ok = check_service_gpu_status()
    
    if service_ok:
        # Check current GPU utilization
        monitor_gpu_utilization()
        
        # Offer to monitor during processing
        print(f"\n🔍 RECOMMENDATIONS:")
        print("1. Check if CUDAExecutionProvider is first in providers list")
        print("2. Verify processing times are < 0.5s per image")
        print("3. Monitor GPU utilization during batch processing")
        print("4. Ensure RTX 3090 shows high utilization during processing")
        
        # Optional: Start continuous monitoring
        user_input = input(f"\nStart continuous GPU monitoring? (y/n): ")
        if user_input.lower() == 'y':
            monitor_during_processing()
    else:
        print(f"\n❌ Service not available for GPU testing")
