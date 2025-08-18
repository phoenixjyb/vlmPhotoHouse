#!/usr/bin/env python3
"""Test script to check server health from a separate process."""

import requests
import sys

def test_health_endpoint():
    try:
        print("Testing health endpoint...")
        response = requests.get("http://127.0.0.1:8001/health", timeout=5)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        print(f"Headers: {dict(response.headers)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = test_health_endpoint()
    if success:
        print("✅ Server is working correctly!")
        sys.exit(0)
    else:
        print("❌ Server test failed!")
        sys.exit(1)
