#!/usr/bin/env python3
"""
Test multiple images to understand SCRFD bbox format issues
"""

import requests
import json

def test_scrfd_bbox_format():
    # Test with multiple images to understand the pattern
    test_images = [
        "/mnt/e/01_INCOMING/Jane/20220112_043621.jpg",
        "/mnt/e/01_INCOMING/Jane/20220112_043706.jpg",
        "/mnt/e/01_INCOMING/Jane/20220112_043710.jpg"
    ]
    
    session = requests.Session()
    session.proxies = {'http': None, 'https': None}
    
    for img_path in test_images:
        print(f"\n=== Testing: {img_path.split('/')[-1]} ===")
        
        try:
            response = session.post(
                "http://172.22.61.27:8003/process_image",
                json={"image_path": img_path},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                detections = result.get('detections', [])
                
                print(f"Faces detected: {len(detections)}")
                
                for i, detection in enumerate(detections):
                    bbox = detection.get('bbox', [])
                    conf = detection.get('confidence', 0)
                    
                    print(f"  Face {i+1}:")
                    print(f"    Raw bbox: {bbox}")
                    print(f"    Confidence: {conf:.3f}")
                    
                    if len(bbox) == 4:
                        # Test different interpretations
                        print(f"    If [x1, y1, x2, y2]: width={bbox[2]-bbox[0]}, height={bbox[3]-bbox[1]}")
                        print(f"    If [x1, y1, w, h]: width={bbox[2]}, height={bbox[3]}")
                        print(f"    If [x2, y2, x1, y1]: width={bbox[2]-bbox[0]}, height={bbox[3]-bbox[1]}")
                        
            else:
                print(f"Error: {response.status_code}")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_scrfd_bbox_format()
