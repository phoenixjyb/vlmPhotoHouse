#!/usr/bin/env python3
"""
Test SCRFD service directly with a real image
"""

import requests
import json

def main():
    # Test with the correct WSL path including the Jane subdirectory
    test_image_path = "/mnt/e/01_INCOMING/Jane/20220112_043621.jpg"  # Correct WSL path
    
    # Create session with no proxy
    session = requests.Session()
    session.proxies = {'http': None, 'https': None}
    
    try:
        response = session.post(
            "http://172.22.61.27:8003/process_image",
            json={"image_path": test_image_path},
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\nSCRFD Response Format Analysis:")
            print(f"Total faces detected: {result.get('faces', 0)}")
            print(f"Detector: {result.get('detector', 'unknown')}")
            
            detections = result.get('detections', [])
            for i, detection in enumerate(detections):
                print(f"\nFace {i+1}:")
                bbox = detection.get('bbox', [])
                print(f"  Raw bbox: {bbox}")
                print(f"  Confidence: {detection.get('confidence', 'N/A')}")
                
                if len(bbox) == 4:
                    # Analyze bbox format
                    x1, y1, x2, y2 = bbox
                    width = x2 - x1
                    height = y2 - y1
                    print(f"  Interpreted as [x1, y1, x2, y2]: ({x1}, {y1}, {x2}, {y2})")
                    print(f"  Calculated width: {width}, height: {height}")
                    
                    # The issue: SCRFD might return [x1, y1, x2, y2] format
                    # But we're treating it as [x, y, w, h] format
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
