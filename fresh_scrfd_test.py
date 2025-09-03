#!/usr/bin/env python3
"""
Fresh SCRFD Face Detection with Proper Database Schema
Clear old YOLOv8 results and run proper SCRFD detection
"""

import sqlite3
import requests
import os
import time
from datetime import datetime

class FreshSCRFDProcessor:
    def __init__(self):
        self.service_url = "http://172.22.61.27:8003"
        self.session = requests.Session()
        self.session.proxies = {'http': None, 'https': None}
        self.db_path = "metadata.sqlite"
        
    def check_service_status(self):
        """Verify SCRFD service is running"""
        try:
            response = self.session.get(f"{self.service_url}/status", timeout=5)
            if response.status_code == 200:
                status = response.json()
                print(f"✅ SCRFD Service Status:")
                print(f"   Detector: {status.get('face_detector')}")
                print(f"   Providers: {status.get('providers')}")
                return status.get('face_detector') == 'scrfd'
            else:
                print(f"❌ Service error: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Service connection error: {e}")
            return False
    
    def clear_old_yolov8_results(self):
        """Clear old YOLOv8 face detection results"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Count old results
            cursor.execute("SELECT COUNT(*) FROM face_detections WHERE detection_method = 'yolov8'")
            old_count = cursor.fetchone()[0]
            
            if old_count > 0:
                print(f"🧹 Found {old_count} old YOLOv8 detections to clear...")
                
                # Clear old YOLOv8 results
                cursor.execute("DELETE FROM face_detections WHERE detection_method = 'yolov8'")
                deleted = cursor.rowcount
                
                conn.commit()
                print(f"✅ Cleared {deleted} old YOLOv8 face detections")
            else:
                print("ℹ️ No old YOLOv8 results to clear")
            
            conn.close()
            
        except Exception as e:
            print(f"❌ Error clearing old results: {e}")
    
    def test_scrfd_with_sample(self):
        """Test SCRFD service with a known face image"""
        try:
            # Use the known good test image
            test_image = "/mnt/e/01_INCOMING/Jane/20220112_043621.jpg"
            
            print(f"🧪 Testing SCRFD with sample image...")
            response = self.session.post(
                f"{self.service_url}/process_image",
                json={"image_path": test_image},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                faces = result.get('faces', 0)
                detector = result.get('detector', 'unknown')
                
                print(f"✅ SCRFD Test Result:")
                print(f"   Faces detected: {faces}")
                print(f"   Detector: {detector}")
                
                if faces > 0:
                    detection = result['detections'][0]
                    print(f"   Sample confidence: {detection.get('confidence', 0):.3f}")
                    print(f"   Embedding size: {detection.get('embedding_size', 0)}")
                    return True
                else:
                    print("❌ No faces detected in test image")
                    return False
            else:
                print(f"❌ Test failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Test error: {e}")
            return False
    
    def get_sample_images_for_testing(self, limit=20):
        """Get a small sample of images for testing"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get sample images, prioritizing those likely to have faces
            cursor.execute("""
                SELECT id, path 
                FROM assets 
                WHERE path LIKE '%.jpg' OR path LIKE '%.jpeg' OR path LIKE '%.png'
                ORDER BY RANDOM()
                LIMIT ?
            """, (limit,))
            
            images = cursor.fetchall()
            conn.close()
            
            return images
            
        except Exception as e:
            print(f"❌ Database error: {e}")
            return []
    
    def process_sample_with_scrfd(self, images):
        """Process sample images with SCRFD and check results"""
        print(f"\n🔍 Processing {len(images)} sample images with SCRFD...")
        
        successful_detections = 0
        total_faces = 0
        
        for i, (image_id, image_path) in enumerate(images):
            try:
                # Convert to WSL path
                if image_path.startswith('E:'):
                    wsl_path = image_path.replace('E:', '/mnt/e').replace('\\', '/')
                else:
                    wsl_path = image_path.replace('\\', '/')
                
                # Call SCRFD service
                response = self.session.post(
                    f"{self.service_url}/process_image",
                    json={"image_path": wsl_path},
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    faces = result.get('faces', 0)
                    
                    if faces > 0:
                        successful_detections += 1
                        total_faces += faces
                        filename = os.path.basename(image_path)
                        print(f"✅ {filename}: {faces} faces detected")
                    
                else:
                    filename = os.path.basename(image_path)
                    print(f"❌ {filename}: Service error {response.status_code}")
                
                # Progress update
                if (i + 1) % 5 == 0:
                    print(f"📈 Progress: {i + 1}/{len(images)} - Found faces in {successful_detections} images")
                
            except Exception as e:
                filename = os.path.basename(image_path)
                print(f"❌ {filename}: Processing error - {e}")
        
        # Summary
        detection_rate = (successful_detections / len(images)) * 100 if images else 0
        avg_faces = total_faces / successful_detections if successful_detections > 0 else 0
        
        print(f"\n📊 SAMPLE PROCESSING RESULTS:")
        print(f"   Images processed: {len(images)}")
        print(f"   Images with faces: {successful_detections}")
        print(f"   Total faces found: {total_faces}")
        print(f"   Detection rate: {detection_rate:.1f}%")
        print(f"   Avg faces per image: {avg_faces:.1f}")
        
        return detection_rate > 40  # Expect much higher rate for human photos
    
    def run_diagnosis_and_test(self):
        """Run comprehensive diagnosis and small test"""
        print("🔍 FRESH SCRFD PROCESSING - DIAGNOSIS & TEST")
        print("=" * 60)
        
        # 1. Check SCRFD service
        print("1️⃣ Checking SCRFD Service...")
        if not self.check_service_status():
            print("❌ SCRFD service not available. Please start it first.")
            return False
        
        # 2. Test with known good image
        print("\n2️⃣ Testing with known face image...")
        if not self.test_scrfd_with_sample():
            print("❌ SCRFD test failed. Service may not be working correctly.")
            return False
        
        # 3. Clear old results
        print("\n3️⃣ Clearing old YOLOv8 results...")
        self.clear_old_yolov8_results()
        
        # 4. Test with sample images
        print("\n4️⃣ Testing SCRFD with sample images...")
        sample_images = self.get_sample_images_for_testing(20)
        if not sample_images:
            print("❌ No sample images found")
            return False
        
        success = self.process_sample_with_scrfd(sample_images)
        
        print("\n" + "=" * 60)
        if success:
            print("✅ DIAGNOSIS PASSED: SCRFD is working correctly!")
            print("💡 Ready to process full collection with proper SCRFD detection")
            print("🚀 Recommended next step:")
            print("   python enhanced_face_orchestrator_unified.py")
        else:
            print("❌ DIAGNOSIS FAILED: Detection rate too low")
            print("💡 Possible issues:")
            print("   • SCRFD service not properly processing images")
            print("   • Path conversion issues")
            print("   • Database save problems")
        
        return success

if __name__ == "__main__":
    processor = FreshSCRFDProcessor()
    processor.run_diagnosis_and_test()
