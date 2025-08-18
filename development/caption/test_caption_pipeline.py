#!/usr/bin/env python3
"""End-to-end caption testing script."""

import requests
import json
import time
from pathlib import Path

def test_ingest_and_caption():
    """Test the full ingestion and caption pipeline."""
    base_url = "http://127.0.0.1:8001"
    
    # Test server health first
    print("1. Testing server health...")
    try:
        health = requests.get(f"{base_url}/health", timeout=5)
        print(f"   Health status: {health.status_code}")
        print(f"   Response: {health.json()}")
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        return False
    
    # Test caption health
    print("\n2. Testing caption service health...")
    try:
        caption_health = requests.get(f"{base_url}/health/caption", timeout=10)
        print(f"   Caption health: {caption_health.status_code}")
        caption_data = caption_health.json()
        print(f"   Provider: {caption_data.get('provider', 'unknown')}")
        print(f"   Model: {caption_data.get('model', 'unknown')}")
    except Exception as e:
        print(f"   ❌ Caption health check failed: {e}")
        return False
    
    # Trigger ingestion of test photos
    print("\n3. Triggering photo ingestion...")
    test_photos_dir = Path("test_photos").absolute()
    if not test_photos_dir.exists():
        print(f"   ❌ Test photos directory not found: {test_photos_dir}")
        return False
        
    ingest_payload = {"roots": [str(test_photos_dir)]}
    try:
        ingest_response = requests.post(f"{base_url}/ingest/scan", 
                                      json=ingest_payload, timeout=30)
        print(f"   Ingest status: {ingest_response.status_code}")
        ingest_data = ingest_response.json()
        print(f"   New assets: {ingest_data.get('new_assets', 0)}")
        print(f"   Skipped: {ingest_data.get('skipped', 0)}")
        print(f"   Time: {ingest_data.get('elapsed_sec', 0)}s")
    except Exception as e:
        print(f"   ❌ Ingestion failed: {e}")
        return False
    
    # Wait for task processing
    print("\n4. Waiting for task processing...")
    for i in range(60):  # Wait up to 60 seconds
        try:
            metrics = requests.get(f"{base_url}/metrics", timeout=5)
            metrics_data = metrics.json()
            tasks = metrics_data.get('tasks', {})
            pending = tasks.get('by_state', {}).get('pending', 0)
            running = tasks.get('by_state', {}).get('running', 0)
            done = tasks.get('by_state', {}).get('done', 0)
            
            print(f"   Tasks - Pending: {pending}, Running: {running}, Done: {done}")
            
            if pending == 0 and running == 0 and done > 0:
                print("   ✅ All tasks completed!")
                break
        except Exception as e:
            print(f"   ⚠️ Metrics check failed: {e}")
        
        time.sleep(2)
    else:
        print("   ⚠️ Timeout waiting for tasks to complete")
    
    # Check for assets and captions
    print("\n5. Checking ingested assets...")
    try:
        assets = requests.get(f"{base_url}/assets", timeout=10)
        assets_data = assets.json()
        total_assets = assets_data.get('total', 0)
        print(f"   Total assets: {total_assets}")
        
        if total_assets > 0:
            print("   Sample assets:")
            for asset in assets_data.get('assets', [])[:3]:
                print(f"     ID: {asset['id']}, Path: {asset['path']}")
    except Exception as e:
        print(f"   ❌ Assets check failed: {e}")
        return False
    
    # Test search functionality
    print("\n6. Testing search functionality...")
    try:
        search = requests.get(f"{base_url}/search", params={"q": "test_photos"}, timeout=10)
        search_data = search.json()
        print(f"   Search results: {search_data.get('total', 0)} matches")
        
        for item in search_data.get('items', [])[:3]:
            print(f"     Asset {item['id']}: {item['path']}")
    except Exception as e:
        print(f"   ❌ Search test failed: {e}")
        return False
    
    print("\n✅ End-to-end caption testing completed successfully!")
    return True

if __name__ == "__main__":
    success = test_ingest_and_caption()
    if success:
        print("\n🎉 Caption pipeline is working end-to-end!")
    else:
        print("\n❌ Caption pipeline testing failed!")
