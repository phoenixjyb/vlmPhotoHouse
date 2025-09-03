#!/usr/bin/env python3
"""
Fresh start for face detection and recognition processing
Process 50 images, then pause for verification
"""

import sqlite3
import os
import time
import requests

def clean_start_fresh_processing():
    """Clean start - remove old data and process fresh"""
    
    print("🧹 FRESH START - Cleaning Previous Data")
    print("=" * 60)
    
    # Clear face detection data
    try:
        conn = sqlite3.connect('app.db')
        cursor = conn.cursor()
        
        # Count existing face detections
        cursor.execute("SELECT COUNT(*) FROM face_detections")
        old_count = cursor.fetchone()[0]
        
        # Clear all face detection data for fresh start
        cursor.execute("DELETE FROM face_detections")
        conn.commit()
        
        print(f"✅ Cleared {old_count} old face detection records")
        
        # Show sample of images we'll process
        cursor.execute("""
            SELECT id, path FROM assets 
            WHERE mime LIKE 'image/%' AND id > 5 
            ORDER BY id LIMIT 10
        """)
        sample_images = cursor.fetchall()
        
        print(f"\n📂 Sample images to process:")
        for img_id, path in sample_images:
            filename = os.path.basename(path)
            print(f"   {img_id}: {filename}")
        
        # Total count
        cursor.execute("""
            SELECT COUNT(*) FROM assets 
            WHERE mime LIKE 'image/%' AND id > 5
        """)
        total_images = cursor.fetchone()[0]
        print(f"\n📊 Total images available: {total_images}")
        print(f"🎯 Will process first 50 images")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Database cleanup error: {e}")
        return False
    
    # Clean embedding files directory (if exists)
    embedding_dir = "embeddings"
    if os.path.exists(embedding_dir):
        import shutil
        try:
            shutil.rmtree(embedding_dir)
            print(f"✅ Cleared embeddings directory")
        except Exception as e:
            print(f"⚠️ Could not clear embeddings dir: {e}")
    
    print(f"\n🚀 Starting fresh face detection and recognition processing...")
    return True

def verify_service_ready():
    """Verify the unified service is ready"""
    print(f"\n🔍 Verifying Service Status...")
    
    session = requests.Session()
    session.proxies = {'http': None, 'https': None}
    
    try:
        response = session.get("http://172.22.61.27:8003/status", timeout=10)
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Service Ready:")
            print(f"   Service: {status.get('service')}")
            print(f"   Detector: {status.get('face_detector')}")
            print(f"   GPU Providers: {status.get('providers')}")
            return True
        else:
            print(f"❌ Service not ready: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Service check error: {e}")
        return False

if __name__ == "__main__":
    # Clean start
    if clean_start_fresh_processing():
        
        # Verify service is ready
        if verify_service_ready():
            print(f"\n🎯 Ready to start processing!")
            print(f"Next step: Run enhanced_face_orchestrator_unified.py --batch-size 50")
            print(f"Then we'll pause at 50 images for verification")
        else:
            print(f"\n❌ Service not ready. Please start unified service first.")
    else:
        print(f"\n❌ Cleanup failed. Please check database connection.")
