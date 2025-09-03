#!/usr/bin/env python3
"""
Visualize face detection results by drawing bounding boxes on images
"""

import sqlite3
import cv2
import os
import numpy as np
from pathlib import Path

def visualize_face_detections(num_images=5, output_dir="face_detection_previews"):
    """Create visualization images with bounding boxes drawn on detected faces"""
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Connect to database
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    # Get recent face detections with valid coordinates
    cursor.execute('''
        SELECT fd.asset_id, a.path, fd.bbox_x, fd.bbox_y, fd.bbox_w, fd.bbox_h
        FROM face_detections fd
        JOIN assets a ON fd.asset_id = a.id
        WHERE fd.bbox_w > 0 AND fd.bbox_h > 0
        ORDER BY fd.asset_id DESC
        LIMIT ?
    ''', (num_images,))
    
    detections = cursor.fetchall()
    
    print(f"📸 Creating visualizations for {len(detections)} images with valid face detections...")
    
    for i, (asset_id, image_path, x, y, w, h) in enumerate(detections):
        try:
            # Check if image file exists
            if not os.path.exists(image_path):
                print(f"❌ Image not found: {image_path}")
                continue
            
            # Load image
            image = cv2.imread(image_path)
            if image is None:
                print(f"❌ Could not load image: {image_path}")
                continue
            
            # Get image dimensions
            img_height, img_width = image.shape[:2]
            
            # Draw bounding box
            x, y, w, h = int(x), int(y), int(w), int(h)
            
            # Draw rectangle (face bounding box)
            cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 3)  # Green box
            
            # Add text label
            filename = os.path.basename(image_path)
            label = f"Face {asset_id}: {w}x{h}"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.7
            thickness = 2
            
            # Get text size for background
            (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            
            # Draw text background
            cv2.rectangle(image, (x, y - text_height - 10), (x + text_width, y), (0, 255, 0), -1)
            
            # Draw text
            cv2.putText(image, label, (x, y - 5), font, font_scale, (0, 0, 0), thickness)
            
            # Add image info
            info_text = f"{filename} ({img_width}x{img_height})"
            cv2.putText(image, info_text, (10, 30), font, 0.6, (255, 255, 255), 2)
            
            # Save visualization
            output_filename = f"detection_{asset_id}_{filename}"
            output_path = os.path.join(output_dir, output_filename)
            
            # Resize if image is too large for display
            max_size = 1200
            if max(img_width, img_height) > max_size:
                scale = max_size / max(img_width, img_height)
                new_width = int(img_width * scale)
                new_height = int(img_height * scale)
                image = cv2.resize(image, (new_width, new_height))
            
            cv2.imwrite(output_path, image)
            
            print(f"✅ Created: {output_filename}")
            print(f"   Image size: {img_width}x{img_height}")
            print(f"   Face bbox: ({x}, {y}) size {w}x{h}")
            print(f"   Bbox covers: {(w*h)/(img_width*img_height)*100:.1f}% of image")
            print()
            
        except Exception as e:
            print(f"❌ Error processing {image_path}: {e}")
    
    conn.close()
    
    print(f"🎨 Visualization complete! Check the '{output_dir}' folder for images with bounding boxes.")
    print(f"📁 Output directory: {os.path.abspath(output_dir)}")

if __name__ == "__main__":
    visualize_face_detections()
