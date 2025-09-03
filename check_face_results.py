#!/usr/bin/env python3
"""
Face Detection Results Checker & Visual Preview
Check existing face detection results and create sample previews
"""

import sqlite3
import os
import cv2
import json
from datetime import datetime
import random

class FaceResultsChecker:
    def __init__(self):
        self.db_path = "metadata.sqlite"
        self.preview_dir = "face_preview"
        
    def check_database_status(self):
        """Check current face detection status in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            print("📊 DATABASE STATUS CHECK")
            print("=" * 50)
            
            # Total assets
            cursor.execute("SELECT COUNT(*) FROM assets")
            total_assets = cursor.fetchone()[0]
            print(f"📁 Total images in database: {total_assets:,}")
            
            # Face detections
            cursor.execute("SELECT COUNT(*) FROM face_detections")
            total_faces = cursor.fetchone()[0]
            print(f"👥 Total face detections: {total_faces:,}")
            
            # Images with faces
            cursor.execute("SELECT COUNT(DISTINCT asset_id) FROM face_detections")
            images_with_faces = cursor.fetchone()[0]
            print(f"🖼️ Images with faces detected: {images_with_faces:,}")
            
            # Detection rate
            if total_assets > 0:
                detection_rate = (images_with_faces / total_assets) * 100
                print(f"📈 Face detection rate: {detection_rate:.1f}%")
                
                if images_with_faces > 0:
                    avg_faces = total_faces / images_with_faces
                    print(f"👤 Average faces per image: {avg_faces:.1f}")
            
            # Confidence distribution
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN confidence >= 0.9 THEN 'High (0.9+)'
                        WHEN confidence >= 0.7 THEN 'Medium (0.7-0.9)'
                        WHEN confidence >= 0.5 THEN 'Low (0.5-0.7)'
                        ELSE 'Very Low (<0.5)'
                    END as confidence_range,
                    COUNT(*) as count
                FROM face_detections 
                GROUP BY confidence_range
                ORDER BY MIN(confidence) DESC
            """)
            
            confidence_stats = cursor.fetchall()
            if confidence_stats:
                print(f"\n🎯 CONFIDENCE DISTRIBUTION:")
                for range_name, count in confidence_stats:
                    percentage = (count / total_faces) * 100 if total_faces > 0 else 0
                    print(f"   {range_name}: {count:,} faces ({percentage:.1f}%)")
            
            # Recent detections
            cursor.execute("""
                SELECT fd.created_at, COUNT(*) as faces_count
                FROM face_detections fd
                GROUP BY DATE(fd.created_at)
                ORDER BY fd.created_at DESC
                LIMIT 5
            """)
            
            recent_stats = cursor.fetchall()
            if recent_stats:
                print(f"\n📅 RECENT DETECTION ACTIVITY:")
                for date, count in recent_stats:
                    print(f"   {date}: {count:,} faces detected")
            
            conn.close()
            return total_faces > 0
            
        except Exception as e:
            print(f"❌ Database check error: {e}")
            return False
    
    def get_sample_detections(self, sample_size=10):
        """Get sample face detections for visual verification"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get sample detections with various confidence levels
            cursor.execute("""
                SELECT 
                    fd.id, fd.asset_id, a.path, a.filename,
                    fd.bbox_x, fd.bbox_y, fd.bbox_w, fd.bbox_h,
                    fd.confidence, fd.detection_model
                FROM face_detections fd
                INNER JOIN assets a ON fd.asset_id = a.id
                ORDER BY RANDOM()
                LIMIT ?
            """, (sample_size,))
            
            samples = cursor.fetchall()
            conn.close()
            
            return samples
            
        except Exception as e:
            print(f"❌ Sample query error: {e}")
            return []
    
    def create_visual_preview(self, samples, max_previews=5):
        """Create visual previews of detected faces"""
        try:
            os.makedirs(self.preview_dir, exist_ok=True)
            print(f"\n🎨 CREATING VISUAL PREVIEWS")
            print("=" * 50)
            
            created_previews = 0
            
            for sample in samples[:max_previews]:
                detection_id, asset_id, image_path, filename, bbox_x, bbox_y, bbox_w, bbox_h, confidence, model = sample
                
                if not os.path.exists(image_path):
                    print(f"❌ Image not found: {filename}")
                    continue
                
                # Load image
                image = cv2.imread(image_path)
                if image is None:
                    print(f"❌ Could not load: {filename}")
                    continue
                
                # Draw bounding box
                x, y, w, h = int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h)
                
                # Draw green rectangle for face
                cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 3)
                
                # Add confidence text
                label = f"Confidence: {confidence:.3f}"
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 1.0
                thickness = 2
                
                # Get text size for background
                (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
                
                # Draw background rectangle
                cv2.rectangle(image, (x, y - text_height - 10), (x + text_width, y), (0, 255, 0), -1)
                
                # Draw text
                cv2.putText(image, label, (x, y - 5), font, font_scale, (0, 0, 0), thickness)
                
                # Save preview
                preview_filename = f"preview_{detection_id}_{confidence:.3f}_{filename}"
                preview_path = os.path.join(self.preview_dir, preview_filename)
                
                # Resize if image is too large (for easier viewing)
                height, width = image.shape[:2]
                if width > 1200:
                    scale = 1200 / width
                    new_width = 1200
                    new_height = int(height * scale)
                    image = cv2.resize(image, (new_width, new_height))
                
                cv2.imwrite(preview_path, image)
                
                print(f"✅ Created preview: {preview_filename}")
                print(f"   Original: {filename}")
                print(f"   Face bbox: [{x}, {y}, {w}, {h}]")
                print(f"   Confidence: {confidence:.3f}")
                print(f"   Model: {model}")
                print()
                
                created_previews += 1
            
            if created_previews > 0:
                print(f"🎨 Created {created_previews} visual previews in: {self.preview_dir}")
                print(f"💡 Open the preview folder to visually verify face detection accuracy")
                return True
            else:
                print(f"❌ No previews created")
                return False
                
        except Exception as e:
            print(f"❌ Preview creation error: {e}")
            return False
    
    def check_existing_face_collection(self):
        """Check if face collection already exists"""
        face_collection_dir = "E:/02_PROCESSED/detected_faces"
        
        if os.path.exists(face_collection_dir):
            print(f"\n📁 EXISTING FACE COLLECTION CHECK")
            print("=" * 50)
            
            thumbnails_dir = os.path.join(face_collection_dir, "thumbnails")
            metadata_dir = os.path.join(face_collection_dir, "metadata")
            gallery_file = os.path.join(face_collection_dir, "face_gallery.html")
            
            if os.path.exists(thumbnails_dir):
                thumbnail_count = len([f for f in os.listdir(thumbnails_dir) if f.endswith('.jpg')])
                print(f"🖼️ Existing face thumbnails: {thumbnail_count}")
            else:
                print(f"🖼️ No face thumbnails found")
            
            if os.path.exists(metadata_dir):
                metadata_count = len([f for f in os.listdir(metadata_dir) if f.endswith('.json')])
                print(f"📄 Existing metadata files: {metadata_count}")
            else:
                print(f"📄 No metadata files found")
            
            if os.path.exists(gallery_file):
                file_size = os.path.getsize(gallery_file) / 1024  # KB
                print(f"🌐 Face gallery exists: {file_size:.1f} KB")
            else:
                print(f"🌐 No face gallery found")
                
            return thumbnail_count > 0 if 'thumbnail_count' in locals() else False
        else:
            print(f"\n📁 No existing face collection found")
            return False
    
    def run_comprehensive_check(self):
        """Run complete status check"""
        print("🔍 FACE DETECTION RESULTS COMPREHENSIVE CHECK")
        print("=" * 60)
        print(f"🕒 Check time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Check database status
        has_detections = self.check_database_status()
        
        # Check existing collection
        has_collection = self.check_existing_face_collection()
        
        if has_detections:
            # Get samples and create previews
            samples = self.get_sample_detections(10)
            if samples:
                self.create_visual_preview(samples, 5)
            
            print("\n" + "=" * 60)
            print("📋 SUMMARY & RECOMMENDATIONS")
            print("=" * 60)
            
            if has_collection:
                print("✅ Face collection already exists")
                print("💡 Recommended action: Review existing gallery or run incremental update")
                print("   Command: python complete_face_processor.py")
            else:
                print("🔄 Face detections exist but no collection created")
                print("💡 Recommended action: Create face collection from database")
                print("   Command: python complete_face_processor.py")
            
            print(f"\n🎨 Visual previews created in: {self.preview_dir}")
            print("👀 Please review the preview images to verify detection accuracy")
            
        else:
            print("\n❌ No face detections found in database")
            print("💡 Recommended action: Run face detection first")
            print("   Command: python enhanced_face_orchestrator_unified.py")
        
        print("\n" + "=" * 60)
        return has_detections, has_collection

if __name__ == "__main__":
    checker = FaceResultsChecker()
    has_detections, has_collection = checker.run_comprehensive_check()
