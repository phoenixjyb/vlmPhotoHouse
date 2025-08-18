#!/usr/bin/env python3
"""Simple HTTP test using only standard library."""

import urllib.request
import json

def test_health_simple():
    try:
        print("Testing health endpoint with urllib...")
        with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=5) as response:
            data = response.read()
            print(f"Status Code: {response.getcode()}")
            print(f"Response: {data.decode('utf-8')}")
            return response.getcode() == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = test_health_simple()
    if success:
        print("\u2705 Server is working correctly!")
    else:
        print("\u274c Server test failed!")
