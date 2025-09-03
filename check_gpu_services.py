#!/usr/bin/env python3
"""
Check GPU status and service capabilities for face detection and recognition
"""

import requests
import json

def check_gpu_and_services():
    """Check GPU availability and test both face detection and recognition services"""
    
    print("🔍 Checking GPU status and service capabilities")
    print("=" * 60)
    
    # Test SCRFD face detection service
    print("\n🎯 Testing SCRFD Face Detection Service:")
    print("-" * 40)
    
    session = requests.Session()
    session.proxies = {'http': None, 'https': None}
    
    try:
        # Test GPU status endpoint
        response = session.get("http://172.22.61.27:8003/gpu_status", timeout=10)
        if response.status_code == 200:
            gpu_info = response.json()
            print(f"✅ SCRFD Service GPU Status:")
            print(f"   CUDA Available: {gpu_info.get('cuda_available', 'Unknown')}")
            print(f"   Device Count: {gpu_info.get('device_count', 'Unknown')}")
            print(f"   Current Device: {gpu_info.get('current_device', 'Unknown')}")
            print(f"   Device Name: {gpu_info.get('device_name', 'Unknown')}")
            print(f"   GPU Memory: {gpu_info.get('memory_info', 'Unknown')}")
        else:
            print(f"❌ SCRFD GPU status endpoint error: {response.status_code}")
            
        # Test face detection capability
        test_path = "/mnt/c/Users/yanbo/wSpace/vlm-photo-engine/vlmPhotoHouse/face_detection_results/asset_3116_20230401_110655_faces.jpg"
        response = session.post(
            "http://172.22.61.27:8003/process_image",
            json={"image_path": test_path},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            faces = len(result.get('detections', []))
            processing_time = result.get('processing_time', 0)
            print(f"✅ Face Detection Test:")
            print(f"   Faces detected: {faces}")
            print(f"   Processing time: {processing_time:.3f}s")
            print(f"   Performance: {'GPU-accelerated' if processing_time < 1.0 else 'Possibly CPU-only'}")
        else:
            print(f"❌ Face detection test failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ SCRFD service error: {e}")
    
    # Check what face recognition capabilities we have
    print("\n🧠 Checking Face Recognition Capabilities:")
    print("-" * 40)
    
    # Check if SCRFD service also provides face recognition/embeddings
    try:
        response = session.get("http://172.22.61.27:8003/capabilities", timeout=10)
        if response.status_code == 200:
            capabilities = response.json()
            print(f"✅ SCRFD Service Capabilities:")
            for capability in capabilities.get('features', []):
                print(f"   - {capability}")
        else:
            print("ℹ️ SCRFD service capabilities endpoint not available")
            
        # Check if there's a face recognition endpoint
        response = session.get("http://172.22.61.27:8003/", timeout=5)
        if response.status_code == 200:
            print("ℹ️ SCRFD service is running - checking for recognition features")
        
    except Exception as e:
        print(f"ℹ️ Checking SCRFD service for recognition capabilities...")
        print("🔍 Currently we have face detection working")
        print("🔍 Face recognition may need separate setup or be part of SCRFD")
    
    # Check general GPU availability
    print("\n🖥️ System GPU Check:")
    print("-" * 40)
    
    try:
        import torch
        print(f"✅ PyTorch GPU Status:")
        print(f"   CUDA Available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"   Device Count: {torch.cuda.device_count()}")
            print(f"   Current Device: {torch.cuda.current_device()}")
            print(f"   Device Name: {torch.cuda.get_device_name(0)}")
            
            # Memory info
            memory_allocated = torch.cuda.memory_allocated(0) / 1024**3
            memory_reserved = torch.cuda.memory_reserved(0) / 1024**3
            print(f"   Memory Allocated: {memory_allocated:.2f} GB")
            print(f"   Memory Reserved: {memory_reserved:.2f} GB")
        else:
            print("   ❌ CUDA not available in current environment")
            
    except ImportError:
        print("❌ PyTorch not available in current environment")
        print("ℹ️ This is expected in Windows environment")
    
    print("\n📋 Summary:")
    print("-" * 40)
    print("1. Face Detection (SCRFD): Running on port 8003 in WSL")
    print("2. Face Recognition: Need to check if integrated with SCRFD or separate")
    print("3. GPU Acceleration: Verify both are using RTX 3090")
    print("4. Next: Determine face recognition setup needed")

if __name__ == "__main__":
    check_gpu_and_services()
