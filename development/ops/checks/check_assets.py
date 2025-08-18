#!/usr/bin/env python3
"""
Check Assets in VLM Database
============================

Simple script to check what assets are in the VLM database.
"""

import requests
import json

def check_assets():
    """Check what assets are in the VLM database"""
    try:
        print("🔍 Checking VLM database assets...")
        
        # Get all assets
        response = requests.get('http://127.0.0.1:8001/assets', timeout=30)
        
        if response.status_code == 200:
            assets = response.json()
            print(f"📊 Found {len(assets)} assets in database")
            
            if assets:
                print("\n📸 Assets:")
                # Show first 10 assets
                for i in range(min(len(assets), 10)):
                    asset = assets[i]
                    path = asset.get('path', 'unknown')
                    print(f"  {i+1}. {path}")
                
                if len(assets) > 10:
                    print(f"  ... and {len(assets) - 10} more")
                    
                # Show some sample asset details
                if len(assets) > 0:
                    sample = assets[0]
                    print(f"\n📋 Sample asset details:")
                    print(f"  ID: {sample.get('id', 'unknown')}")
                    print(f"  Path: {sample.get('path', 'unknown')}")
                    print(f"  Width x Height: {sample.get('width', '?')} x {sample.get('height', '?')}")
                    print(f"  File size: {sample.get('file_size', '?')} bytes")
                    print(f"  Created: {sample.get('created_at', 'unknown')}")
                
            else:
                print("🗃️ No assets found in database")
                
        else:
            print(f"❌ Error: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")

def initialize_vector_index():
    """Initialize the vector index for search functionality"""
    try:
        print("\n🔧 Initializing vector index...")
        
        response = requests.post(
            'http://127.0.0.1:8001/vector-index/rebuild',
            timeout=60  # This might take a while
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Vector index initialization started!")
            print(f"Response: {result}")
            return True
        else:
            print(f"❌ Failed to initialize vector index: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Vector index initialization error: {e}")
        return False

def test_search():
    """Test search functionality"""
    try:
        print("\n🔍 Testing search functionality...")
        
        search_data = {
            "query": "photo",
            "limit": 5
        }
        
        response = requests.post(
            'http://127.0.0.1:8001/search/vector',
            json=search_data,
            timeout=30
        )
        
        if response.status_code == 200:
            results = response.json()
            print(f"✅ Search successful!")
            print(f"📊 Found {len(results.get('results', []))} results")
            
            for i, result in enumerate(results.get('results', [])[:3]):
                print(f"  {i+1}. {result.get('path', 'unknown')} (score: {result.get('score', 0):.3f})")
                
        else:
            print(f"❌ Search failed: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Search error: {e}")

if __name__ == "__main__":
    check_assets()
    initialize_vector_index()
    test_search()
