#!/usr/bin/env python3
"""
Better Face Detection Visualizer - Shows only faces with valid coordinates
"""

import sqlite3
import cv2
import numpy as np
import os
from pathlib import Path

def get_faces_with_good_coordinates(db_path="metadata.sqlite", limit=5):
    """Get faces with valid (non-zero) coordinates"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT DISTINCT 
            a.id as asset_id,
            a.path as image_path,
            fd.id as face_id,
            fd.bbox_x,
            fd.bbox_y, 
            fd.bbox_w,
            fd.bbox_h,
            fd.person_id
        FROM assets a
        INNER JOIN face_detections fd ON a.id = fd.asset_id
        WHERE a.mime LIKE 'image/%'
        AND a.path IS NOT NULL
        AND fd.bbox_x > 10  -- Valid coordinates
        AND fd.bbox_y > 10
        AND fd.bbox_w > 50
        AND fd.bbox_h > 50
        ORDER BY a.id DESC
        LIMIT ?
    """, (limit,))
    
    results = cursor.fetchall()
    conn.close()
    return results

def visualize_face_with_details(asset_id, image_path, face_id, x, y, w, h, person_id):
    """Visualize a single face with detailed info"""
    print(f"\n📸 Asset {asset_id}: {os.path.basename(image_path)}")
    print(f"   👤 Face {face_id}: ({x:.1f}, {y:.1f}) {w:.1f}x{h:.1f}")
    
    if not os.path.exists(image_path):
        print(f"   ❌ Image not found: {image_path}")
        return None
        
    try:
        # Load image
        image = cv2.imread(image_path)
        if image is None:
            print(f"   ❌ Could not load image")
            return None
            
        h_img, w_img = image.shape[:2]
        print(f"   📐 Image size: {w_img}x{h_img}")
        
        # Convert coordinates to integers
        x, y, w, h = int(x), int(y), int(w), int(h)
        
        # Validate coordinates are within image bounds
        if x < 0 or y < 0 or x + w > w_img or y + h > h_img:
            print(f"   ⚠️ Face coordinates outside image bounds!")
            # Clip to image bounds
            x = max(0, min(x, w_img - 1))
            y = max(0, min(y, h_img - 1))
            w = min(w, w_img - x)
            h = min(h, h_img - y)
            print(f"   🔧 Clipped to: ({x}, {y}) {w}x{h}")
        
        # Create visualization
        vis_image = image.copy()
        
        # Draw thick green bounding box
        cv2.rectangle(vis_image, (x, y), (x + w, y + h), (0, 255, 0), 5)
        
        # Draw corner markers for better visibility
        corner_size = 20
        cv2.line(vis_image, (x, y), (x + corner_size, y), (0, 0, 255), 3)
        cv2.line(vis_image, (x, y), (x, y + corner_size), (0, 0, 255), 3)
        cv2.line(vis_image, (x + w, y + h), (x + w - corner_size, y + h), (0, 0, 255), 3)
        cv2.line(vis_image, (x + w, y + h), (x + w, y + h - corner_size), (0, 0, 255), 3)
        
        # Add detailed label
        label = f"Face:{face_id} ({x},{y}) {w}x{h}"
        if person_id:
            label += f" P:{person_id}"
            
        # Draw label with background
        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 2)[0]
        cv2.rectangle(vis_image, (x, y - label_size[1] - 15), 
                     (x + label_size[0] + 10, y - 5), (0, 255, 0), -1)
        cv2.putText(vis_image, label, (x + 5, y - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
        
        # Add image info at bottom
        info = f"Asset:{asset_id} | {os.path.basename(image_path)} | {w_img}x{h_img}"
        cv2.putText(vis_image, info, (10, h_img - 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        
        # Resize if too large
        if w_img > 1200 or h_img > 800:
            scale = min(1200/w_img, 800/h_img)
            new_w = int(w_img * scale)
            new_h = int(h_img * scale)
            vis_image = cv2.resize(vis_image, (new_w, new_h))
            print(f"   🔍 Resized to: {new_w}x{new_h}")
        
        # Save
        output_dir = Path("face_verification")
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"face_{face_id}_asset_{asset_id}.jpg"
        cv2.imwrite(str(output_file), vis_image)
        
        print(f"   ✅ Saved: {output_file}")
        return output_file
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

def main():
    print("🔍 Better Face Detection Verification")
    print("=" * 50)
    
    # Get faces with good coordinates
    faces = get_faces_with_good_coordinates(limit=8)
    
    if not faces:
        print("❌ No faces with valid coordinates found!")
        return
        
    print(f"✅ Found {len(faces)} faces with valid coordinates")
    
    success_count = 0
    for asset_id, image_path, face_id, x, y, w, h, person_id in faces:
        result = visualize_face_with_details(asset_id, image_path, face_id, x, y, w, h, person_id)
        if result:
            success_count += 1
    
    print(f"\n🎉 Successfully created {success_count} face verifications")
    print("📁 Check the 'face_verification' folder for detailed visualizations")

if __name__ == "__main__":
    main()
