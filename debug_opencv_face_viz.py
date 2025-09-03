#!/usr/bin/env python3
"""
Debug OpenCV Face Detection with Visualization
"""
import cv2
import numpy as np
import sqlite3
from pathlib import Path

def debug_face_detection_with_viz():
    print("🔍 DEBUG: OpenCV Face Detection with Visualization")
    print("="*60)
    
    # Get a sample image from database
    conn = sqlite3.connect('metadata.sqlite')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT path FROM assets 
        WHERE mime LIKE 'image/%' 
        AND path IS NOT NULL 
        LIMIT 1
    """)
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print("❌ No images found in database")
        return
        
    image_path = result[0]
    print(f"📸 Testing image: {image_path}")
    
    try:
        # Load image
        image = cv2.imread(image_path)
        if image is None:
            print(f"❌ Could not load image: {image_path}")
            return
            
        print(f"📐 Image shape: {image.shape}")
        h, w = image.shape[:2]
        
        # Initialize face cascade
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        if face_cascade.empty():
            print("❌ Could not load face cascade")
            return
            
        print("✅ Face cascade loaded successfully")
        
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        print(f"📐 Grayscale shape: {gray.shape}")
        
        # Test face detection with different parameters
        print("\n🔍 Testing face detection...")
        
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        print(f"👤 Found {len(faces)} faces")
        
        # Create visualization
        vis_image = image.copy()
        
        for i, (x, y, w, h) in enumerate(faces):
            print(f"  Face {i+1}: x={x}, y={y}, w={w}, h={h}")
            
            # Draw thick green bounding box
            cv2.rectangle(vis_image, (x, y), (x + w, y + h), (0, 255, 0), 8)
            
            # Draw corner markers
            corner_size = 30
            cv2.line(vis_image, (x, y), (x + corner_size, y), (0, 0, 255), 6)
            cv2.line(vis_image, (x, y), (x, y + corner_size), (0, 0, 255), 6)
            cv2.line(vis_image, (x + w, y + h), (x + w - corner_size, y + h), (0, 0, 255), 6)
            cv2.line(vis_image, (x + w, y + h), (x + w, y + h - corner_size), (0, 0, 255), 6)
            
            # Add label
            label = f"Face {i+1}: ({x},{y}) {w}x{h}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 2.0, 3)[0]
            
            # Draw label background
            cv2.rectangle(vis_image, (x, y - label_size[1] - 20), 
                         (x + label_size[0] + 10, y - 10), (0, 255, 0), -1)
            
            # Draw label text
            cv2.putText(vis_image, label, (x + 5, y - 15), 
                       cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 3)
        
        # Add image info
        info = f"Image: {Path(image_path).name} | {w}x{h} | {len(faces)} faces detected"
        cv2.putText(vis_image, info, (20, h - 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        
        # Resize for display if too large
        display_image = vis_image
        if w > 1200 or h > 800:
            scale = min(1200/w, 800/h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            display_image = cv2.resize(vis_image, (new_w, new_h))
            print(f"🔍 Resized for display: {new_w}x{new_h}")
        
        # Save visualization
        output_dir = Path("debug_face_detection")
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"opencv_face_debug_{Path(image_path).stem}.jpg"
        
        cv2.imwrite(str(output_file), vis_image)
        print(f"✅ Saved full resolution visualization: {output_file}")
        
        # Also save display version
        display_file = output_dir / f"opencv_face_debug_{Path(image_path).stem}_display.jpg"
        cv2.imwrite(str(display_file), display_image)
        print(f"✅ Saved display visualization: {display_file}")
        
        # Test what happens with different scale factors
        print("\n🧪 Testing different scale factors...")
        
        for scale_factor in [1.05, 1.1, 1.2, 1.3]:
            test_faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=scale_factor,
                minNeighbors=5,
                minSize=(30, 30),
                flags=cv2.CASCADE_SCALE_IMAGE
            )
            print(f"  Scale {scale_factor}: {len(test_faces)} faces")
        
        return output_file, len(faces)
        
    except Exception as e:
        print(f"❌ Error during detection: {e}")
        import traceback
        traceback.print_exc()
        return None, 0

if __name__ == "__main__":
    result_file, face_count = debug_face_detection_with_viz()
    if result_file:
        print(f"\n🎉 Debug complete! Found {face_count} faces")
        print(f"📁 Check visualization: {result_file}")
        print("📁 Files saved in debug_face_detection/ folder")
    else:
        print("\n❌ Debug failed")
