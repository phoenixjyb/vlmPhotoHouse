#!/usr/bin/env python3

import requests
import sqlite3
import json
import time
import os

def test_face_inference_service():
    """Test the running face inference service on port 8003"""
    
    print("🧪 TESTING FACE INFERENCE SERVICE")
    print("=" * 50)
    
    # First check service health
    try:
        response = requests.get("http://localhost:8003/health", timeout=5)
        if response.status_code == 200:
            health_data = response.json()
            print("✅ Service Health:")
            for key, value in health_data.items():
                print(f"  {key}: {value}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Cannot connect to service: {e}")
        return
    
    # Get a real image from database
    print("\n📸 Getting test image from database...")
    conn = sqlite3.connect('metadata.sqlite')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, path 
        FROM assets 
        WHERE mime LIKE 'image/%' 
        AND path IS NOT NULL
        LIMIT 1
    """)
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print("❌ No images found in database")
        return
    
    asset_id, image_path = result
    print(f"📁 Test image: {image_path}")
    
    if not os.path.exists(image_path):
        print(f"❌ Image file not found: {image_path}")
        return
    
    # Test different possible endpoints
    endpoints_to_try = [
        "/infer",
        "/detect_faces", 
        "/inference",
        "/predict",
        "/extract_features"
    ]
    
    for endpoint in endpoints_to_try:
        print(f"\n🔍 Testing endpoint: {endpoint}")
        
        try:
            start_time = time.time()
            
            with open(image_path, 'rb') as img_file:
                files = {'image': img_file}
                response = requests.post(
                    f"http://localhost:8003{endpoint}",
                    files=files,
                    timeout=30
                )
            
            end_time = time.time()
            inference_time = end_time - start_time
            
            if response.status_code == 200:
                print(f"  ✅ SUCCESS! Time: {inference_time:.3f}s")
                try:
                    result_data = response.json()
                    print(f"  📊 Result keys: {list(result_data.keys())}")
                    
                    # Show relevant face data
                    if 'faces' in result_data:
                        faces = result_data['faces']
                        print(f"  👤 Faces detected: {len(faces)}")
                        if faces:
                            face = faces[0]
                            print(f"  📐 First face confidence: {face.get('confidence', 'N/A')}")
                    
                    if 'embedding' in result_data:
                        embedding = result_data['embedding']
                        print(f"  🧠 Embedding shape: {len(embedding) if isinstance(embedding, list) else 'N/A'}")
                    
                    print(f"  ⚡ Performance: {inference_time:.3f}s - {'🚀 FAST' if inference_time < 0.1 else '⚠️ SLOW' if inference_time > 0.5 else '✅ OK'}")
                    
                    # Calculate processing rate
                    images_per_hour = 3600 / inference_time
                    print(f"  📈 Rate: {images_per_hour:.0f} images/hour")
                    
                    return endpoint, inference_time, result_data
                    
                except json.JSONDecodeError:
                    print(f"  📝 Non-JSON response: {response.text[:100]}...")
                    
            elif response.status_code == 404:
                print(f"  ❌ Endpoint not found")
            else:
                print(f"  ❌ Error {response.status_code}: {response.text[:100]}...")
                
        except Exception as e:
            print(f"  ❌ Exception: {str(e)[:100]}...")
    
    print("\n❌ No working endpoints found!")
    return None

if __name__ == "__main__":
    test_face_inference_service()
