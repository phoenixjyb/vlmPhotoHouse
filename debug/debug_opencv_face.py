#!/usr/bin/env python3
"""
Debug OpenCV Face Detection Issues
"""

import cv2
import numpy as np
import os

def debug_opencv_setup():
    """Debug OpenCV installation and cascade loading"""
    print("🔍 DEBUGGING OPENCV FACE DETECTION")
    print("=" * 50)
    
    # Check OpenCV version
    print(f"📦 OpenCV version: {cv2.__version__}")
    
    # Check cascade file
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    print(f"📁 Cascade path: {cascade_path}")
    print(f"📄 Cascade exists: {os.path.exists(cascade_path)}")
    
    # Try to load cascade
    try:
        face_cascade = cv2.CascadeClassifier(cascade_path)
        print(f"✅ Cascade loaded: {not face_cascade.empty()}")
    except Exception as e:
        print(f"❌ Cascade loading error: {e}")
        return None
        
    return face_cascade

def debug_image_processing(image_path):
    """Debug image loading and processing"""
    print(f"\n🖼️ DEBUGGING IMAGE: {os.path.basename(image_path)}")
    print("-" * 30)
    
    # Check if file exists
    if not os.path.exists(image_path):
        print(f"❌ File not found: {image_path}")
        return None
    
    # Load image
    try:
        image = cv2.imread(image_path)
        if image is None:
            print(f"❌ Could not load image")
            return None
            
        h, w = image.shape[:2]
        print(f"📐 Image dimensions: {w}x{h}")
        print(f"📊 Image channels: {image.shape[2] if len(image.shape) > 2 else 'Unknown'}")
        print(f"💾 Image dtype: {image.dtype}")
        
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        print(f"📐 Gray dimensions: {gray.shape}")
        print(f"📊 Gray dtype: {gray.dtype}")
        print(f"📈 Gray min/max: {gray.min()}/{gray.max()}")
        
        return image, gray
        
    except Exception as e:
        print(f"❌ Image processing error: {e}")
        return None

def test_face_detection_step_by_step(image, gray, cascade):
    """Test face detection with different parameters"""
    print(f"\n🎯 TESTING FACE DETECTION")
    print("-" * 30)
    
    h, w = gray.shape
    print(f"🔍 Testing on {w}x{h} image")
    
    # Test different parameters
    test_configs = [
        {"scaleFactor": 1.1, "minNeighbors": 5, "minSize": (30, 30)},
        {"scaleFactor": 1.05, "minNeighbors": 3, "minSize": (20, 20)},
        {"scaleFactor": 1.2, "minNeighbors": 4, "minSize": (40, 40)},
        {"scaleFactor": 1.3, "minNeighbors": 3, "minSize": (50, 50)},
    ]
    
    for i, config in enumerate(test_configs):
        print(f"\n🧪 Test {i+1}: {config}")
        
        try:
            # Add maxSize to prevent scale issues
            max_size = (min(w//2, h//2), min(w//2, h//2))
            
            faces = cascade.detectMultiScale(
                gray,
                scaleFactor=config["scaleFactor"],
                minNeighbors=config["minNeighbors"],
                minSize=config["minSize"],
                maxSize=max_size,
                flags=cv2.CASCADE_SCALE_IMAGE
            )
            
            print(f"   ✅ Success! Found {len(faces)} faces")
            for j, (x, y, w, h) in enumerate(faces):
                print(f"      Face {j+1}: ({x}, {y}) {w}x{h}")
                
            return faces
            
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            continue
    
    print("❌ All detection attempts failed")
    return []

def debug_specific_image():
    """Debug a specific problematic image"""
    # Use a sample image from our database
    import sqlite3
    
    conn = sqlite3.connect('metadata.sqlite')
    cursor = conn.cursor()
    cursor.execute("SELECT path FROM assets WHERE mime LIKE 'image/%' AND path IS NOT NULL LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print("❌ No images found in database")
        return
        
    image_path = result[0]
    
    # Debug OpenCV setup
    cascade = debug_opencv_setup()
    if cascade is None:
        return
        
    # Debug image processing
    result = debug_image_processing(image_path)
    if result is None:
        return
        
    image, gray = result
    
    # Test face detection
    faces = test_face_detection_step_by_step(image, gray, cascade)
    
    print(f"\n🎉 DEBUGGING COMPLETE")
    print(f"📊 Final result: {len(faces)} faces detected")

if __name__ == "__main__":
    debug_specific_image()
