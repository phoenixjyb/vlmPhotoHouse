#!/usr/bin/env python3
"""
Test connectivity with proxy bypass
"""

import requests
import os
import subprocess

def test_with_proxy_bypass():
    """Test connectivity with various proxy bypass methods"""
    
    print("🔍 Testing Connectivity with Proxy Bypass")
    print("=" * 60)
    
    # Get WSL IP
    try:
        result = subprocess.run(['wsl', '-d', 'Ubuntu-22.04', '--', 'hostname', '-I'], 
                              capture_output=True, text=True)
        wsl_ip = result.stdout.strip().split()[0] if result.returncode == 0 else "172.22.61.27"
        print(f"📍 WSL IP: {wsl_ip}")
    except:
        wsl_ip = "172.22.61.27"
        print(f"📍 Using default WSL IP: {wsl_ip}")
    
    # Test URLs
    test_urls = [
        f"http://{wsl_ip}:8003/status",
        "http://127.0.0.1:8003/status",
        "http://localhost:8003/status"
    ]
    
    # Method 1: Bypass proxy with environment variables
    print(f"\n🔧 Method 1: Environment Variable Bypass")
    print("-" * 40)
    
    # Set no_proxy environment variables
    no_proxy_env = os.environ.copy()
    no_proxy_env['no_proxy'] = f'localhost,127.0.0.1,{wsl_ip}'
    no_proxy_env['NO_PROXY'] = f'localhost,127.0.0.1,{wsl_ip}'
    no_proxy_env['http_proxy'] = ''
    no_proxy_env['https_proxy'] = ''
    no_proxy_env['HTTP_PROXY'] = ''
    no_proxy_env['HTTPS_PROXY'] = ''
    
    for url in test_urls:
        print(f"   Testing: {url}")
        try:
            # Create session without proxy
            session = requests.Session()
            session.proxies = {}
            
            response = session.get(url, timeout=5)
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ SUCCESS!")
                print(f"      Service: {result.get('service')}")
                print(f"      Detector: {result.get('face_detector')}")
                return url
            else:
                print(f"   ❌ HTTP {response.status_code}")
        except requests.exceptions.ConnectionError as e:
            print(f"   ❌ Connection error: {e}")
        except requests.exceptions.Timeout:
            print(f"   ❌ Timeout")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Method 2: Direct curl bypass
    print(f"\n🔧 Method 2: Direct curl with --noproxy")
    print("-" * 40)
    
    for url in test_urls:
        print(f"   Testing: {url}")
        try:
            result = subprocess.run([
                'curl', '-s', '--connect-timeout', '5', 
                '--noproxy', '*', url
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout:
                print(f"   ✅ SUCCESS!")
                print(f"      Response: {result.stdout[:100]}...")
                return url
            else:
                print(f"   ❌ Curl failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            print(f"   ❌ Timeout")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Method 3: Check if WSL service is actually running
    print(f"\n🔧 Method 3: Check WSL Service Status")
    print("-" * 40)
    
    try:
        # Check if service process exists
        result = subprocess.run([
            'wsl', '-d', 'Ubuntu-22.04', '--', 'bash', '-c',
            'ps aux | grep -v grep | grep unified_scrfd_service'
        ], capture_output=True, text=True)
        
        if result.stdout.strip():
            print(f"   ✅ Service process found:")
            print(f"      {result.stdout.strip()}")
        else:
            print(f"   ❌ Service process not found")
            
        # Check port binding
        result = subprocess.run([
            'wsl', '-d', 'Ubuntu-22.04', '--', 'bash', '-c',
            'netstat -tlnp | grep :8003'
        ], capture_output=True, text=True)
        
        if result.stdout.strip():
            print(f"   ✅ Port 8003 is bound:")
            print(f"      {result.stdout.strip()}")
        else:
            print(f"   ❌ Port 8003 not bound")
            
    except Exception as e:
        print(f"   ❌ WSL check error: {e}")
    
    return None

def suggest_solutions():
    """Suggest solutions for proxy issues"""
    
    print(f"\n💡 Proxy Solutions")
    print("=" * 60)
    
    print(f"🔧 Solution 1: Temporary Proxy Disable")
    print(f"   • Close Clash temporarily")
    print(f"   • Test connectivity")
    print(f"   • Restart services")
    
    print(f"\n🔧 Solution 2: Proxy Bypass Configuration")
    print(f"   • Add to Clash bypass list:")
    print(f"     - localhost")
    print(f"     - 127.0.0.1") 
    print(f"     - 172.22.61.27 (WSL IP)")
    print(f"     - 10.0.0.0/8")
    print(f"     - 172.16.0.0/12")
    print(f"     - 192.168.0.0/16")
    
    print(f"\n🔧 Solution 3: Change Service Port")
    print(f"   • Use different port (e.g., 8005)")
    print(f"   • Avoid common proxy conflicts")
    
    print(f"\n🔧 Solution 4: Windows Service Alternative")
    print(f"   • Run service directly in Windows")
    print(f"   • Avoid WSL networking issues")

if __name__ == "__main__":
    working_url = test_with_proxy_bypass()
    if not working_url:
        suggest_solutions()
    else:
        print(f"\n✅ Working URL found: {working_url}")
