#!/usr/bin/env python3
"""
Debug embedding generation issue
"""

import requests
import json

def debug_embedding_issue():
    """Debug why embeddings are not being generated"""
    
    print("🐛 DEBUGGING EMBEDDING GENERATION")
    print("=" * 50)
    
    session = requests.Session()
    session.proxies = {'http': None, 'https': None}
    
    # First, check service status in detail
    try:
        print("🔍 Checking service status...")
        response = session.get("http://172.22.61.27:8003/status", timeout=10)
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Service Status:")
            for key, value in status.items():
                print(f"   {key}: {value}")
        else:
            print(f"❌ Status check failed: {response.status_code}")
            return
            
    except Exception as e:
        print(f"❌ Service connection error: {e}")
        return
    
    # Test a single image processing with detailed output
    print(f"\n🧪 Testing single image processing...")
    test_path = "/mnt/c/Users/yanbo/wSpace/vlm-photo-engine/vlmPhotoHouse/face_detection_results/asset_3116_20230401_110655_faces.jpg"
    
    try:
        response = session.post(
            "http://172.22.61.27:8003/process_image",
            json={"image_path": test_path},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"📊 Service Response Analysis:")
            print(f"   Status Code: {response.status_code}")
            print(f"   Response Keys: {list(result.keys())}")
            
            # Check for any error messages
            if 'error' in result:
                print(f"   ❌ Error: {result['error']}")
            
            # Check face detection results
            faces = result.get('faces', 0)
            detections = result.get('detections', [])
            
            print(f"   Faces detected: {faces}")
            print(f"   Detection details: {len(detections)} entries")
            
            if detections:
                first_detection = detections[0]
                print(f"   First detection keys: {list(first_detection.keys())}")
                print(f"   First detection values:")
                for key, value in first_detection.items():
                    print(f"      {key}: {value}")
                    
                # Check specifically for embedding-related fields
                if 'embedding_size' in first_detection:
                    emb_size = first_detection['embedding_size']
                    print(f"   🔍 Embedding size reported: {emb_size}")
                    if emb_size == 0:
                        print(f"   ❌ Embedding size is 0 - embeddings not generated!")
                    else:
                        print(f"   ✅ Embedding size indicates generation: {emb_size}")
                        
        else:
            print(f"❌ Processing failed: {response.status_code}")
            print(f"Response text: {response.text}")
            
    except Exception as e:
        print(f"❌ Processing test error: {e}")

def check_service_logs():
    """Check if we can get any service logs or error information"""
    
    print(f"\n📋 SERVICE DIAGNOSTIC SUGGESTIONS")
    print("=" * 50)
    print("Possible issues:")
    print("1. LVFace model not properly loaded")
    print("2. Face cropping/preprocessing failing")
    print("3. ONNX session issues with embeddings")
    print("4. Path/permission issues for embedding files")
    print("5. Service running detection-only mode")
    print()
    print("Recommended checks:")
    print("1. Check WSL service terminal for error messages")
    print("2. Verify LVFace model file exists in service directory")
    print("3. Test service with a simple known-good image")
    print("4. Check if service has write permissions for embeddings directory")

if __name__ == "__main__":
    debug_embedding_issue()
    check_service_logs()
