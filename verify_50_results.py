#!/usr/bin/env python3
"""
Verification script for 50 images processing results
Check face detections, embeddings, visualizations, and database integrity
"""

import sqlite3
import os
import cv2
import json
import random
from datetime import datetime

def verify_processing_results():
    """Comprehensive verification of the 50 images processing"""
    
    print("🔍 VERIFICATION - 50 Images Processing Results")
    print("=" * 60)
    
    # Database analysis
    try:
        conn = sqlite3.connect('app.db')
        cursor = conn.cursor()
        
        # Count processed images with face detections
        cursor.execute("""
            SELECT COUNT(DISTINCT asset_id) FROM face_detections
        """)
        images_with_faces = cursor.fetchone()[0]
        
        # Total face detections
        cursor.execute("SELECT COUNT(*) FROM face_detections")
        total_faces = cursor.fetchone()[0]
        
        # Images with multiple faces
        cursor.execute("""
            SELECT asset_id, COUNT(*) as face_count 
            FROM face_detections 
            GROUP BY asset_id 
            HAVING COUNT(*) > 1
            ORDER BY face_count DESC
        """)
        multi_face_images = cursor.fetchall()
        
        print(f"📊 Database Analysis:")
        print(f"   Images with faces detected: {images_with_faces}")
        print(f"   Total face detections: {total_faces}")
        print(f"   Images with multiple faces: {len(multi_face_images)}")
        
        if multi_face_images:
            print(f"   Max faces in single image: {multi_face_images[0][1]}")
            print(f"   Top multi-face images:")
            for asset_id, face_count in multi_face_images[:5]:
                cursor.execute("SELECT path FROM assets WHERE id = ?", (asset_id,))
                path_result = cursor.fetchone()
                if path_result:
                    filename = os.path.basename(path_result[0])
                    print(f"      Asset {asset_id}: {face_count} faces - {filename}")
        
        # Sample some face detection data
        cursor.execute("""
            SELECT asset_id, bbox_x, bbox_y, bbox_w, bbox_h, embedding_path 
            FROM face_detections 
            ORDER BY asset_id 
            LIMIT 10
        """)
        sample_detections = cursor.fetchall()
        
        print(f"\n🎯 Sample Face Detections:")
        for asset_id, x, y, w, h, emb_path in sample_detections:
            has_embedding = "✅" if emb_path else "❌"
            print(f"   Asset {asset_id}: bbox=({x},{y},{w},{h}), embedding={has_embedding}")
        
        # Check for sample images to visualize
        cursor.execute("""
            SELECT a.id, a.path, COUNT(f.id) as face_count
            FROM assets a
            LEFT JOIN face_detections f ON a.id = f.asset_id
            WHERE a.mime LIKE 'image/%' AND a.id > 5 AND a.id <= 55
            GROUP BY a.id, a.path
            HAVING COUNT(f.id) > 0
            ORDER BY face_count DESC
            LIMIT 5
        """)
        
        visualization_candidates = cursor.fetchall()
        conn.close()
        
    except Exception as e:
        print(f"❌ Database verification error: {e}")
        return False
    
    # Check embeddings directory
    embeddings_dir = "embeddings"
    if os.path.exists(embeddings_dir):
        embedding_files = [f for f in os.listdir(embeddings_dir) if f.endswith('.json')]
        print(f"\n💾 Embeddings Files:")
        print(f"   Embedding files created: {len(embedding_files)}")
        
        if embedding_files:
            # Sample an embedding file
            sample_file = os.path.join(embeddings_dir, embedding_files[0])
            try:
                with open(sample_file, 'r') as f:
                    embedding_data = json.load(f)
                    if isinstance(embedding_data, list):
                        print(f"   Sample embedding dimension: {len(embedding_data)}")
                        print(f"   Embedding type: {type(embedding_data[0])} values")
                    print(f"   ✅ Embeddings properly saved as JSON")
            except Exception as e:
                print(f"   ❌ Error reading embedding: {e}")
    else:
        print(f"\n💾 Embeddings Files:")
        print(f"   ❌ No embeddings directory found")
    
    # Prepare visualization samples
    print(f"\n📸 Preparing Verification Samples:")
    print(f"   Found {len(visualization_candidates)} images with faces for visualization")
    
    return visualization_candidates

def create_verification_visualizations(candidates):
    """Create visualizations for verification"""
    
    if not candidates:
        print("❌ No candidates for visualization")
        return
    
    print(f"\n🎨 Creating Verification Visualizations...")
    
    # Create output directory
    output_dir = "verification_results"
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        conn = sqlite3.connect('app.db')
        cursor = conn.cursor()
        
        for i, (asset_id, image_path, face_count) in enumerate(candidates):
            if i >= 3:  # Limit to 3 samples
                break
                
            print(f"   Processing Asset {asset_id}: {face_count} faces")
            
            # Load image
            if not os.path.exists(image_path):
                print(f"   ❌ Image not found: {image_path}")
                continue
                
            img = cv2.imread(image_path)
            if img is None:
                print(f"   ❌ Could not load image: {image_path}")
                continue
            
            # Get face detections for this image
            cursor.execute("""
                SELECT bbox_x, bbox_y, bbox_w, bbox_h, embedding_path 
                FROM face_detections 
                WHERE asset_id = ?
            """, (asset_id,))
            
            face_boxes = cursor.fetchall()
            
            # Draw bounding boxes
            for j, (x, y, w, h, emb_path) in enumerate(face_boxes):
                # Draw rectangle
                color = (0, 255, 0) if emb_path else (0, 0, 255)  # Green if has embedding, red if not
                cv2.rectangle(img, (int(x), int(y)), (int(x+w), int(y+h)), color, 3)
                
                # Add label
                label = f"Face{j+1}"
                if emb_path:
                    label += " ✓"
                cv2.putText(img, label, (int(x), int(y-10)), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            
            # Save visualization
            filename = os.path.basename(image_path)
            output_path = os.path.join(output_dir, f"verify_{asset_id}_{filename}")
            cv2.imwrite(output_path, img)
            print(f"   ✅ Saved: {output_path}")
        
        conn.close()
        print(f"\n✅ Verification visualizations saved to: {output_dir}/")
        
    except Exception as e:
        print(f"❌ Visualization error: {e}")

def generate_verification_summary():
    """Generate final verification summary"""
    
    print(f"\n📋 VERIFICATION SUMMARY")
    print("=" * 40)
    print("✅ Face Detection: Check visualizations for bounding box accuracy")
    print("✅ Face Recognition: Check database for embedding_path entries")
    print("✅ Multiple Faces: Verify each face gets separate database entry")
    print("✅ GPU Acceleration: Fast processing indicates GPU usage")
    print()
    print("🔍 Next Steps:")
    print("1. Review visualization images in verification_results/")
    print("2. Check database entries match visual face count")
    print("3. Verify embedding files are created")
    print("4. If all looks good, continue with full dataset processing")

if __name__ == "__main__":
    # Run verification
    candidates = verify_processing_results()
    
    if candidates:
        create_verification_visualizations(candidates)
    
    generate_verification_summary()
