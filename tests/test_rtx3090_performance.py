#!/usr/bin/env python3

import requests
import sqlite3
import json
import time
import os
import threading
import subprocess
import base64
from datetime import datetime

def test_face_inference_correct_endpoint():
    """Test the running LVFace service on port 8003 with correct /embed endpoint"""
    
    print("🧪 TESTING LVFace SERVICE WITH GPU MONITORING")
    print("=" * 60)
    
    # Check service health
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
    
    # Get test images from database
    print("\n📸 Getting test images from database...")
    conn = sqlite3.connect('metadata.sqlite')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, path 
        FROM assets 
        WHERE mime LIKE 'image/%' 
        AND path IS NOT NULL
        LIMIT 3
    """)
    
    images = cursor.fetchall()
    conn.close()
    
    if not images:
        print("❌ No images found in database")
        return
    
    print(f"📊 Found {len(images)} test images")
    
    # Start GPU monitoring
    print("\n🖥️  Starting RTX 3090 monitoring...")
    monitor_cmd = 'wsl -d Ubuntu-22.04 bash -c "watch -n 1 \'nvidia-smi --query-gpu=timestamp,name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits | grep RTX\'"'
    
    # Test the /embed endpoint
    print(f"\n🔍 Testing /embed endpoint with {len(images)} images...")
    
    inference_times = []
    
    for i, (asset_id, image_path) in enumerate(images):
        if not os.path.exists(image_path):
            print(f"  ❌ Image {i+1} not found: {image_path}")
            continue
            
        try:
            print(f"  📸 Processing image {i+1}: {os.path.basename(image_path)}")
            
            # Read and encode image to base64
            with open(image_path, 'rb') as img_file:
                image_data = img_file.read()
                image_b64 = base64.b64encode(image_data).decode('utf-8')
            
            # Start timing
            start_time = time.time()
            
            # Send request to /embed endpoint
            response = requests.post(
                "http://localhost:8003/embed",
                json={'image': image_b64},
                timeout=30
            )
            
            end_time = time.time()
            inference_time = end_time - start_time
            
            if response.status_code == 200:
                result_data = response.json()
                inference_times.append(inference_time)
                
                print(f"    ✅ SUCCESS! Time: {inference_time:.3f}s")
                
                # Show embedding info
                if 'embedding' in result_data:
                    embedding = result_data['embedding']
                    print(f"    🧠 Embedding size: {len(embedding)}")
                    print(f"    📐 Embedding shape: {result_data.get('shape', 'N/A')}")
                
                # Performance assessment
                if inference_time < 0.05:
                    print("    🚀 BLAZING FAST: Excellent RTX 3090 performance!")
                elif inference_time < 0.1:
                    print("    ⚡ FAST: Good GPU acceleration")
                elif inference_time < 0.3:
                    print("    ✅ OK: Decent performance")
                else:
                    print("    ⚠️  SLOW: Possible CPU fallback")
                    
            else:
                print(f"    ❌ Error {response.status_code}: {response.text[:100]}...")
                
        except Exception as e:
            print(f"    ❌ Exception: {str(e)[:100]}...")
        
        # Small delay between requests
        time.sleep(0.5)
    
    # Results summary
    print(f"\n📊 INFERENCE PERFORMANCE RESULTS")
    print("=" * 50)
    
    if inference_times:
        avg_time = sum(inference_times) / len(inference_times)
        min_time = min(inference_times)
        max_time = max(inference_times)
        
        print(f"✅ Successfully processed: {len(inference_times)} images")
        print(f"⚡ Average inference: {avg_time:.4f}s")
        print(f"🚀 Fastest: {min_time:.4f}s")
        print(f"🐌 Slowest: {max_time:.4f}s")
        
        # Performance assessment
        if avg_time < 0.05:
            print("🚀 PERFORMANCE: EXCELLENT - RTX 3090 at full power!")
            performance_grade = "A+"
        elif avg_time < 0.1:
            print("⚡ PERFORMANCE: VERY GOOD - Strong GPU acceleration")
            performance_grade = "A"
        elif avg_time < 0.2:
            print("✅ PERFORMANCE: GOOD - Decent GPU usage")
            performance_grade = "B"
        elif avg_time < 0.5:
            print("⚠️  PERFORMANCE: MODERATE - Some GPU usage")
            performance_grade = "C"
        else:
            print("🐌 PERFORMANCE: SLOW - Likely CPU fallback")
            performance_grade = "D"
            
        # Processing rate calculations
        images_per_second = 1 / avg_time
        images_per_hour = images_per_second * 3600
        
        print(f"📈 Processing rate: {images_per_second:.1f} images/second")
        print(f"📊 Processing rate: {images_per_hour:.0f} images/hour")
        
        # Estimate for full dataset
        total_images = 6559  # From previous assessment
        estimated_hours = total_images / images_per_hour
        estimated_minutes = estimated_hours * 60
        
        if estimated_hours < 1:
            print(f"🎯 Full dataset ({total_images:,} images) ETA: {estimated_minutes:.0f} minutes")
        else:
            print(f"🎯 Full dataset ({total_images:,} images) ETA: {estimated_hours:.1f} hours")
            
        print(f"🏆 Performance Grade: {performance_grade}")
        
        # GPU usage recommendation
        print(f"\n🖥️  RTX 3090 GPU STATUS")
        if avg_time < 0.1:
            print("✅ GPU appears to be properly utilized")
            print("🚀 Ready for large-scale face processing!")
        else:
            print("⚠️  GPU utilization may not be optimal")
            print("💡 Consider checking CUDA/GPU configuration")
    else:
        print("❌ No successful inferences")
        
    # Check current GPU usage
    print(f"\n🔍 Checking current RTX 3090 status...")
    try:
        result = subprocess.run(
            'wsl -d Ubuntu-22.04 bash -c "nvidia-smi --query-gpu=name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits | grep RTX"',
            shell=True, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            gpu_info = result.stdout.strip()
            if gpu_info:
                parts = gpu_info.split(', ')
                if len(parts) >= 6:
                    print(f"🖥️  GPU: {parts[0]}")
                    print(f"⚡ GPU Utilization: {parts[1]}%")
                    print(f"💾 Memory Utilization: {parts[2]}%")
                    print(f"📊 Memory Used: {parts[3]}MB / {parts[4]}MB")
                    print(f"🌡️  Temperature: {parts[5]}°C")
    except Exception as e:
        print(f"❌ Could not get current GPU stats: {e}")
    
    return inference_times

if __name__ == "__main__":
    test_face_inference_correct_endpoint()
