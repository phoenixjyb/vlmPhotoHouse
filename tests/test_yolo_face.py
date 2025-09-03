#!/usr/bin/env python3
"""
YOLO Face Detection Test
"""

import cv2
import numpy as np
import sqlite3
from pathlib import Path

def test_yolo_face_detection():
    print("🚀 Testing YOLO Face Detection")
    print("="*50)
    
    try:
        # Try to import ultralytics (YOLOv8)
        from ultralytics import YOLO
        print("✅ ultralytics imported successfully")
    except ImportError:
        print("❌ ultralytics not found. Installing...")
        import subprocess
        subprocess.check_call([".venv\\Scripts\\python.exe", "-m", "pip", "install", "ultralytics"])
        from ultralytics import YOLO
        print("✅ ultralytics installed and imported")
    
    # Load YOLOv8 model (will download automatically)
    print("📦 Loading YOLOv8n model...")
    model = YOLO('yolov8n.pt')  # nano version for speed
    print("✅ YOLOv8 model loaded")
    
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
    
    # Load image
    image = cv2.imread(image_path)
    if image is None:
        print(f"❌ Could not load image: {image_path}")
        return
        
    h, w = image.shape[:2]
    print(f"📐 Image shape: {w}x{h}")
    
    # Run YOLO detection
    print("🔍 Running YOLO detection...")
    results = model(image)
    
    # Extract person detections (class 0 is person in COCO dataset)
    detections = results[0].boxes
    
    if detections is None:
        print("❌ No detections found")
        return
    
    # Filter for person detections (faces are typically part of person detections)
    person_detections = []
    face_detections = []
    
    for i, box in enumerate(detections):
        class_id = int(box.cls[0])
        confidence = float(box.conf[0])
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        
        # Class 0 is person in COCO
        if class_id == 0 and confidence > 0.5:
            person_detections.append({
                'bbox': (int(x1), int(y1), int(x2-x1), int(y2-y1)),
                'confidence': confidence
            })
            print(f"  Person {len(person_detections)}: conf={confidence:.3f}, bbox=({int(x1)},{int(y1)},{int(x2-x1)},{int(y2-y1)})")
    
    print(f"👤 Found {len(person_detections)} person detections")
    
    # For better face detection, let's try to crop person regions and detect faces within them
    # But first, let's visualize what YOLO found
    
    vis_image = image.copy()
    
    for i, detection in enumerate(person_detections):
        x, y, w, h = detection['bbox']
        confidence = detection['confidence']
        
        # Draw bounding box
        cv2.rectangle(vis_image, (x, y), (x + w, y + h), (0, 255, 0), 4)
        
        # Add label
        label = f"Person {i+1}: {confidence:.3f}"
        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)[0]
        cv2.rectangle(vis_image, (x, y - label_size[1] - 10), 
                     (x + label_size[0], y), (0, 255, 0), -1)
        cv2.putText(vis_image, label, (x, y - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    
    # Add image info
    info = f"YOLO Detection: {Path(image_path).name} | {w}x{h} | {len(person_detections)} persons"
    cv2.putText(vis_image, info, (20, h - 30), 
               cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    
    # Save visualization
    output_dir = Path("yolo_face_detection")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"yolo_detection_{Path(image_path).stem}.jpg"
    
    # Resize if too large
    if w > 1200 or h > 800:
        scale = min(1200/w, 800/h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        vis_image = cv2.resize(vis_image, (new_w, new_h))
        print(f"🔍 Resized for display: {new_w}x{new_h}")
    
    cv2.imwrite(str(output_file), vis_image)
    print(f"✅ Saved YOLO visualization: {output_file}")
    
    return output_file, len(person_detections)

if __name__ == "__main__":
    try:
        result_file, detection_count = test_yolo_face_detection()
        if result_file:
            print(f"\n🎉 YOLO test complete! Found {detection_count} person detections")
            print(f"📁 Check visualization: {result_file}")
        else:
            print("\n❌ YOLO test failed")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
