#!/usr/bin/env python3
"""
Debug network connectivity between Windows and WSL
"""

import requests
import subprocess
import json

def test_connectivity():
    """Test different ways to connect to the SCRFD service"""
    
    print("🔍 Testing SCRFD Service Connectivity")
    print("=" * 50)
    
    # Test URLs to try
    test_urls = [
        "http://localhost:8003/status",
        "http://127.0.0.1:8003/status", 
        "http://0.0.0.0:8003/status"
    ]
    
    for url in test_urls:
        print(f"\n🌐 Testing: {url}")
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"✅ SUCCESS!")
                result = response.json()
                print(f"   Service: {result.get('service')}")
                print(f"   Detector: {result.get('face_detector')}")
                return url
            else:
                print(f"❌ HTTP {response.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"❌ Connection refused")
        except requests.exceptions.Timeout:
            print(f"❌ Timeout")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print(f"\n🔍 Checking WSL networking...")
    try:
        # Get WSL IP
        result = subprocess.run(['wsl', 'hostname', '-I'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            wsl_ip = result.stdout.strip().split()[0]
            print(f"   WSL IP: {wsl_ip}")
            
            # Test WSL IP
            wsl_url = f"http://{wsl_ip}:8003/status"
            print(f"\n🌐 Testing WSL IP: {wsl_url}")
            try:
                response = requests.get(wsl_url, timeout=5)
                if response.status_code == 200:
                    print(f"✅ SUCCESS via WSL IP!")
                    result = response.json()
                    print(f"   Service: {result.get('service')}")
                    print(f"   Detector: {result.get('face_detector')}")
                    return wsl_url
                else:
                    print(f"❌ HTTP {response.status_code}")
            except Exception as e:
                print(f"❌ Error: {e}")
        else:
            print(f"❌ Could not get WSL IP")
    
    except Exception as e:
        print(f"❌ WSL check error: {e}")
    
    print(f"\n❌ No working connection found!")
    return None

def test_image_processing(service_url):
    """Test image processing with working URL"""
    if not service_url:
        return
        
    print(f"\n🖼️ Testing Image Processing")
    print("=" * 50)
    
    test_image = "/mnt/e/01_INCOMING/Jane/20220112_043621.jpg"
    
    try:
        response = requests.post(f"{service_url.replace('/status', '/process_image')}", 
                               json={"image_path": test_image}, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Image processing successful!")
            print(f"   Faces detected: {result.get('faces', 0)}")
            if result.get('faces', 0) > 0:
                detection = result['detections'][0]
                print(f"   BBox: {detection.get('bbox')}")
                print(f"   Confidence: {detection.get('confidence'):.3f}")
        else:
            print(f"❌ Processing failed: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Processing error: {e}")

if __name__ == "__main__":
    working_url = test_connectivity()
    test_image_processing(working_url)
