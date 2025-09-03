#!/usr/bin/env python3
"""
Enhanced Face Processing Orchestrator with Proper Face Detection

This version:
1. Uses OpenCV face detection to find faces in original image coordinates
2. Crops detected faces and sends them for embedding
3. Saves proper bounding box coordinates in original image space
"""

import sqlite3
import requests
import json
import time
import base64
import threading
import os
import cv2
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

class EnhancedFaceProcessingOrchestrator:
    def __init__(self, db_path="metadata.sqlite"):
        self.db_path = db_path
        self.service_url = "http://172.22.61.27:8003"
        self.processed_count = 0
        self.error_count = 0
        self.start_time = None
        self.lock = threading.Lock()
        self.stop_processing = False
        
        # Initialize OpenCV face detector
        # Initialize OpenCV face detection with error handling
        try:
            self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            if self.face_cascade.empty():
                print("❌ Warning: Could not load face cascade - falling back to simple detection")
                self.face_cascade = None
        except Exception as e:
            print(f"❌ Face cascade error: {e} - falling back to simple detection")
            self.face_cascade = None
        
    def detect_faces_opencv(self, image):
        """Detect faces using OpenCV and return bounding boxes in original coordinates"""
        try:
            if self.face_cascade is None or self.face_cascade.empty():
                # Fallback: return center region as face
                h, w = image.shape[:2]
                center_x, center_y = w // 4, h // 4
                face_w, face_h = w // 2, h // 2
                return [(center_x, center_y, face_w, face_h)]
            
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Ensure image is valid
            if gray.size == 0 or len(gray.shape) != 2:
                return []
            
            # Detect faces with robust parameters (exactly like debug script)
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30),
                flags=cv2.CASCADE_SCALE_IMAGE
            )
            
            return faces  # Returns [(x, y, w, h), ...]
            
        except Exception as e:
            print(f"❌ Face detection error: {e}")
            # Fallback: return center region
            try:
                h, w = image.shape[:2] if len(image.shape) >= 2 else (100, 100)
                center_x, center_y = w // 4, h // 4
                face_w, face_h = w // 2, h // 2
                return [(center_x, center_y, face_w, face_h)]
            except:
                return [(50, 50, 100, 100)]  # Absolute fallback
    
    def get_pending_images(self, batch_size=25):
        """Get batch of images that need face processing"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT a.id, a.path
            FROM assets a
            WHERE a.mime LIKE 'image/%'
            AND a.path IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM face_detections fd 
                WHERE fd.asset_id = a.id
            )
            ORDER BY a.id
            LIMIT ?
        """, (batch_size,))
        
        pending_images = cursor.fetchall()
        conn.close()
        return pending_images
    
    def save_face_detection(self, asset_id, face_bbox, embedding):
        """Save face detection with proper bounding box coordinates"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        x, y, w, h = face_bbox
        
        try:
            cursor.execute("""
                INSERT INTO face_detections 
                (asset_id, bbox_x, bbox_y, bbox_w, bbox_h, embedding_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                asset_id,
                float(x), float(y), float(w), float(h),
                json.dumps(embedding)
            ))
            
            conn.commit()
            return True
            
        except Exception as e:
            print(f"❌ DB Error for asset {asset_id}: {e}")
            return False
        finally:
            conn.close()
    
    def get_face_embedding(self, face_crop):
        """Get embedding for a cropped face image"""
        try:
            # Encode face crop as base64
            _, buffer = cv2.imencode('.jpg', face_crop)
            face_b64 = base64.b64encode(buffer).decode('utf-8')
            
            # Call embedding service
            response = requests.post(
                f"{self.service_url}/embed",
                json={'image': face_b64},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('embedding', [])
            else:
                return None
                
        except Exception as e:
            print(f"❌ Embedding error: {e}")
            return None
    
    def process_single_image(self, asset_id, image_path):
        """Process a single image with proper face detection"""
        if self.stop_processing:
            return False
            
        try:
            # Check if file exists
            if not os.path.exists(image_path):
                with self.lock:
                    self.error_count += 1
                return False
            
            # Load image with OpenCV
            image = cv2.imread(image_path)
            if image is None:
                with self.lock:
                    self.error_count += 1
                return False
            
            # Get original image dimensions
            orig_height, orig_width = image.shape[:2]
            
            # Detect faces in original image
            faces = self.detect_faces_opencv(image)
            
            if len(faces) == 0:
                # No faces detected - still mark as processed but don't save face detection
                print(f"   📷 No faces in {os.path.basename(image_path)}")
                return True
            
            # Process each detected face
            faces_saved = 0
            for i, (x, y, w, h) in enumerate(faces):
                # Validate bounding box
                if x < 0 or y < 0 or x + w > orig_width or y + h > orig_height:
                    continue
                    
                # Crop face from original image
                face_crop = image[y:y+h, x:x+w]
                
                # Resize face crop to 112x112 for embedding
                face_resized = cv2.resize(face_crop, (112, 112))
                
                # Get embedding for this face
                embedding = self.get_face_embedding(face_resized)
                
                if embedding and len(embedding) > 0:
                    # Save with original coordinates
                    success = self.save_face_detection(asset_id, (x, y, w, h), embedding)
                    if success:
                        faces_saved += 1
                        print(f"     👤 Face {i+1}: ({x},{y}) {w}x{h} → Embedding saved")
                    
            with self.lock:
                self.processed_count += 1
                
            if faces_saved > 0:
                print(f"   ✅ {os.path.basename(image_path)}: {faces_saved} faces processed")
            
            return True
            
        except Exception as e:
            print(f"❌ Error processing {image_path}: {e}")
            with self.lock:
                self.error_count += 1
            return False
    
    def get_gpu_stats(self):
        """Get RTX 3090 GPU statistics"""
        try:
            result = subprocess.run([
                'nvidia-smi', 
                '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw',
                '--format=csv,noheader,nounits',
                '--id=0'
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                gpu_util, mem_used, mem_total, temp, power = result.stdout.strip().split(', ')
                return f"{gpu_util}% GPU | {int(mem_used)/1024:.0f}GB/{int(mem_total)/1024:.0f}GB | {temp}°C | {power}W"
        except:
            pass
        return "GPU stats unavailable"
    
    def run_processing(self, max_workers=3, batch_size=15):
        """Run the enhanced face processing pipeline"""
        print("🚀 ENHANCED FACE PROCESSING WITH PROPER DETECTION")
        print("=" * 60)
        print("🔧 Using OpenCV face detection + LVFace embeddings")
        print("📐 Coordinates saved in original image space")
        print()
        
        self.start_time = time.time()
        batch_count = 0
        
        try:
            while not self.stop_processing:
                # Get pending images
                pending_images = self.get_pending_images(batch_size)
                
                if not pending_images:
                    print("🎉 All images processed!")
                    break
                
                batch_count += 1
                print(f"📦 Batch {batch_count}: Processing {len(pending_images)} images...")
                
                # Process batch with threading
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = []
                    for asset_id, image_path in pending_images:
                        future = executor.submit(self.process_single_image, asset_id, image_path)
                        futures.append(future)
                    
                    # Process results
                    completed = 0
                    for future in as_completed(futures):
                        completed += 1
                        if completed % 5 == 0:
                            print(f"   ⚡ {completed}/{len(pending_images)} in batch...")
                
                # Show progress every few batches
                if batch_count % 5 == 0:
                    elapsed = time.time() - self.start_time
                    rate = self.processed_count / elapsed if elapsed > 0 else 0
                    gpu_stats = self.get_gpu_stats()
                    
                    print(f"🖥️  {datetime.now().strftime('%H:%M:%S')} | RTX 3090: {gpu_stats}")
                    print(f"📊 Processed: {self.processed_count:,} | Rate: {rate:.1f} img/s | Errors: {self.error_count}")
                    print()
                
                time.sleep(0.1)  # Brief pause between batches
                
        except KeyboardInterrupt:
            print("\n⏹️ Stopping gracefully...")
            self.stop_processing = True
        
        # Final stats
        elapsed = time.time() - self.start_time
        print(f"\n🏁 PROCESSING COMPLETE!")
        print(f"✅ Total processed: {self.processed_count:,}")
        print(f"❌ Errors: {self.error_count}")
        print(f"⏱️ Time: {elapsed:.1f}s ({self.processed_count/elapsed:.1f} img/s)")

def main():
    print("🚀 Starting Enhanced Face Processing with Proper Detection...")
    print("   Press Ctrl+C to stop gracefully")
    
    orchestrator = EnhancedFaceProcessingOrchestrator()
    orchestrator.run_processing(max_workers=3, batch_size=10)

if __name__ == "__main__":
    main()
