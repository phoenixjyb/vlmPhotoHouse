#!/usr/bin/env python3
"""
Test all possible bbox coordinate permutations to find the correct format
"""

import requests
import json

def test_all_bbox_permutations():
    # Test with an image that we know has issues
    test_image_path = "/mnt/e/01_INCOMING/Jane/20220112_043621.jpg"
    
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
            
            if detections:
                bbox = detections[0].get('bbox', [])
                print(f"Raw bbox: {bbox}")
                
                if len(bbox) == 4:
                    a, b, c, d = bbox
                    
                    print(f"\nTesting all permutations:")
                    print(f"1. [x1, y1, x2, y2]: ({a}, {b}) to ({c}, {d}), size: {c-a}x{d-b}, aspect: {(c-a)/(d-b) if d-b != 0 else 'inf':.2f}")
                    print(f"2. [x1, y1, w, h]:   ({a}, {b}), size: {c}x{d}, aspect: {c/d if d != 0 else 'inf':.2f}")
                    print(f"3. [x2, y2, x1, y1]: ({c}, {d}) to ({a}, {b}), size: {a-c}x{b-d}, aspect: {(a-c)/(b-d) if b-d != 0 else 'inf':.2f}")
                    print(f"4. [w, h, x1, y1]:   ({c}, {d}), size: {a}x{b}, aspect: {a/b if b != 0 else 'inf':.2f}")
                    print(f"5. [x1, x2, y1, y2]: ({a}, {c}) to ({b}, {d}), size: {c-a}x{d-b}, aspect: {(c-a)/(d-b) if d-b != 0 else 'inf':.2f}")
                    print(f"6. [y1, x1, y2, x2]: ({b}, {a}) to ({d}, {c}), size: {c-a}x{d-b}, aspect: {(c-a)/(d-b) if d-b != 0 else 'inf':.2f}")
                    
                    # Reasonable face aspect ratios are typically 0.5 to 2.0
                    reasonable_ratios = []
                    
                    ratios = [
                        (c-a)/(d-b) if d-b != 0 else float('inf'),  # [x1, y1, x2, y2]
                        c/d if d != 0 else float('inf'),            # [x1, y1, w, h]
                        (a-c)/(b-d) if b-d != 0 else float('inf'),  # [x2, y2, x1, y1]
                        a/b if b != 0 else float('inf'),            # [w, h, x1, y1]
                        (c-a)/(d-b) if d-b != 0 else float('inf'),  # [x1, x2, y1, y2]
                        (c-a)/(d-b) if d-b != 0 else float('inf')   # [y1, x1, y2, x2]
                    ]
                    
                    formats = [
                        "[x1, y1, x2, y2]",
                        "[x1, y1, w, h]",
                        "[x2, y2, x1, y1]", 
                        "[w, h, x1, y1]",
                        "[x1, x2, y1, y2]",
                        "[y1, x1, y2, x2]"
                    ]
                    
                    print(f"\nReasonable aspect ratios (0.5-2.0):")
                    for i, (fmt, ratio) in enumerate(zip(formats, ratios)):
                        if 0.5 <= ratio <= 2.0:
                            print(f"✅ {fmt}: aspect={ratio:.2f}")
                        else:
                            print(f"❌ {fmt}: aspect={ratio:.2f}")
                
        else:
            print(f"Error: {response.status_code}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_all_bbox_permutations()
