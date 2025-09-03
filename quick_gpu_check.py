#!/usr/bin/env python3
"""
Quick GPU Status Check for Face Detection
"""

import requests
import subprocess
import time

def quick_gpu_check():
    """Quick check of GPU usage and service status"""
    
    print("🔍 QUICK GPU CHECK FOR FACE DETECTION")
    print("=" * 50)
    
    # 1. Check service GPU configuration
    session = requests.Session()
    session.proxies = {'http': None, 'https': None}
    
    try:
        response = session.get("http://172.22.61.27:8003/status", timeout=5)
        if response.status_code == 200:
            status = response.json()
            providers = status.get('providers', [])
            print(f"✅ Service Providers: {providers}")
            
            if 'CUDAExecutionProvider' in providers:
                cuda_pos = providers.index('CUDAExecutionProvider')
                print(f"✅ CUDA Provider at position {cuda_pos} (0=highest priority)")
            else:
                print(f"❌ CUDA Provider NOT found - using CPU only!")
        else:
            print(f"❌ Service not responding")
            return
            
    except Exception as e:
        print(f"❌ Service check failed: {e}")
        return
    
    # 2. Check current GPU utilization
    print(f"\n📊 Current GPU Status:")
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'], 
                              capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 5:
                    gpu_id, name, util, mem_used, mem_total = parts
                    utilization_status = "🔥 ACTIVE" if int(util) > 0 else "💤 IDLE"
                    print(f"   GPU {gpu_id}: {name} - {util}% usage, {mem_used}/{mem_total}MB {utilization_status}")
        else:
            print(f"❌ nvidia-smi failed")
            
    except Exception as e:
        print(f"❌ GPU check failed: {e}")
    
    # 3. Test processing speed
    print(f"\n⚡ Testing Processing Speed:")
    try:
        test_path = "/mnt/c/Users/yanbo/wSpace/vlm-photo-engine/vlmPhotoHouse/face_detection_results/asset_3116_20230401_110655_faces.jpg"
        
        start_time = time.time()
        response = session.post(
            "http://172.22.61.27:8003/process_image",
            json={"image_path": test_path},
            timeout=10
        )
        end_time = time.time()
        
        if response.status_code == 200:
            result = response.json()
            faces = result.get('faces', 0)
            processing_time = end_time - start_time
            
            print(f"   Faces detected: {faces}")
            print(f"   Processing time: {processing_time:.3f}s")
            
            if processing_time < 0.5:
                print(f"   ✅ FAST - GPU accelerated")
            elif processing_time < 2.0:
                print(f"   ⚠️ MODERATE - check GPU usage")
            else:
                print(f"   ❌ SLOW - likely CPU only")
        else:
            print(f"   ❌ Processing test failed")
            
    except Exception as e:
        print(f"   ❌ Speed test failed: {e}")
    
    print(f"\n💡 Next Steps:")
    print(f"1. If GPU usage shows 0%, face detection is using CPU")
    print(f"2. If processing time > 1s, likely CPU processing")
    print(f"3. RTX 3090 should show >50% usage during processing")
    print(f"4. Run 'nvidia-smi' during batch processing to monitor")

if __name__ == "__main__":
    quick_gpu_check()
