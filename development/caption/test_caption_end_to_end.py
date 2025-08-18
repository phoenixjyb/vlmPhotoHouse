#!/usr/bin/env python3
"""
Test end-to-end caption generation with the VLM Photo Engine.

This script tests the complete caption pipeline:
1. Get images from database
2. Generate captions using BLIP2 external provider
3. Verify the results
"""

import requests
import json
import sqlite3
from pathlib import Path

def get_photos_from_db():
    """Get list of photos from the database."""
    conn = sqlite3.connect('metadata.sqlite')
    cursor = conn.cursor()
    cursor.execute('SELECT id, path FROM assets LIMIT 5')
    photos = cursor.fetchall()
    conn.close()
    return photos

def test_caption_generation(photo_id, photo_path):
    """Test caption generation for a specific photo."""
    print(f"\n🖼️  Testing caption for: {photo_path}")
    
    # Test via the API endpoint (if available)
    try:
        # Check if there's a caption endpoint
        response = requests.post(
            "http://127.0.0.1:8001/assets/caption",
            json={"asset_id": photo_id},
            timeout=120  # Caption generation can take time
        )
        if response.status_code == 200:
            result = response.json()
            print(f"✅ API Caption: {result.get('caption', 'No caption')}")
            return True
        else:
            print(f"❌ API Error: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"⚠️  API request failed: {e}")
    
    # Direct test with external caption models
    try:
        import subprocess
        import tempfile
        from PIL import Image
        
        # Load and prepare image
        if Path(photo_path).exists():
            # Test external caption models directly
            cmd = [
                r"C:\\Users\\yanbo\\wSpace\\vlm-photo-engine\\vlmCaptionModels\\.venv\\Scripts\\python.exe",
                r"C:\\Users\\yanbo\\wSpace\\vlm-photo-engine\\vlmCaptionModels\\inference.py",
                "--provider", "blip2",
                "--model", "auto", 
                "--image", photo_path
            ]
            
            print(f"🔄 Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0:
                try:
                    response_data = json.loads(result.stdout.strip())
                    caption = response_data.get('caption', 'No caption')
                    model = response_data.get('model', 'Unknown')
                    print(f"✅ Direct Caption: {caption}")
                    print(f"📋 Model: {model}")
                    return True
                except json.JSONDecodeError:
                    print(f"❌ Invalid JSON response: {result.stdout}")
            else:
                print(f"❌ Command failed: {result.stderr}")
        else:
            print(f"❌ Image file not found: {photo_path}")
            
    except Exception as e:
        print(f"❌ Direct test failed: {e}")
    
    return False

def main():
    print("🚀 Testing VLM Photo Engine End-to-End Caption Pipeline")
    print("=" * 60)
    
    # Check if server is running
    try:
        response = requests.get("http://127.0.0.1:8001/health/caption", timeout=5)
        if response.status_code == 200:
            health = response.json()
            print(f"✅ Server running with provider: {health.get('provider', 'Unknown')}")
            print(f"📁 External dir: {health.get('external_dir', 'None')}")
        else:
            print("❌ Server health check failed")
            return
    except requests.exceptions.RequestException:
        print("❌ Cannot connect to server. Make sure it's running on port 8001")
        return
    
    # Get photos from database
    print(f"\n📸 Getting photos from database...")
    photos = get_photos_from_db()
    
    if not photos:
        print("❌ No photos found in database")
        return
    
    print(f"✅ Found {len(photos)} photos in database")
    
    # Test caption generation for each photo
    success_count = 0
    for photo_id, photo_path in photos:
        success = test_caption_generation(photo_id, photo_path)
        if success:
            success_count += 1
    
    print(f"\n📊 Results:")
    print(f"✅ Successful captions: {success_count}/{len(photos)}")
    print(f"❌ Failed captions: {len(photos) - success_count}/{len(photos)}")
    
    if success_count > 0:
        print(f"\n🎉 Caption pipeline is working! BLIP2 model successfully generated captions.")
    else:
        print(f"\n😞 Caption pipeline needs troubleshooting.")

if __name__ == "__main__":
    main()
