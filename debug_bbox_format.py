#!/usr/bin/env python3
"""
Debug the exact SCRFD bbox format by comparing with expected face dimensions
"""

import requests
import json
import cv2
import os

def debug_scrfd_bbox():
    # Test with a known image
    test_image_path = "/mnt/e/01_INCOMING/Jane/20220112_183922.jpg"
    windows_path = "E:/01_INCOMING/Jane/20220112_183922.jpg"
    
    # Get actual image dimensions
    if os.path.exists(windows_path):
        img = cv2.imread(windows_path)
        img_height, img_width = img.shape[:2]
        print(f"Image dimensions: {img_width} x {img_height}")
    else:
        print("Cannot load image for dimension check")
        img_width, img_height = None, None
    
    # Test SCRFD service
    session = requests.Session()
    session.proxies = {'http': None, 'https': None}
    
    try:
        response = session.post(
            "http://172.22.61.27:8003/process_image",
            json={"image_path": test_image_path},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            detections = result.get('detections', [])
            
            print(f"\nSCRFD returned {len(detections)} detection(s):")
            
            for i, detection in enumerate(detections):
                bbox = detection.get('bbox', [])
                conf = detection.get('confidence', 0)
                
                print(f"\nDetection {i+1}:")
                print(f"  Raw bbox: {bbox}")
                print(f"  Confidence: {conf:.3f}")
                
                if len(bbox) == 4:
                    # Test different interpretations
                    b1, b2, b3, b4 = bbox
                    
                    print(f"\n  Interpretation tests:")
                    print(f"  1. [x1, y1, w, h]: pos=({b1}, {b2}), size={b3}x{b4}, aspect={b3/b4 if b4>0 else 'inf':.2f}")
                    print(f"  2. [x1, y1, x2, y2]: pos=({b1}, {b2}), size={b3-b1}x{b4-b2}, aspect={(b3-b1)/(b4-b2) if b4-b2>0 else 'inf':.2f}")
                    
                    # Check if coordinates make sense relative to image size
                    if img_width and img_height:
                        print(f"\n  Sanity checks (image is {img_width}x{img_height}):")
                        
                        # Check interpretation 1: [x1, y1, w, h]
                        if b1 >= 0 and b2 >= 0 and b1+b3 <= img_width and b2+b4 <= img_height:
                            print(f"  ✅ [x1,y1,w,h] interpretation fits in image")
                        else:
                            print(f"  ❌ [x1,y1,w,h] interpretation EXCEEDS image bounds")
                        
                        # Check interpretation 2: [x1, y1, x2, y2] 
                        if b1 >= 0 and b2 >= 0 and b3 <= img_width and b4 <= img_height and b3 > b1 and b4 > b2:
                            print(f"  ✅ [x1,y1,x2,y2] interpretation fits in image")
                        else:
                            print(f"  ❌ [x1,y1,x2,y2] interpretation has issues")
                    
                    # Check face aspect ratio reasonableness
                    ratio1 = b3/b4 if b4 > 0 else float('inf')
                    ratio2 = (b3-b1)/(b4-b2) if (b4-b2) > 0 else float('inf')
                    
                    print(f"\n  Face aspect ratio analysis:")
                    print(f"  [x1,y1,w,h] ratio: {ratio1:.2f} {'✅ reasonable' if 0.5 <= ratio1 <= 2.0 else '❌ unreasonable'}")
                    print(f"  [x1,y1,x2,y2] ratio: {ratio2:.2f} {'✅ reasonable' if 0.5 <= ratio2 <= 2.0 else '❌ unreasonable'}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_scrfd_bbox()
