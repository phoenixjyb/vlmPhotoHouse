#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Video Ingestion

Test if video files can now be ingested with video support enabled.
"""

import requests
import json
import sys

# Ensure UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def test_video_ingestion():
    # Test directory with video files
    test_dir = "E:/01_INCOMING/Jane/Jane20240825/Camera/音视频裁剪大师"
    
    print(f"Testing video ingestion for: {test_dir}")
    
    try:
        # Test backend health first
        health_response = requests.get("http://localhost:8000/health")
        print(f"Backend health status: {health_response.status_code}")
        
        if health_response.status_code == 200:
            health_data = health_response.json()
            print(f"Backend is healthy. Index size: {health_data.get('index', {}).get('size', 'N/A')}")
        
        # Now test ingestion
        payload = {"roots": [test_dir]}
        print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
        
        response = requests.post(
            "http://localhost:8000/ingest/scan",
            json=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json"
            },
            timeout=60
        )
        
        print(f"Ingestion response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("Ingestion successful!")
            print(f"  New assets: {result.get('new_assets', 'N/A')}")
            print(f"  Skipped: {result.get('skipped', 'N/A')}")
            print(f"  Total: {result.get('total', 'N/A')}")
        else:
            print(f"Ingestion failed: {response.text}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_video_ingestion()
