#!/usr/bin/env python3
"""
Simple Drive E Processor for Quick Test
Uses only built-in Python libraries to test the API connectivity and basic functionality.
"""

import os
import sys
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
import urllib.request
import urllib.parse
import urllib.error

# Configuration
DRIVE_E_ROOT = Path("E:/")
API_BASE_URL = "http://127.0.0.1:8002"
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.webp', '.mp4', '.avi', '.mov'}

def test_api_connectivity():
    """Test if the API is accessible."""
    try:
        response = urllib.request.urlopen(f"{API_BASE_URL}/health", timeout=5)
        if response.getcode() == 200:
            print("✅ Main API is accessible")
            return True
        else:
            print(f"❌ API returned status {response.getcode()}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to API: {e}")
        return False

def discover_test_files(max_files=5):
    """Discover a few test files."""
    files = []
    
    if not DRIVE_E_ROOT.exists():
        print(f"❌ Drive E not found at {DRIVE_E_ROOT}")
        return files
    
    print(f"🔍 Scanning {DRIVE_E_ROOT} for test files...")
    
    try:
        for ext in SUPPORTED_EXTENSIONS:
            pattern_files = list(DRIVE_E_ROOT.rglob(f"*{ext}"))
            files.extend(pattern_files[:2])  # Take 2 files per extension
            
            if len(files) >= max_files:
                files = files[:max_files]
                break
                
    except Exception as e:
        print(f"❌ Error scanning drive: {e}")
        return []
    
    print(f"📁 Found {len(files)} test files")
    for f in files:
        print(f"  📄 {f}")
    
    return files

def calculate_file_hash(file_path):
    """Calculate SHA256 hash of file."""
    try:
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print(f"❌ Failed to hash {file_path}: {e}")
        return None

def test_file_processing(file_path):
    """Test processing a single file."""
    print(f"\n🔄 Testing: {file_path}")
    
    try:
        # Get file info
        stat = file_path.stat()
        file_hash = calculate_file_hash(file_path)
        
        if not file_hash:
            return False
        
        print(f"  📊 Size: {stat.st_size:,} bytes")
        print(f"  🔑 Hash: {file_hash[:16]}...")
        
        # Test asset creation (simplified)
        asset_data = {
            'path': str(file_path.resolve()),
            'hash_sha256': file_hash,
            'file_size': stat.st_size,
            'mime_type': 'image/jpeg' if file_path.suffix.lower() in ['.jpg', '.jpeg'] else 'application/octet-stream'
        }
        
        # Convert to JSON
        json_data = json.dumps(asset_data).encode('utf-8')
        
        # Create request
        req = urllib.request.Request(
            f"{API_BASE_URL}/assets/",
            data=json_data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        try:
            response = urllib.request.urlopen(req, timeout=30)
            if response.getcode() in [200, 201]:
                result = json.loads(response.read().decode())
                asset_id = result.get('id')
                print(f"  ✅ Asset created with ID: {asset_id}")
                return True
            elif response.getcode() == 409:
                print(f"  📄 Asset already exists")
                return True
            else:
                print(f"  ❌ Asset creation failed: {response.getcode()}")
                return False
                
        except urllib.error.HTTPError as e:
            if e.code == 409:
                print(f"  📄 Asset already exists")
                return True
            else:
                print(f"  ❌ HTTP Error: {e.code}")
                return False
                
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    """Main test function."""
    print("🧪 Drive E Quick Test (Simplified)")
    print("=" * 40)
    
    # Test API connectivity
    if not test_api_connectivity():
        print("\n❌ Cannot proceed without API access")
        return False
    
    # Discover test files
    test_files = discover_test_files(5)
    
    if not test_files:
        print("\n❌ No test files found")
        return False
    
    # Test processing
    success_count = 0
    for file_path in test_files:
        if test_file_processing(file_path):
            success_count += 1
    
    # Results
    print(f"\n📊 Test Results:")
    print(f"  📁 Files tested: {len(test_files)}")
    print(f"  ✅ Successful: {success_count}")
    print(f"  ❌ Failed: {len(test_files) - success_count}")
    print(f"  📈 Success rate: {(success_count / len(test_files) * 100):.1f}%")
    
    if success_count > 0:
        print(f"\n🎉 Basic functionality works!")
        print(f"💡 You can now proceed with full processing using the backend environment")
        return True
    else:
        print(f"\n❌ Tests failed - check API services")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
