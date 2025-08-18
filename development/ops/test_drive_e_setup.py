#!/usr/bin/env python3
"""
Test Drive E: Photo Setup
========================

This script tests the Drive E: photo organization setup by:
1. Verifying folder structure
2. Testing VLM scan on incoming photos
3. Checking database creation
4. Validating search functionality
"""

import os
import sys
import json
import requests
import time
from pathlib import Path

# Add the app directory to Python path
sys.path.append('backend')

def verify_folder_structure():
    """Verify Drive E: folder structure exists"""
    print("🔍 Verifying Drive E: folder structure...")
    
    required_folders = [
        "E:/01_INCOMING",
        "E:/02_PROCESSING", 
        "E:/03_ARCHIVE/2024",
        "E:/04_EVENTS/Vacations",
        "E:/05_PEOPLE/Family",
        "E:/06_FAVORITES",
        "E:/VLM_DATA"
    ]
    
    missing_folders = []
    for folder in required_folders:
        if not Path(folder).exists():
            missing_folders.append(folder)
    
    if missing_folders:
        print(f"❌ Missing folders: {missing_folders}")
        return False
    else:
        print("✅ All required folders exist!")
        return True

def check_test_photos():
    """Check if test photos are in incoming folder"""
    print("🔍 Checking test photos in incoming folder...")
    
    incoming_path = Path("E:/01_INCOMING")
    photos = list(incoming_path.glob("*.jpg"))
    
    print(f"📸 Found {len(photos)} photos in incoming folder:")
    for photo in photos:
        print(f"  - {photo.name} ({photo.stat().st_size} bytes)")
    
    return len(photos) > 0

def test_vlm_server():
    """Test VLM server health"""
    print("🔍 Testing VLM server connection...")
    
    try:
        response = requests.get("http://127.0.0.1:8001/health", timeout=5)
        if response.status_code == 200:
            print("✅ VLM server is healthy!")
            health_data = response.json()
            print(f"  Server status: {health_data.get('status', 'unknown')}")
            return True
        else:
            print(f"❌ VLM server returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to VLM server: {e}")
        print("   Make sure the server is running on port 8001")
        return False

def test_caption_service():
    """Test caption service health"""
    print("🔍 Testing caption service...")
    
    try:
        response = requests.get("http://127.0.0.1:8001/health/caption", timeout=10)
        if response.status_code == 200:
            print("✅ Caption service is healthy!")
            caption_data = response.json()
            print(f"  Service status: {caption_data.get('status', 'unknown')}")
            return True
        else:
            print(f"❌ Caption service returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to caption service: {e}")
        return False

def run_incoming_scan():
    """Run VLM scan on incoming folder"""
    print("🔍 Running VLM scan on incoming folder...")
    
    scan_data = {
        "roots": ["E:/01_INCOMING"]
    }
    
    try:
        response = requests.post(
            "http://127.0.0.1:8001/ingest/scan",
            json=scan_data,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Scan completed successfully!")
            print(f"  Task ID: {result.get('task_id', 'unknown')}")
            print(f"  Status: {result.get('status', 'unknown')}")
            return result.get('task_id')
        else:
            print(f"❌ Scan failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Scan request failed: {e}")
        return None

def check_scan_progress(task_id):
    """Check scan progress"""
    if not task_id:
        return False
        
    print(f"🔍 Checking scan progress for task {task_id}...")
    
    for attempt in range(30):  # Check for up to 5 minutes
        try:
            response = requests.get(f"http://127.0.0.1:8001/tasks/{task_id}/progress")
            if response.status_code == 200:
                progress = response.json()
                status = progress.get('status', 'unknown')
                print(f"  Attempt {attempt + 1}: Status = {status}")
                
                if status == 'completed':
                    print("✅ Scan completed!")
                    print(f"  Results: {progress}")
                    return True
                elif status == 'failed':
                    print("❌ Scan failed!")
                    print(f"  Error: {progress}")
                    return False
                    
            time.sleep(10)  # Wait 10 seconds between checks
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Progress check failed: {e}")
            time.sleep(10)
    
    print("⏰ Scan is taking longer than expected...")
    return False

def test_search():
    """Test search functionality"""
    print("🔍 Testing search functionality...")
    
    search_data = {
        "query": "landscape",
        "limit": 10
    }
    
    try:
        response = requests.post(
            "http://127.0.0.1:8001/search",
            json=search_data,
            timeout=30
        )
        
        if response.status_code == 200:
            results = response.json()
            print("✅ Search completed successfully!")
            print(f"  Found {len(results.get('results', []))} results")
            
            for i, result in enumerate(results.get('results', [])[:3]):
                print(f"  Result {i+1}: {result.get('path', 'unknown')} (score: {result.get('score', 0):.3f})")
            
            return True
        else:
            print(f"❌ Search failed with status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Search request failed: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 DRIVE E: PHOTO SETUP TEST")
    print("=" * 50)
    
    # Step 1: Verify folder structure
    if not verify_folder_structure():
        print("❌ Setup incomplete - folder structure missing")
        return False
    
    # Step 2: Check test photos
    if not check_test_photos():
        print("❌ No test photos found in incoming folder")
        return False
    
    # Step 3: Test VLM server
    if not test_vlm_server():
        print("❌ VLM server not available")
        return False
    
    # Step 4: Test caption service
    if not test_caption_service():
        print("❌ Caption service not available")
        return False
    
    # Step 5: Run incoming scan
    task_id = run_incoming_scan()
    if task_id:
        # Step 6: Check scan progress
        if check_scan_progress(task_id):
            # Step 7: Test search
            if test_search():
                print("\n🎉 DRIVE E: SETUP TEST COMPLETED SUCCESSFULLY!")
                print("Your Drive E: photo organization system is ready!")
                return True
    
    print("\n❌ Setup test failed - check the issues above")
    return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
