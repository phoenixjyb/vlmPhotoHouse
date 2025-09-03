#!/usr/bin/env python3
"""Test the unified SCRFD + LVFace service with a sample image"""

import json
import requests

def test_unified_service():
    """Test the unified face detection + recognition service"""
    
    # Service URL - use WSL IP with proxy bypass
    base_url = "http://172.22.61.27:8003"
    
    # Test status
    print("🔍 Testing service status...")
    try:
        # Create session with proxy bypass
        session = requests.Session()
        session.proxies = {'http': None, 'https': None}
        
        response = session.get(f"{base_url}/status")
        if response.status_code == 200:
            status = response.json()
            print("✅ Service Status:")
            for key, value in status.items():
                print(f"   {key}: {value}")
        else:
            print(f"❌ Status check failed: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Could not connect to service: {e}")
        return
    
    # Test image processing
    print("\n🖼️ Testing image processing...")
    test_image_path = "/mnt/e/01_INCOMING/Jane/20220112_043621.jpg"  # WSL path format
    
    try:
        response = session.post(f"{base_url}/process_image", 
                               json={"image_path": test_image_path})
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Image Processing Result:")
            print(f"   Faces detected: {result.get('faces', 0)}")
            print(f"   Detector used: {result.get('detector', 'unknown')}")
            
            if 'detections' in result:
                for i, detection in enumerate(result['detections']):
                    print(f"   Face {i+1}:")
                    print(f"     BBox: {detection.get('bbox', 'N/A')}")
                    print(f"     Confidence: {detection.get('confidence', 'N/A')}")
                    print(f"     Detector: {detection.get('detector', 'N/A')}")
                    print(f"     Embedding size: {detection.get('embedding_size', 'N/A')}")
                    print(f"     Has landmarks: {detection.get('has_landmarks', 'N/A')}")
        else:
            print(f"❌ Image processing failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Image processing error: {e}")

if __name__ == "__main__":
    test_unified_service()
