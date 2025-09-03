#!/usr/bin/env python3
"""
Test various connection methods to bypass proxy issues
"""

import requests
import os

def test_connection_methods():
    """Test different ways to connect bypassing proxy"""
    
    print("🔍 Testing Connection Methods")
    print("=" * 50)
    
    # Method 1: Environment variables
    os.environ['NO_PROXY'] = 'localhost,127.0.0.1,172.*.*.*'
    os.environ['no_proxy'] = 'localhost,127.0.0.1,172.*.*.*'
    
    # Method 2: Session with no proxy
    session = requests.Session()
    session.proxies = {
        'http': None,
        'https': None
    }
    
    urls_to_test = [
        "http://localhost:8003/status",
        "http://127.0.0.1:8003/status", 
        "http://172.22.61.27:8003/status"
    ]
    
    for url in urls_to_test:
        print(f"\n🌐 Testing: {url}")
        
        # Test with session (no proxy)
        try:
            response = session.get(url, timeout=5)
            if response.status_code == 200:
                result = response.json()
                print(f"✅ SUCCESS with session!")
                print(f"   Service: {result.get('service')}")
                print(f"   Detector: {result.get('face_detector')}")
                return url
            else:
                print(f"❌ Session: HTTP {response.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"❌ Session: Connection refused")
        except requests.exceptions.Timeout:
            print(f"❌ Session: Timeout")
        except Exception as e:
            print(f"❌ Session: {e}")
    
    print(f"\n❌ All connection methods failed!")
    print(f"💡 The SCRFD service might not be running in WSL")
    return None

if __name__ == "__main__":
    test_connection_methods()
