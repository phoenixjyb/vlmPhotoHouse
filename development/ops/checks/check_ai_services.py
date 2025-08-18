#!/usr/bin/env python3
"""
Check AI Services Configuration
===============================
"""

import requests
import json

def check_ai_services():
    """Check what AI services are configured"""
    try:
        print("🔍 Checking AI services configuration...")
        
        response = requests.get('http://127.0.0.1:8001/health')
        if response.status_code == 200:
            health = response.json()
            
            print("\n🤖 Current AI Services:")
            print(f"  Caption Provider: {health['caption']['provider']}")
            print(f"  Caption Device: {health['caption']['device']}")
            print(f"  Caption Model: {health['caption']['model']}")
            
            print(f"\n👤 Face Services:")
            print(f"  Embed Provider: {health['face']['embed_provider']}")
            print(f"  Detect Provider: {health['face']['detect_provider']}")
            print(f"  Device: {health['face']['device']}")
            
            print(f"\n📈 Index Status:")
            print(f"  Initialized: {health['index']['initialized']}")
            print(f"  Size: {health['index']['size']}")
            print(f"  Dimension: {health['index']['dim']}")
            
            return health
        else:
            print(f"❌ Error: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    check_ai_services()
