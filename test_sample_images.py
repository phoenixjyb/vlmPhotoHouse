#!/usr/bin/env python3
"""
Comprehensive test using sample images to debug coordinate system and multiple face detection
"""

import requests
import json
import cv2
import os
import numpy as np
from pathlib import Path

def test_sample_images():
    """Test SCRFD with sample images to debug coordinates and multiple faces"""
    
    # Sample images folder
    sample_folder = "face_detection_results"
    output_folder = "coordinate_debug_results"
    os.makedirs(output_folder, exist_ok=True)
    
    # Get all sample images
    sample_images = [f for f in os.listdir(sample_folder) if f.endswith('.jpg')]
    print(f"📸 Found {len(sample_images)} sample images for testing")
    
    # Test each image
    session = requests.Session()
    session.proxies = {'http': None, 'https': None}
    
    for i, filename in enumerate(sample_images[:5]):  # Test first 5 images
        print(f"\n{'='*60}")
        print(f"🔍 Testing: {filename}")
        print(f"{'='*60}")
        
        image_path = os.path.join(sample_folder, filename)
        
        # Load image to get dimensions
        img = cv2.imread(image_path)
        if img is None:
            print(f"❌ Could not load image: {image_path}")
            continue
            
        img_height, img_width = img.shape[:2]
        print(f"📐 Image dimensions: {img_width} x {img_height}")
        
        # Convert path for WSL
        # These are local files, so we need to convert the path
        wsl_path = f"/mnt/c/Users/yanbo/wSpace/vlm-photo-engine/vlmPhotoHouse/{sample_folder}/{filename}"
        
        try:
            # Test SCRFD service
            response = session.post(
                "http://172.22.61.27:8003/process_image",
                json={"image_path": wsl_path},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                detections = result.get('detections', [])
                
                print(f"👥 Faces detected: {len(detections)}")
                
                if len(detections) == 0:
                    print("   No faces detected - might be coordinate or detection issue")
                    continue
                
                # Create visualization image
                vis_img = img.copy()
                
                for j, detection in enumerate(detections):
                    bbox = detection.get('bbox', [])
                    conf = detection.get('confidence', 0)
                    
                    print(f"\n  Face {j+1}:")
                    print(f"    Raw bbox: {bbox}")
                    print(f"    Confidence: {conf:.3f}")
                    
                    if len(bbox) == 4:
                        # Test all reasonable interpretations
                        a, b, c, d = bbox
                        
                        interpretations = [
                            ("x1,y1,x2,y2", a, b, c-a, d-b, a, b),
                            ("x1,y1,w,h", a, b, c, d, a, b),
                            ("x_min,y_max,x_max,y_min", a, d, c-a, b-d, a, d),
                            ("x_max,y_max,x_min,y_min", c, d, a-c, b-d, c, d)
                        ]
                        
                        valid_interpretations = []
                        
                        for name, x, y, w, h, draw_x, draw_y in interpretations:
                            # Check if this interpretation makes sense
                            if (w > 0 and h > 0 and 
                                x >= 0 and y >= 0 and 
                                x + w <= img_width and y + h <= img_height and
                                0.3 <= w/h <= 3.0):  # Reasonable aspect ratio
                                
                                valid_interpretations.append((name, x, y, w, h, draw_x, draw_y))
                                print(f"    ✅ {name}: pos=({x:.0f},{y:.0f}), size={w:.0f}x{h:.0f}, aspect={w/h:.2f}")
                        
                        # If we have valid interpretations, draw them
                        if valid_interpretations:
                            # Use the most reasonable one (first valid)
                            name, x, y, w, h, draw_x, draw_y = valid_interpretations[0]
                            
                            # Draw bounding box
                            color = (0, 255, 0) if j == 0 else (255, 0, 0)  # Green for first, red for others
                            cv2.rectangle(vis_img, (int(draw_x), int(draw_y)), 
                                        (int(draw_x + w), int(draw_y + h)), color, 3)
                            
                            # Add label
                            label = f"Face{j+1}: {name}"
                            cv2.putText(vis_img, label, (int(draw_x), int(draw_y-10)), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                        else:
                            print(f"    ❌ No valid interpretations found")
                
                # Save visualization
                output_path = os.path.join(output_folder, f"debug_{filename}")
                
                # Resize if too large
                max_size = 1200
                if max(img_width, img_height) > max_size:
                    scale = max_size / max(img_width, img_height)
                    new_width = int(img_width * scale)
                    new_height = int(img_height * scale)
                    vis_img = cv2.resize(vis_img, (new_width, new_height))
                
                cv2.imwrite(output_path, vis_img)
                print(f"💾 Saved visualization: {output_path}")
                
            else:
                print(f"❌ Service error: {response.status_code}")
                print(f"Response: {response.text}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print(f"\n🎨 Debug complete! Check '{output_folder}' for visualizations.")

if __name__ == "__main__":
    test_sample_images()
