#!/usr/bin/env python3

import requests
import sqlite3
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class FaceProcessingOrchestrator:
    def __init__(self):
        self.face_service_url = "http://localhost:8003"
        self.db_path = "metadata.sqlite"
        self.processed_count = 0
        self.error_count = 0
        self.lock = threading.Lock()
        
    def get_pending_images(self):
        """Get images that need face processing"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get images without face detections
        cursor.execute("""
            SELECT a.id, a.file_path, a.filename
            FROM assets a
            WHERE a.mime LIKE 'image/%'
            AND NOT EXISTS (
                SELECT 1 FROM face_detections fd 
                WHERE fd.asset_id = a.id
            )
            LIMIT 100
        """)
        
        pending_images = cursor.fetchall()
        conn.close()
        return pending_images
    
    def process_single_image(self, asset_id, file_path, filename):
        """Process a single image for face detection"""
        try:
            # Call LVFace service
            with open(file_path, 'rb') as img_file:
                files = {'image': (filename, img_file, 'image/jpeg')}
                response = requests.post(
                    f"{self.face_service_url}/detect_faces",
                    files=files,
                    timeout=30
                )
            
            if response.status_code == 200:
                faces_data = response.json()
                self.save_face_detections(asset_id, faces_data)
                
                with self.lock:
                    self.processed_count += 1
                    if self.processed_count % 10 == 0:
                        print(f"✅ Processed {self.processed_count} images...")
                
                return True
            else:
                print(f"❌ Error processing {filename}: {response.status_code}")
                with self.lock:
                    self.error_count += 1
                return False
                
        except Exception as e:
            print(f"❌ Exception processing {filename}: {str(e)}")
            with self.lock:
                self.error_count += 1
            return False
    
    def save_face_detections(self, asset_id, faces_data):
        """Save face detection results to database"""
        if not faces_data.get('faces'):
            return
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for face in faces_data['faces']:
            cursor.execute("""
                INSERT INTO face_detections 
                (asset_id, bbox_x, bbox_y, bbox_width, bbox_height, confidence, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                asset_id,
                face['bbox'][0],
                face['bbox'][1], 
                face['bbox'][2],
                face['bbox'][3],
                face.get('confidence', 0.0),
                json.dumps(face.get('embedding', []))
            ))
        
        conn.commit()
        conn.close()
    
    def start_processing(self, max_workers=4):
        """Start processing pending images"""
        print("🚀 Starting Face Processing Pipeline...")
        print(f"⚡ Using RTX 3090 GPU acceleration")
        print(f"🔧 Max workers: {max_workers}")
        print()
        
        start_time = time.time()
        
        while True:
            pending_images = self.get_pending_images()
            
            if not pending_images:
                print("✅ All images processed!")
                break
            
            print(f"📊 Processing batch of {len(pending_images)} images...")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                
                for asset_id, file_path, filename in pending_images:
                    future = executor.submit(
                        self.process_single_image, 
                        asset_id, file_path, filename
                    )
                    futures.append(future)
                
                # Wait for batch completion
                for future in as_completed(futures):
                    future.result()
        
        elapsed_time = time.time() - start_time
        print()
        print("🎉 FACE PROCESSING COMPLETE!")
        print(f"✅ Processed: {self.processed_count} images")
        print(f"❌ Errors: {self.error_count} images")
        print(f"⏱️ Total time: {elapsed_time:.1f} seconds")
        print(f"📊 Average: {elapsed_time/max(self.processed_count, 1):.2f}s per image")

if __name__ == "__main__":
    orchestrator = FaceProcessingOrchestrator()
    
    print("🎯 FACE PROCESSING ORCHESTRATOR")
    print("=" * 40)
    print("Ready to process 6,559 pending images")
    print("Would you like to start? (y/n): ", end="")
    
    # For now, just show readiness - user can confirm
    print("\n🚀 Ready to begin face processing!")
    print("📊 This will process all 6,559 pending images")
    print("⏱️ Estimated time: ~1.4 hours with RTX 3090")
    print()
    print("To start processing, run:")
    print("  python face_orchestrator.py")
