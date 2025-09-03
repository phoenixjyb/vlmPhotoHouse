#!/usr/bin/env python3

import requests
import time
import sqlite3
import json
import os

def test_face_detection_performance():
    """Test actual LVFace performance with RTX 3090"""
    
    # Get a real image from our database - check actual column names first
    conn = sqlite3.connect('metadata.sqlite')
    cursor = conn.cursor()
    
    # Check table schema
    cursor.execute("PRAGMA table_info(assets)")
    columns = cursor.fetchall()
    print("📋 Available columns in assets table:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
    
    # Try different column name patterns
    cursor.execute("SELECT * FROM assets WHERE mime LIKE 'image/%' LIMIT 1")
    row = cursor.fetchone()
    
    if not row:
        print("❌ No image found in database")
        conn.close()
        return
    
    # Get column names
    column_names = [description[0] for description in cursor.description]
    asset_data = dict(zip(column_names, row))
    
    print(f"\n📸 Found asset: {asset_data}")
    
    # Try to find the file path
    possible_path_columns = ['file_path', 'path', 'filepath', 'full_path', 'location']
    file_path = None
    filename = None
    
    for col in possible_path_columns:
        if col in asset_data and asset_data[col]:
            file_path = asset_data[col]
            break
    
    # Try filename columns
    possible_name_columns = ['filename', 'name', 'file_name', 'basename']
    for col in possible_name_columns:
        if col in asset_data and asset_data[col]:
            filename = asset_data[col]
            break
    
    conn.close()
    
    if not file_path:
        print("❌ No file path found in asset data")
        print("📋 Available data:", asset_data)
        return
    
    if not filename:
        filename = os.path.basename(file_path)
    print(f"\n🧪 Testing with: {filename}")
    print(f"📁 Path: {file_path}")
    
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return
    
    try:
        # Test multiple times for accurate measurement
        times = []
        
        for i in range(3):
            print(f"\n🔍 Test {i+1}/3...")
            
            start_time = time.time()
            
            with open(file_path, 'rb') as img_file:
                files = {'image': (filename, img_file, 'image/jpeg')}
                response = requests.post(
                    "http://localhost:8003/detect_faces",
                    files=files,
                    timeout=30
                )
            
            end_time = time.time()
            inference_time = end_time - start_time
            times.append(inference_time)
            
            if response.status_code == 200:
                result = response.json()
                faces_found = len(result.get('faces', []))
                print(f"  ⏱️  Time: {inference_time:.3f}s")
                print(f"  👤 Faces: {faces_found}")
                
                # Show first face details if available
                if result.get('faces'):
                    face = result['faces'][0]
                    print(f"  📊 Confidence: {face.get('confidence', 'N/A')}")
                    print(f"  📐 BBox: {face.get('bbox', 'N/A')}")
                
            else:
                print(f"  ❌ Error: {response.status_code}")
                print(f"  📝 Response: {response.text}")
        
        if times:
            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)
            
            print(f"\n📊 PERFORMANCE RESULTS:")
            print(f"  ⚡ Average: {avg_time:.3f}s per image")
            print(f"  🚀 Fastest: {min_time:.3f}s")
            print(f"  🐌 Slowest: {max_time:.3f}s")
            
            # Calculate processing rate
            images_per_hour = 3600 / avg_time
            print(f"  📈 Rate: {images_per_hour:.0f} images/hour")
            
            # Estimate for 6,559 images
            total_hours = 6559 / images_per_hour
            print(f"  🎯 6,559 images would take: {total_hours:.1f} hours")
            
            if avg_time > 0.1:
                print(f"\n⚠️  Performance Analysis:")
                if avg_time > 0.5:
                    print("   🐌 SLOW: Might be using CPU instead of GPU")
                elif avg_time > 0.2:
                    print("   ⚠️  MODERATE: Could be a heavy model or mixed CPU/GPU")
                else:
                    print("   🚀 GOOD: Reasonable GPU performance")
                
    except Exception as e:
        print(f"❌ Error testing performance: {e}")

def check_face_service_details():
    """Get detailed info about the face service"""
    try:
        # Check if there's a model info endpoint
        response = requests.get("http://localhost:8003/info", timeout=10)
        if response.status_code == 200:
            print("🤖 SERVICE INFO:")
            print(response.json())
    except:
        pass
    
    try:
        # Check health endpoint for detailed info
        response = requests.get("http://localhost:8003/health", timeout=10)
        if response.status_code == 200:
            health_data = response.json()
            print("\n💊 HEALTH STATUS:")
            for key, value in health_data.items():
                print(f"  {key}: {value}")
    except Exception as e:
        print(f"❌ Error checking service: {e}")

if __name__ == "__main__":
    print("🧪 RTX 3090 FACE DETECTION PERFORMANCE TEST")
    print("=" * 50)
    
    check_face_service_details()
    print()
    test_face_detection_performance()
