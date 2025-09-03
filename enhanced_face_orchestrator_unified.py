#!/usr/bin/env python3
"""
Enhanced Face Processing Orchestrator using Unified SCRFD + LVFace Service
This replaces the old separate pipeline with the new unified service
"""

import json
import os
import requests
import sqlite3
import time
from datetime import datetime
import threading
from queue import Queue
import psutil
import argparse

# Disable proxy for local connections to avoid Clash interference
os.environ['NO_PROXY'] = 'localhost,127.0.0.1,172.*.*.*'
os.environ['no_proxy'] = 'localhost,127.0.0.1,172.*.*.*'

# Create session with proxy bypass for unified service
session = requests.Session()
session.proxies = {
    'http': None,
    'https': None
}
import subprocess

class UnifiedFaceOrchestrator:
    def __init__(self, max_workers=3, batch_size=0, test_mode=False):
        # Use WSL IP to bypass proxy issues
        self.service_url = "http://172.22.61.27:8003"
        
        # Create session with proxy bypass for Clash compatibility
        self.session = requests.Session()
        self.session.proxies = {'http': None, 'https': None}
        
        # Load Drive E configuration
        config_path = "config/drive_e_paths.json"
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
            self.db_path = config["databases"]["app"]
        else:
            # Fallback to local database
            self.db_path = "app.db"
            
        self.processed_count = 0
        self.failed_count = 0
        self.start_time = None
        self.max_workers = max_workers  # Number of concurrent processing threads
        self.batch_size = batch_size    # Maximum number of images to process
        self.test_mode = test_mode      # Test mode for smaller batches
        
        # Database lock for thread safety
        self.db_lock = threading.Lock()
        
        # Thread-safe queues
        self.image_queue = Queue()
        self.results_queue = Queue()
    
    def convert_path_for_wsl(self, windows_path):
        """Convert Windows path to WSL-accessible path"""
        # Normalize path separators to forward slashes
        normalized_path = windows_path.replace('\\', '/')
        
        # Convert E:/path to /mnt/e/path
        if normalized_path.startswith('E:/'):
            wsl_path = normalized_path.replace('E:/', '/mnt/e/')
            return wsl_path
        # Convert C:/path to /mnt/c/path  
        elif normalized_path.startswith('C:/'):
            wsl_path = normalized_path.replace('C:/', '/mnt/c/')
            return wsl_path
        # For other drives, follow same pattern
        elif ':' in normalized_path:
            drive_letter = normalized_path[0].lower()
            path_part = normalized_path[2:]
            return f'/mnt/{drive_letter}{path_part}'
        return windows_path
    
    def save_face_detection_results(self, asset_id, image_path, scrfd_result):
        """Save SCRFD detection results to database using existing schema"""
        with self.db_lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Clear any existing detections for this image
                cursor.execute("DELETE FROM face_detections WHERE asset_id = ?", (asset_id,))
                
                # Only save if faces were detected
                if scrfd_result.get('faces', 0) > 0:
                    detections = scrfd_result.get('detections', [])
                    
                    # Create embeddings directory if needed
                    os.makedirs("embeddings", exist_ok=True)
                    
                    # Handle multiple faces per image
                    for i, detection in enumerate(detections):
                        # Based on visual verification, SCRFD is returning [x, y, w, h] format
                        # Example: [252, 347, 121, 140] means x=252, y=347, w=121, h=140
                        bbox = detection.get('bbox', [0, 0, 0, 0])
                        
                        # SCRFD returns [x, y, w, h] format directly
                        x, y, w, h = bbox[0], bbox[1], bbox[2], bbox[3]
                        
                        # Ensure positive width and height
                        if w <= 0 or h <= 0:
                            print(f"⚠️ Invalid bbox for {os.path.basename(image_path)}: {bbox} -> x={x}, y={y}, w={w}, h={h}")
                            continue
                        
                        # Handle embedding if available
                        embedding = detection.get('embedding')
                        embedding_path = None
                        
                        if embedding and len(embedding) > 0:
                            # Create embedding file
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            embedding_filename = f"face_{timestamp}_{asset_id}_{i}.json"
                            embedding_path = os.path.join("embeddings", embedding_filename)
                            
                            # Save embedding to file
                            try:
                                with open(embedding_path, 'w') as f:
                                    json.dump(embedding, f)
                            except Exception as e:
                                print(f"⚠️ Could not save embedding: {e}")
                                embedding_path = None
                        
                        # Insert into database with existing schema
                        # Schema: id, asset_id, bbox_x, bbox_y, bbox_w, bbox_h, person_id, embedding_path
                        cursor.execute("""
                            INSERT INTO face_detections 
                            (asset_id, bbox_x, bbox_y, bbox_w, bbox_h, person_id, embedding_path)
                            VALUES (?, ?, ?, ?, ?, NULL, ?)
                        """, (asset_id, x, y, w, h, embedding_path))
                
                conn.commit()
                conn.close()
                return True
                
            except Exception as e:
                print(f"❌ Database error for {image_path}: {e}")
                if 'conn' in locals():
                    conn.close()
                return False
        
        # Threading
        self.max_workers = 4
        self.image_queue = Queue()
        self.results_queue = Queue()
        
    def check_service_health(self):
        """Check if the unified service is running"""
        try:
            response = session.get(f"{self.service_url}/status", timeout=5)
            if response.status_code == 200:
                status = response.json()
                print("🔍 Service Status:")
                print(f"   Status: {status.get('status', 'unknown')}")
                print(f"   Face Detector: {status.get('face_detector', 'unknown')}")
                print(f"   InsightFace Available: {status.get('insightface_available', False)}")
                print(f"   Providers: {', '.join(status.get('providers', []))}")
                return True
            else:
                print(f"❌ Service health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Could not connect to unified service: {e}")
            return False
    
    def get_unprocessed_images(self):
        """Get images that need SCRFD processing (skip already processed)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get images that haven't been processed yet
            # Skip images that already have face detections
            limit_clause = f"LIMIT {self.batch_size}" if self.batch_size > 0 else ""
            
            cursor.execute(f"""
                SELECT a.id, a.path 
                FROM assets a 
                LEFT JOIN face_detections f ON a.id = f.asset_id
                WHERE a.mime LIKE 'image/%' 
                  AND a.id > 5 
                  AND f.asset_id IS NULL
                ORDER BY a.id
                {limit_clause}
            """)
            
            images = cursor.fetchall()
            
            # Also get count of already processed images
            cursor.execute("""
                SELECT COUNT(DISTINCT a.id) 
                FROM assets a 
                INNER JOIN face_detections f ON a.id = f.asset_id
                WHERE a.mime LIKE 'image/%' AND a.id > 5
            """)
            already_processed = cursor.fetchone()[0]
            
            conn.close()
            
            if self.test_mode:
                print(f"🧪 Test mode: Found {len(images)} unprocessed images (skipping first 5 placeholder images)")
                print(f"   Already processed: {already_processed} images")
            else:
                print(f"📊 Found {len(images)} unprocessed images (skipping first 5 placeholder images)")
                print(f"   Already processed: {already_processed} images")
            return images
            
        except Exception as e:
            print(f"❌ Database query error: {e}")
            return []
    
    def process_single_image(self, asset_id, image_path):
        """Process a single image using the unified service"""
        try:
            # Convert Windows path to WSL path for the service
            wsl_path = self.convert_path_for_wsl(image_path)
            
            # Call unified service
            response = session.post(
                f"{self.service_url}/process_image",
                json={"image_path": wsl_path},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Log results
                faces_found = result.get('faces', 0)
                detector = result.get('detector', 'unknown')
                
                # Save results to database
                db_saved = self.save_face_detection_results(asset_id, image_path, result)
                
                if faces_found > 0:
                    print(f"✅ {os.path.basename(image_path)}: {faces_found} faces ({detector}) {'📊' if db_saved else '⚠️'}")
                    return {
                        'success': True,
                        'faces': faces_found,
                        'detector': detector,
                        'path': image_path,
                        'db_saved': db_saved
                    }
                else:
                    print(f"🔍 {os.path.basename(image_path)}: No faces detected {'📊' if db_saved else '⚠️'}")
                    return {
                        'success': True,
                        'faces': 0,
                        'detector': detector,
                        'path': image_path,
                        'db_saved': db_saved
                    }
            else:
                print(f"❌ {os.path.basename(image_path)}: HTTP {response.status_code}")
                return {'success': False, 'error': f"HTTP {response.status_code}", 'path': image_path}
                
        except Exception as e:
            print(f"❌ {os.path.basename(image_path)}: {str(e)}")
            return {'success': False, 'error': str(e), 'path': image_path}
    
    def worker_thread(self):
        """Worker thread for processing images"""
        while True:
            try:
                item = self.image_queue.get(timeout=1)
                if item is None:  # Poison pill
                    break
                    
                asset_id, image_path = item
                result = self.process_single_image(asset_id, image_path)
                self.results_queue.put(result)
                self.image_queue.task_done()
                
            except Exception as e:
                print(f"⚠️ Worker error: {e}")
                break
    
    def monitor_progress(self):
        """Monitor processing progress and performance"""
        faces_detected = 0
        db_saves = 0
        
        while True:
            try:
                result = self.results_queue.get(timeout=5)
                
                if result['success']:
                    self.processed_count += 1
                    faces_detected += result.get('faces', 0)
                    if result.get('db_saved', False):
                        db_saves += 1
                else:
                    self.failed_count += 1
                
                # Calculate performance metrics
                elapsed = time.time() - self.start_time
                total_processed = self.processed_count + self.failed_count
                rate = total_processed / elapsed if elapsed > 0 else 0
                
                # Print progress every 10 images
                if total_processed % 10 == 0:
                    print(f"\n📈 Progress: {total_processed} images processed")
                    print(f"   ✅ Success: {self.processed_count}")
                    print(f"   👤 Faces found: {faces_detected}")
                    print(f"   📊 DB saves: {db_saves}")
                    print(f"   ❌ Failed: {self.failed_count}")
                    print(f"   ⚡ Rate: {rate:.2f} images/second")
                    print(f"   🕒 Elapsed: {elapsed:.1f}s")
                    
                    # GPU monitoring
                    try:
                        gpu_usage = subprocess.check_output([
                            "nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", 
                            "--format=csv,noheader,nounits"
                        ], text=True).strip()
                        print(f"   🎮 GPU: {gpu_usage}")
                    except:
                        pass
                
                self.results_queue.task_done()
                
            except Exception as e:
                # Timeout or other error, continue monitoring
                break
    
    def run_batch_processing(self):
        """Run batch face processing using unified service"""
        print("🚀 Starting Enhanced Face Processing with Unified Service")
        
        # Check service health
        if not self.check_service_health():
            print("❌ Unified service not available. Please start it first.")
            return False
        
        # Get unprocessed images
        images = self.get_unprocessed_images()
        if not images:
            print("✅ No unprocessed images found!")
            return True
        
        print(f"🎯 Processing {len(images)} images using unified service...")
        
        # Start timing
        self.start_time = time.time()
        
        # Start worker threads
        threads = []
        for i in range(self.max_workers):
            t = threading.Thread(target=self.worker_thread)
            t.start()
            threads.append(t)
        
        # Start progress monitor
        monitor_thread = threading.Thread(target=self.monitor_progress)
        monitor_thread.start()
        
        # Queue all images
        for asset_id, image_path in images:
            self.image_queue.put((asset_id, image_path))
        
        # Wait for processing to complete
        self.image_queue.join()
        
        # Stop worker threads
        for _ in range(self.max_workers):
            self.image_queue.put(None)
        for t in threads:
            t.join()
        
        # Final statistics
        elapsed = time.time() - self.start_time
        total_processed = self.processed_count + self.failed_count
        rate = total_processed / elapsed if elapsed > 0 else 0
        
        print(f"\n🎉 Batch Processing Complete!")
        print(f"   📊 Total images: {len(images)}")
        print(f"   ✅ Successfully processed: {self.processed_count}")
        print(f"   ❌ Failed: {self.failed_count}")
        print(f"   ⚡ Average rate: {rate:.2f} images/second")
        print(f"   🕒 Total time: {elapsed:.1f} seconds")
        
        return True

def main():
    parser = argparse.ArgumentParser(description='Enhanced Face Processing with Unified SCRFD+LVFace Service')
    parser.add_argument('--batch-size', type=int, default=0, 
                       help='Maximum number of images to process (0 = unlimited, default: 0)')
    parser.add_argument('--max-workers', type=int, default=3,
                       help='Number of concurrent processing threads (default: 3)')
    parser.add_argument('--test-mode', action='store_true',
                       help='Enable test mode for debugging')
    parser.add_argument('--incremental', action='store_true',
                       help='Process only unprocessed images (default behavior)')
    
    args = parser.parse_args()
    
    # In test mode, use smaller batch size if not specified
    if args.test_mode and args.batch_size == 0:
        args.batch_size = 10
    
    orchestrator = UnifiedFaceOrchestrator(
        max_workers=args.max_workers,
        batch_size=args.batch_size,
        test_mode=args.test_mode
    )
    orchestrator.run_batch_processing()

if __name__ == "__main__":
    main()
