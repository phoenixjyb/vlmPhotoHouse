#!/usr/bin/env python3
"""
Face Detection Results Visualizer

This script loads processed images from the database and visualizes detected faces
with bounding boxes, confidence scores, and face IDs overlaid on the original images.
"""

import sqlite3
import cv2
import numpy as np
import os
import json
from pathlib import Path
import argparse
import random

class FaceDetectionVisualizer:
    def __init__(self, db_path="metadata.sqlite", output_dir="face_detection_results"):
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
    def get_processed_images_with_faces(self, limit=20):
        """Get images that have been processed and have face detections"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT 
                a.id as asset_id,
                a.path as image_path,
                COUNT(fd.id) as face_count
            FROM assets a
            INNER JOIN face_detections fd ON a.id = fd.asset_id
            WHERE a.mime LIKE 'image/%'
            AND a.path IS NOT NULL
            AND fd.bbox_x IS NOT NULL
            GROUP BY a.id, a.path
            HAVING face_count > 0
            ORDER BY face_count DESC, a.id DESC
            LIMIT ?
        """, (limit,))
        
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_face_detections_for_image(self, asset_id):
        """Get all face detections for a specific image"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                id,
                bbox_x,
                bbox_y,
                bbox_w,
                bbox_h,
                person_id,
                embedding_path,
                created_at
            FROM face_detections
            WHERE asset_id = ?
            ORDER BY id DESC
        """, (asset_id,))
        
        results = cursor.fetchall()
        conn.close()
        return results
    
    def visualize_image_with_faces(self, image_path, asset_id, face_count):
        """Create visualization of an image with detected faces"""
        filename = os.path.basename(image_path)
        print(f"📸 Processing: {filename} (Asset ID: {asset_id}, {face_count} faces)")
        
        # Check if image file exists
        if not os.path.exists(image_path):
            print(f"❌ Image not found: {image_path}")
            return None
            
        try:
            # Load image
            image = cv2.imread(image_path)
            if image is None:
                print(f"❌ Could not load image: {image_path}")
                return None
                
            # Get face detections
            faces = self.get_face_detections_for_image(asset_id)
            
            if not faces:
                print(f"❌ No face detections found for asset {asset_id}")
                return None
            
            # Create visualization
            vis_image = image.copy()
            
            for i, (face_id, bbox_x, bbox_y, bbox_w, bbox_h, person_id, embedding_path, created_at) in enumerate(faces):
                # Convert coordinates to integers
                x, y, w, h = int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h)
                
                # Generate color for this face (consistent per face_id)
                np.random.seed(face_id)
                color = tuple(map(int, np.random.randint(0, 255, 3)))
                
                # Draw bounding box
                cv2.rectangle(vis_image, (x, y), (x + w, y + h), color, 3)
                
                # Prepare label text
                label_parts = []
                label_parts.append(f"Face:{face_id}")
                if person_id:
                    label_parts.append(f"Person:{person_id}")
                if embedding_path:
                    label_parts.append("✓Emb")
                
                label = " | ".join(label_parts)
                
                # Draw label background
                label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                cv2.rectangle(vis_image, (x, y - label_size[1] - 10), 
                             (x + label_size[0], y), color, -1)
                
                # Draw label text
                cv2.putText(vis_image, label, (x, y - 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                print(f"  👤 Face {face_id}: ({x},{y}) {w}x{h}, person={person_id}")
            
            # Add image info
            info_text = f"Asset:{asset_id} | Faces:{face_count} | {filename}"
            cv2.putText(vis_image, info_text, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Save visualization
            output_filename = f"asset_{asset_id}_{Path(filename).stem}_faces.jpg"
            output_path = self.output_dir / output_filename
            
            # Resize if image is too large
            height, width = vis_image.shape[:2]
            if width > 1920 or height > 1080:
                scale = min(1920/width, 1080/height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                vis_image = cv2.resize(vis_image, (new_width, new_height))
            
            cv2.imwrite(str(output_path), vis_image)
            print(f"✅ Saved visualization: {output_path}")
            
            return output_path
            
        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
            return None
    
    def generate_summary_report(self):
        """Generate a summary report of face detection results"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get overall statistics
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT a.id) as total_images_with_faces,
                COUNT(fd.id) as total_faces_detected,
                COUNT(DISTINCT fd.person_id) as unique_persons
            FROM assets a
            INNER JOIN face_detections fd ON a.id = fd.asset_id
            WHERE a.mime LIKE 'image/%'
        """)
        
        stats = cursor.fetchone()
        total_images_with_faces, total_faces, unique_persons = stats
        
        # Get processing progress
        cursor.execute("SELECT COUNT(*) FROM assets WHERE mime LIKE 'image/%'")
        total_images = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(DISTINCT a.id) 
            FROM assets a
            WHERE a.mime LIKE 'image/%'
            AND EXISTS (SELECT 1 FROM face_detections fd WHERE fd.asset_id = a.id)
        """)
        processed_images = cursor.fetchone()[0]
        
        conn.close()
        
        print("\n" + "="*60)
        print("📊 FACE DETECTION RESULTS SUMMARY")
        print("="*60)
        print(f"📷 Total images in database: {total_images:,}")
        print(f"✅ Images processed with faces: {processed_images:,}")
        print(f"👤 Total faces detected: {total_faces:,}")
        print(f"👥 Unique persons identified: {unique_persons:,}" if unique_persons else "👥 Unique persons: 0")
        print(f"📈 Processing progress: {(processed_images/total_images)*100:.1f}%" if total_images > 0 else "📈 Progress: 0%")
        
        if total_images_with_faces > 0:
            print(f"📊 Faces per image (avg): {total_faces/total_images_with_faces:.1f}")
        
        return {
            'total_images': total_images,
            'processed_images': processed_images,
            'total_faces': total_faces,
            'unique_persons': unique_persons
        }
    
    def run_visualization(self, limit=10):
        """Run the complete visualization process"""
        print("🎨 Starting Face Detection Visualization")
        print(f"📁 Output directory: {self.output_dir}")
        
        # Generate summary
        stats = self.generate_summary_report()
        
        if stats['total_faces'] == 0:
            print("\n❌ No face detections found in database!")
            return
        
        # Get sample images with faces
        print(f"\n🖼️ Loading top {limit} images with most faces...")
        processed_images = self.get_processed_images_with_faces(limit)
        
        if not processed_images:
            print("❌ No processed images with faces found!")
            return
        
        print(f"✅ Found {len(processed_images)} images with face detections")
        
        # Visualize each image
        successful_visualizations = 0
        for asset_id, image_path, face_count in processed_images:
            result = self.visualize_image_with_faces(image_path, asset_id, face_count)
            if result:
                successful_visualizations += 1
        
        print(f"\n🎉 Successfully created {successful_visualizations} visualizations")
        print(f"📁 Check output directory: {self.output_dir}")

def main():
    parser = argparse.ArgumentParser(description='Visualize face detection results')
    parser.add_argument('--db', default='metadata.sqlite', help='Database path')
    parser.add_argument('--output', default='face_detection_results', help='Output directory')
    parser.add_argument('--limit', type=int, default=10, help='Number of images to visualize')
    
    args = parser.parse_args()
    
    visualizer = FaceDetectionVisualizer(args.db, args.output)
    visualizer.run_visualization(args.limit)

if __name__ == "__main__":
    main()
