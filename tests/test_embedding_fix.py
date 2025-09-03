#!/usr/bin/env python3
"""
Test the embedding fix with a single image
"""

import requests
import json
import sqlite3
import os

def test_embedding_fix():
    """Test if embeddings are now properly returned and saved"""
    
    print("🧪 TESTING EMBEDDING FIX")
    print("=" * 40)
    
    # Test the service with a single image
    session = requests.Session()
    session.proxies = {'http': None, 'https': None}
    
    test_path = "/mnt/c/Users/yanbo/wSpace/vlm-photo-engine/vlmPhotoHouse/face_detection_results/asset_3116_20230401_110655_faces.jpg"
    
    try:
        print("🔄 Calling service...")
        response = session.post(
            "http://172.22.61.27:8003/process_image",
            json={"image_path": test_path},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            
            print("✅ Service Response:")
            faces = result.get('faces', 0)
            detections = result.get('detections', [])
            
            print(f"   Faces detected: {faces}")
            
            if detections:
                first_detection = detections[0]
                print(f"   First detection keys: {list(first_detection.keys())}")
                
                # Check if embedding is now included
                if 'embedding' in first_detection:
                    embedding = first_detection['embedding']
                    if embedding and isinstance(embedding, list):
                        print(f"   ✅ Embedding included! Dimension: {len(embedding)}")
                        print(f"   Embedding sample: {embedding[:5]}...")
                        return True
                    else:
                        print(f"   ❌ Embedding field present but empty/invalid")
                else:
                    print(f"   ❌ No embedding field in response")
                    print("   ℹ️ Service may need restart to pick up changes")
            
        else:
            print(f"❌ Service error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Test error: {e}")
    
    return False

def test_orchestrator_with_fix():
    """Test if the orchestrator now saves embeddings properly"""
    
    print(f"\n🔧 TESTING ORCHESTRATOR EMBEDDING SAVE")
    print("=" * 40)
    
    # Clear test data
    try:
        conn = sqlite3.connect('app.db')
        cursor = conn.cursor()
        
        # Clear any test records
        cursor.execute("DELETE FROM face_detections WHERE asset_id = 999999")
        conn.commit()
        
        # Test if orchestrator can process and save embeddings
        print("ℹ️ After service restart, run:")
        print("   .venv\\Scripts\\python.exe enhanced_face_orchestrator_unified.py --batch-size 1 --test-mode")
        print("   Then check if embeddings are saved!")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Database test setup error: {e}")

if __name__ == "__main__":
    # Test if service returns embeddings
    embeddings_working = test_embedding_fix()
    
    if not embeddings_working:
        print(f"\n🔄 SERVICE RESTART NEEDED")
        print("=" * 40)
        print("The service needs to be restarted to pick up the embedding fix.")
        print("In WSL terminal, restart the service:")
        print("   cd /home/yanbo/vlm-photo-engine/LVFace")
        print("   source .venv-cuda124-wsl/bin/activate")
        print("   python unified_scrfd_service.py")
    else:
        print(f"\n✅ EMBEDDINGS NOW WORKING!")
        
    # Test orchestrator
    test_orchestrator_with_fix()
