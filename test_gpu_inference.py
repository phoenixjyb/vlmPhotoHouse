#!/usr/bin/env python3

import requests
import sqlite3
import json
import time
import os
import threading
import subprocess
from datetime import datetime

class GPUMonitor:
    def __init__(self):
        self.monitoring = False
        self.gpu_stats = []
        
    def start_monitoring(self):
        """Start GPU monitoring in background thread"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_gpu)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        print("🖥️  GPU monitoring started...")
    
    def stop_monitoring(self):
        """Stop GPU monitoring"""
        self.monitoring = False
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join()
        print("🖥️  GPU monitoring stopped.")
    
    def _monitor_gpu(self):
        """Monitor GPU usage via WSL nvidia-smi"""
        while self.monitoring:
            try:
                # Get GPU stats via WSL
                cmd = 'wsl -d Ubuntu-22.04 bash -c "nvidia-smi --query-gpu=timestamp,name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits"'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if 'RTX 3090' in line:
                            parts = line.split(', ')
                            if len(parts) >= 8:
                                stat = {
                                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                                    'gpu_util': parts[2],
                                    'mem_util': parts[3], 
                                    'mem_used': parts[4],
                                    'mem_total': parts[5],
                                    'temp': parts[6],
                                    'power': parts[7]
                                }
                                self.gpu_stats.append(stat)
                                
                                # Keep only last 20 readings
                                if len(self.gpu_stats) > 20:
                                    self.gpu_stats.pop(0)
                                    
                                # Print real-time stats
                                print(f"⚡ {stat['timestamp']} | GPU: {stat['gpu_util']}% | Mem: {stat['mem_util']}% | Temp: {stat['temp']}°C | Power: {stat['power']}W")
                
            except Exception as e:
                print(f"⚠️  GPU monitoring error: {e}")
            
            time.sleep(2)  # Check every 2 seconds
    
    def get_avg_stats(self):
        """Get average GPU statistics"""
        if not self.gpu_stats:
            return None
            
        try:
            gpu_utils = [float(s['gpu_util']) for s in self.gpu_stats if s['gpu_util'].replace('.', '').isdigit()]
            mem_utils = [float(s['mem_util']) for s in self.gpu_stats if s['mem_util'].replace('.', '').isdigit()]
            
            return {
                'avg_gpu_util': sum(gpu_utils) / len(gpu_utils) if gpu_utils else 0,
                'max_gpu_util': max(gpu_utils) if gpu_utils else 0,
                'avg_mem_util': sum(mem_utils) / len(mem_utils) if mem_utils else 0,
                'max_mem_util': max(mem_utils) if mem_utils else 0,
                'samples': len(self.gpu_stats)
            }
        except:
            return None

def test_face_inference_with_gpu_monitoring():
    """Test face inference while monitoring RTX 3090 GPU usage"""
    
    print("🧪 FACE INFERENCE + GPU MONITORING TEST")
    print("=" * 60)
    
    # Initialize GPU monitor
    gpu_monitor = GPUMonitor()
    
    # Check service health first
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
        LIMIT 5
    """)
    
    images = cursor.fetchall()
    conn.close()
    
    if not images:
        print("❌ No images found in database")
        return
    
    print(f"📊 Found {len(images)} test images")
    
    # Start GPU monitoring
    gpu_monitor.start_monitoring()
    
    # Test different endpoints with real images
    endpoints_to_try = ["/infer", "/detect_faces", "/inference", "/predict", "/extract_features"]
    
    successful_endpoint = None
    inference_times = []
    
    for endpoint in endpoints_to_try:
        print(f"\n🔍 Testing endpoint: {endpoint}")
        
        for i, (asset_id, image_path) in enumerate(images[:2]):  # Test with first 2 images
            if not os.path.exists(image_path):
                print(f"  ❌ Image not found: {image_path}")
                continue
                
            try:
                print(f"  📸 Processing image {i+1}: {os.path.basename(image_path)}")
                
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
                    print(f"    ✅ SUCCESS! Time: {inference_time:.3f}s")
                    inference_times.append(inference_time)
                    successful_endpoint = endpoint
                    
                    try:
                        result_data = response.json()
                        
                        # Show face detection results
                        if 'faces' in result_data:
                            faces = result_data['faces']
                            print(f"    👤 Faces detected: {len(faces)}")
                        
                        if 'embedding' in result_data:
                            embedding = result_data['embedding']
                            print(f"    🧠 Embedding size: {len(embedding) if isinstance(embedding, list) else 'N/A'}")
                            
                    except json.JSONDecodeError:
                        print(f"    📝 Non-JSON response")
                        
                elif response.status_code == 404:
                    print(f"    ❌ Endpoint not found")
                    break  # Try next endpoint
                else:
                    print(f"    ❌ Error {response.status_code}")
                    
                # Small delay between requests
                time.sleep(1)
                
            except Exception as e:
                print(f"    ❌ Exception: {str(e)[:50]}...")
        
        if successful_endpoint:
            break  # Found working endpoint
    
    # Stop monitoring and get results
    time.sleep(3)  # Allow final GPU readings
    gpu_monitor.stop_monitoring()
    
    print(f"\n📊 RESULTS SUMMARY")
    print("=" * 40)
    
    if successful_endpoint:
        print(f"✅ Working endpoint: {successful_endpoint}")
        if inference_times:
            avg_time = sum(inference_times) / len(inference_times)
            min_time = min(inference_times)
            max_time = max(inference_times)
            
            print(f"⚡ Average inference: {avg_time:.3f}s")
            print(f"🚀 Fastest: {min_time:.3f}s")
            print(f"🐌 Slowest: {max_time:.3f}s")
            
            # Performance assessment
            if avg_time < 0.1:
                print("🚀 EXCELLENT: RTX 3090 GPU performance!")
            elif avg_time < 0.3:
                print("✅ GOOD: Decent GPU acceleration")
            else:
                print("⚠️  SLOW: Possible CPU fallback")
                
            # Processing rate
            images_per_hour = 3600 / avg_time
            print(f"📈 Processing rate: {images_per_hour:.0f} images/hour")
            
            # Estimate for full dataset
            total_images = 6559  # From previous assessment
            estimated_hours = total_images / images_per_hour
            print(f"🎯 Full dataset ({total_images:,} images) ETA: {estimated_hours:.1f} hours")
    else:
        print("❌ No working endpoints found")
    
    # GPU stats summary
    gpu_stats = gpu_monitor.get_avg_stats()
    if gpu_stats:
        print(f"\n🖥️  RTX 3090 GPU USAGE SUMMARY")
        print(f"📊 Average GPU utilization: {gpu_stats['avg_gpu_util']:.1f}%")
        print(f"📊 Peak GPU utilization: {gpu_stats['max_gpu_util']:.1f}%") 
        print(f"💾 Average memory utilization: {gpu_stats['avg_mem_util']:.1f}%")
        print(f"💾 Peak memory utilization: {gpu_stats['max_mem_util']:.1f}%")
        print(f"📈 Monitoring samples: {gpu_stats['samples']}")
        
        if gpu_stats['avg_gpu_util'] > 70:
            print("🚀 EXCELLENT: High GPU utilization - RTX 3090 is working hard!")
        elif gpu_stats['avg_gpu_util'] > 30:
            print("✅ GOOD: Moderate GPU usage")
        else:
            print("⚠️  LOW: GPU might not be fully utilized")
    else:
        print("❌ No GPU stats collected")
    
    return successful_endpoint, inference_times, gpu_stats

if __name__ == "__main__":
    test_face_inference_with_gpu_monitoring()
