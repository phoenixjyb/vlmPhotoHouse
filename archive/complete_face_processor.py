#!/usr/bin/env python3
"""
Complete Face Processing Pipeline
- Process all images in database from scratch
- Save detected faces as compressed thumbnails
- Create organized face collection with links to originals
"""

import json
import os
import requests
import sqlite3
import time
from datetime import datetime
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import shutil
from pathlib import Path

class CompleteFaceProcessor:
    def __init__(self, fresh_start=False):
        # Service configuration with proxy bypass
        self.service_url = "http://172.22.61.27:8003"
        self.session = requests.Session()
        self.session.proxies = {'http': None, 'https': None}
        
        # Database
        self.db_path = "metadata.sqlite"
        
        # Processing mode
        self.fresh_start = fresh_start
        
        # Output directories
        self.output_base = "E:/02_PROCESSED"
        self.faces_dir = os.path.join(self.output_base, "detected_faces")
        self.thumbnails_dir = os.path.join(self.faces_dir, "thumbnails")
        self.metadata_dir = os.path.join(self.faces_dir, "metadata")
        
        # Face processing settings
        self.face_size = (128, 128)  # Highly compressed face thumbnails
        self.jpeg_quality = 70  # Good quality but compressed
        
        # Statistics
        self.stats = {
            'total_images': 0,
            'processed_images': 0,
            'images_with_faces': 0,
            'total_faces': 0,
            'failed_images': 0,
            'start_time': None,
            'existing_faces': 0
        }
        
        self.setup_directories()
        
    def setup_directories(self):
        """Create output directory structure"""
        directories = [
            self.output_base,
            self.faces_dir,
            self.thumbnails_dir,
            self.metadata_dir
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            
        print(f"📁 Created directory structure:")
        print(f"   Base: {self.output_base}")
        print(f"   Faces: {self.faces_dir}")
        print(f"   Thumbnails: {self.thumbnails_dir}")
        print(f"   Metadata: {self.metadata_dir}")
    
    def clear_previous_results(self):
        """Clear face_detections table to start fresh (only if fresh_start=True)"""
        if not self.fresh_start:
            print("🔄 Incremental mode: Keeping existing face detection results")
            return
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Clear previous face detection results
            cursor.execute("DELETE FROM face_detections")
            
            # Reset processed flag if it exists
            try:
                cursor.execute("UPDATE assets SET processed = 0")
            except sqlite3.OperationalError:
                # Column doesn't exist, ignore
                pass
            
            conn.commit()
            conn.close()
            
            print("🧹 Cleared previous face detection results (fresh start)")
            
            # Also clear face collection directories
            if os.path.exists(self.thumbnails_dir):
                shutil.rmtree(self.thumbnails_dir)
            if os.path.exists(self.metadata_dir):
                shutil.rmtree(self.metadata_dir)
            
            self.setup_directories()
            print("🧹 Cleared previous face collection")
            
        except Exception as e:
            print(f"❌ Error clearing results: {e}")
    
    def get_images_to_process(self):
        """Get images that need face collection processing"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if self.fresh_start:
                # Fresh start: get all images
                cursor.execute("""
                    SELECT a.id, a.path, a.filename 
                    FROM assets a
                    WHERE a.path LIKE '%.jpg' OR a.path LIKE '%.jpeg' OR a.path LIKE '%.png'
                    ORDER BY a.id
                """)
                print("🔄 Fresh start mode: Processing all images")
            else:
                # Incremental: only process images that have face detections but no collection files
                cursor.execute("""
                    SELECT DISTINCT a.id, a.path, a.filename 
                    FROM assets a
                    INNER JOIN face_detections fd ON a.id = fd.asset_id
                    WHERE (a.path LIKE '%.jpg' OR a.path LIKE '%.jpeg' OR a.path LIKE '%.png')
                    ORDER BY a.id
                """)
                print("🔄 Incremental mode: Processing only images with detected faces")
            
            images = cursor.fetchall()
            
            # Count existing faces in database
            cursor.execute("SELECT COUNT(*) FROM face_detections")
            existing_face_count = cursor.fetchone()[0]
            self.stats['existing_faces'] = existing_face_count
            
            conn.close()
            
            self.stats['total_images'] = len(images)
            print(f"📊 Found {len(images)} images to process")
            print(f"📊 Existing faces in database: {existing_face_count}")
            
            return images
            
        except Exception as e:
            print(f"❌ Database error: {e}")
            return []
    
    def check_service_health(self):
        """Verify SCRFD service is running"""
        try:
            response = self.session.get(f"{self.service_url}/status", timeout=5)
            if response.status_code == 200:
                status = response.json()
                print(f"✅ SCRFD Service Status:")
                print(f"   Detector: {status.get('face_detector')}")
                print(f"   GPU: {status.get('providers')}")
                return True
            else:
                print(f"❌ Service unhealthy: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Service connection error: {e}")
            return False
    
    def create_face_collection_from_database(self):
        """Create face collection from existing database results (no new detection)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get all face detections from database
            cursor.execute("""
                SELECT fd.asset_id, a.path, a.filename, fd.bbox_x, fd.bbox_y, 
                       fd.bbox_w, fd.bbox_h, fd.confidence, fd.id
                FROM face_detections fd
                INNER JOIN assets a ON fd.asset_id = a.id
                ORDER BY fd.asset_id, fd.id
            """)
            
            face_records = cursor.fetchall()
            conn.close()
            
            if not face_records:
                print("❌ No face detection records found in database")
                return
            
            print(f"📊 Found {len(face_records)} face records in database")
            print("🖼️ Creating face collection from database...")
            
            for record in face_records:
                asset_id, image_path, filename, bbox_x, bbox_y, bbox_w, bbox_h, confidence, detection_id = record
                
                # Create face crop from database coordinates
                success = self.create_face_crop_from_coords(
                    asset_id, image_path, filename, 
                    [bbox_x, bbox_y, bbox_w, bbox_h], 
                    confidence, detection_id
                )
                
                if success:
                    self.stats['total_faces'] += 1
                    if asset_id not in getattr(self, '_processed_images', set()):
                        self.stats['images_with_faces'] += 1
                        getattr(self, '_processed_images', set()).add(asset_id)
            
            print(f"✅ Created {self.stats['total_faces']} face thumbnails")
            
        except Exception as e:
            print(f"❌ Error creating collection from database: {e}")
    
    def create_face_crop_from_coords(self, asset_id, image_path, filename, bbox, confidence, detection_id):
        """Create face crop from database coordinates"""
        try:
            if not os.path.exists(image_path):
                print(f"❌ Original image not found: {image_path}")
                return False
            
            original_image = cv2.imread(image_path)
            if original_image is None:
                print(f"❌ Could not load image: {image_path}")
                return False
            
            x, y, w, h = bbox
            
            # Extract face crop
            face_crop = original_image[y:y+h, x:x+w]
            
            if face_crop.size == 0:
                return False
            
            # Create face ID using detection_id for consistency
            face_id = f"{asset_id}_{detection_id}_{int(confidence*1000)}"
            
            # Check if face already exists
            face_filename = f"face_{face_id}.jpg"
            face_path = os.path.join(self.thumbnails_dir, face_filename)
            
            if os.path.exists(face_path):
                return True  # Already exists, skip
            
            # Save compressed face thumbnail
            face_resized = cv2.resize(face_crop, self.face_size)
            cv2.imwrite(face_path, face_resized, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            
            # Create metadata
            metadata = {
                'face_id': face_id,
                'detection_id': detection_id,
                'original_image': image_path,
                'original_filename': filename,
                'bbox': bbox,
                'confidence': confidence,
                'face_thumbnail': face_path,
                'created_at': datetime.now().isoformat(),
                'source': 'database'
            }
            
            # Save metadata JSON
            metadata_filename = f"face_{face_id}.json"
            metadata_path = os.path.join(self.metadata_dir, metadata_filename)
            
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"❌ Error creating face crop for {filename}: {e}")
            return False
        """Process a single image for face detection"""
        try:
            # Convert Windows path to WSL path for service
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
                faces_count = result.get('faces', 0)
                
                if faces_count > 0:
                    self.stats['images_with_faces'] += 1
                    self.stats['total_faces'] += faces_count
                    
                    # Save face crops and metadata
                    self.save_detected_faces(image_id, image_path, filename, result)
                
                self.stats['processed_images'] += 1
                return True, faces_count
                
            else:
                print(f"❌ Service error for {filename}: {response.status_code}")
                self.stats['failed_images'] += 1
                return False, 0
                
        except Exception as e:
            print(f"❌ Processing error for {filename}: {e}")
            self.stats['failed_images'] += 1
            return False, 0
    
    def save_detected_faces(self, image_id, image_path, filename, detection_result):
        """Save detected face crops and metadata"""
        try:
            # Load original image
            if not os.path.exists(image_path):
                print(f"❌ Original image not found: {image_path}")
                return
            
            original_image = cv2.imread(image_path)
            if original_image is None:
                print(f"❌ Could not load image: {image_path}")
                return
            
            detections = detection_result.get('detections', [])
            
            for face_idx, detection in enumerate(detections):
                bbox = detection.get('bbox', [])
                confidence = detection.get('confidence', 0)
                
                if len(bbox) != 4:
                    continue
                
                x, y, w, h = bbox
                
                # Extract face crop
                face_crop = original_image[y:y+h, x:x+w]
                
                if face_crop.size == 0:
                    continue
                
                # Create face ID
                face_id = f"{image_id}_{face_idx}_{int(confidence*1000)}"
                
                # Save compressed face thumbnail
                face_filename = f"face_{face_id}.jpg"
                face_path = os.path.join(self.thumbnails_dir, face_filename)
                
                # Resize and compress face
                face_resized = cv2.resize(face_crop, self.face_size)
                cv2.imwrite(face_path, face_resized, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                
                # Create metadata
                metadata = {
                    'face_id': face_id,
                    'original_image': image_path,
                    'original_filename': filename,
                    'bbox': bbox,
                    'confidence': confidence,
                    'face_thumbnail': face_path,
                    'detected_at': datetime.now().isoformat(),
                    'embedding_size': detection.get('embedding_size', 0)
                }
                
                # Save metadata JSON
                metadata_filename = f"face_{face_id}.json"
                metadata_path = os.path.join(self.metadata_dir, metadata_filename)
                
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
                
                print(f"💾 Saved face {face_id}: {confidence:.3f} confidence")
            
        except Exception as e:
            print(f"❌ Error saving faces for {filename}: {e}")
    
    def create_face_gallery(self):
        """Create an HTML gallery of all detected faces"""
        try:
            gallery_path = os.path.join(self.faces_dir, "face_gallery.html")
            
            # Get all face metadata files
            metadata_files = [f for f in os.listdir(self.metadata_dir) if f.endswith('.json')]
            metadata_files.sort()
            
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Detected Faces Gallery</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .stats {{ background: #f0f0f0; padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
        .face-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; }}
        .face-card {{ border: 1px solid #ddd; border-radius: 5px; padding: 10px; background: white; }}
        .face-image {{ width: 128px; height: 128px; object-fit: cover; }}
        .face-info {{ font-size: 12px; margin-top: 5px; }}
        .confidence {{ font-weight: bold; color: #007acc; }}
        .original-link {{ color: #007acc; text-decoration: none; }}
        .original-link:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <h1>🧑‍🤝‍🧑 Detected Faces Gallery</h1>
    
    <div class="stats">
        <h3>📊 Processing Statistics</h3>
        <p><strong>Total Images Processed:</strong> {self.stats['processed_images']:,}</p>
        <p><strong>Images with Faces:</strong> {self.stats['images_with_faces']:,}</p>
        <p><strong>Total Faces Detected:</strong> {self.stats['total_faces']:,}</p>
        <p><strong>Detection Rate:</strong> {(self.stats['images_with_faces']/max(self.stats['processed_images'],1)*100):.1f}%</p>
        <p><strong>Average Faces per Image:</strong> {(self.stats['total_faces']/max(self.stats['images_with_faces'],1)):.1f}</p>
    </div>
    
    <div class="face-grid">
"""
            
            # Add each face to the gallery
            for metadata_file in metadata_files:
                metadata_path = os.path.join(self.metadata_dir, metadata_file)
                
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                    
                    face_id = metadata.get('face_id', 'unknown')
                    confidence = metadata.get('confidence', 0)
                    original_filename = metadata.get('original_filename', 'unknown')
                    original_path = metadata.get('original_image', '')
                    thumbnail_path = metadata.get('face_thumbnail', '')
                    
                    # Make thumbnail path relative to HTML file
                    relative_thumbnail = os.path.relpath(thumbnail_path, self.faces_dir)
                    
                    html_content += f"""
        <div class="face-card">
            <img src="{relative_thumbnail}" alt="Face {face_id}" class="face-image">
            <div class="face-info">
                <div class="confidence">Confidence: {confidence:.3f}</div>
                <div><strong>Face ID:</strong> {face_id}</div>
                <div><strong>From:</strong> <a href="file:///{original_path}" class="original-link" title="{original_path}">{original_filename}</a></div>
            </div>
        </div>
"""
                except Exception as e:
                    print(f"❌ Error processing metadata {metadata_file}: {e}")
            
            html_content += """
    </div>
</body>
</html>
"""
            
            with open(gallery_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print(f"🎨 Created face gallery: {gallery_path}")
            
        except Exception as e:
            print(f"❌ Error creating gallery: {e}")
    
    def print_statistics(self):
        """Print final processing statistics"""
        elapsed = time.time() - self.stats['start_time']
        
        print("\n" + "="*60)
        print("🎉 FACE PROCESSING COMPLETE!")
        print("="*60)
        print(f"📊 Total Images: {self.stats['total_images']:,}")
        print(f"✅ Processed: {self.stats['processed_images']:,}")
        print(f"❌ Failed: {self.stats['failed_images']:,}")
        print(f"👥 Images with Faces: {self.stats['images_with_faces']:,}")
        print(f"🧑 Total Faces Detected: {self.stats['total_faces']:,}")
        print(f"📈 Detection Rate: {(self.stats['images_with_faces']/max(self.stats['processed_images'],1)*100):.1f}%")
        print(f"⚡ Processing Speed: {(self.stats['processed_images']/elapsed):.1f} images/second")
        print(f"🕒 Total Time: {elapsed:.1f} seconds")
        print(f"💾 Face Thumbnails: {self.thumbnails_dir}")
        print(f"📄 Metadata: {self.metadata_dir}")
        print("="*60)
    
    def run_complete_processing(self):
        """Run the complete face processing pipeline"""
        mode_text = "Fresh Start" if self.fresh_start else "Incremental"
        print(f"🚀 Starting Complete Face Processing Pipeline ({mode_text})")
        print("="*60)
        
        # Clear previous results only if fresh start
        self.clear_previous_results()
        
        if self.fresh_start:
            # Fresh start: Check service and process all images
            if not self.check_service_health():
                print("❌ SCRFD service not available. Please start the service first.")
                return
            
            # Get all images for fresh processing
            images = self.get_images_to_process()
            if not images:
                print("❌ No images found in database")
                return
            
            # Start processing
            self.stats['start_time'] = time.time()
            print(f"\n🔍 Processing {len(images)} images with SCRFD...")
            
            for i, (image_id, image_path, filename) in enumerate(images):
                success, faces_count = self.process_single_image(image_id, image_path, filename)
                
                if faces_count > 0:
                    print(f"✅ {filename}: {faces_count} faces detected")
                elif i % 100 == 0:  # Show progress every 100 images
                    elapsed = time.time() - self.stats['start_time']
                    rate = self.stats['processed_images'] / elapsed if elapsed > 0 else 0
                    print(f"📈 Progress: {self.stats['processed_images']}/{len(images)} ({rate:.1f} img/s) - Faces found: {self.stats['total_faces']}")
        
        else:
            # Incremental: Create collection from existing database results
            print("\n🔄 Creating face collection from existing database results...")
            self.stats['start_time'] = time.time()
            self._processed_images = set()  # Track unique images
            self.create_face_collection_from_database()
        
        # Create gallery
        if self.stats['total_faces'] > 0:
            self.create_face_gallery()
        else:
            print("ℹ️ No faces found to create gallery")
        
        # Print final statistics
        self.print_statistics()

if __name__ == "__main__":
    import sys
    
    # Check command line arguments
    fresh_start = "--fresh" in sys.argv or "--fresh-start" in sys.argv
    
    if fresh_start:
        print("🆕 FRESH START MODE: Will clear all previous results and reprocess everything")
        confirm = input("⚠️ This will delete existing face collection. Continue? (y/N): ")
        if confirm.lower() != 'y':
            print("❌ Cancelled")
            exit()
    else:
        print("🔄 INCREMENTAL MODE: Will create face collection from existing database results")
        print("💡 Use --fresh flag for fresh start mode")
    
    processor = CompleteFaceProcessor(fresh_start=fresh_start)
    processor.run_complete_processing()
