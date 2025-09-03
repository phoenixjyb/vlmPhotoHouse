#!/usr/bin/env python3
"""
Analyze SCRFD coordinate format to determine correct interpretation
"""

def analyze_coordinates():
    """Analyze the SCRFD coordinates from the test output"""
    
    print("🔍 Analyzing SCRFD coordinate format from test output:")
    print()
    
    # From the test output:
    faces = [
        {"bbox": [252, 347, 121, 140], "confidence": 0.874},
        {"bbox": [606, 430, 24, 28], "confidence": 0.787},
        {"bbox": [665, 593, 24, 28], "confidence": 0.668},
        {"bbox": [742, 477, 23, 37], "confidence": 0.665},
        {"bbox": [703, 419, 19, 28], "confidence": 0.562}
    ]
    
    print("Raw SCRFD output:")
    for i, face in enumerate(faces, 1):
        bbox = face["bbox"]
        print(f"  Face {i}: {bbox}")
    
    print("\nTesting different coordinate interpretations:")
    
    for i, face in enumerate(faces, 1):
        bbox = face["bbox"]
        a, b, c, d = bbox
        
        print(f"\nFace {i}: [{a}, {b}, {c}, {d}]")
        
        # Test interpretation 1: [x1, y1, x2, y2]
        x1, y1, x2, y2 = a, b, c, d
        w1 = x2 - x1
        h1 = y2 - y1
        print(f"  [x1,y1,x2,y2]: pos=({x1},{y1}) size={w1}x{h1} {'✅' if w1>0 and h1>0 else '❌'}")
        
        # Test interpretation 2: [x1, y1, w, h]
        x, y, w, h = a, b, c, d
        print(f"  [x,y,w,h]: pos=({x},{y}) size={w}x{h} {'✅' if w>0 and h>0 else '❌'}")
        
        # Test interpretation 3: [x1, y2, x2, y1] (what we tried)
        x1, y2, x2, y1 = a, b, c, d
        w3 = x2 - x1
        h3 = y2 - y1
        print(f"  [x1,y2,x2,y1]: pos=({x1},{y1}) size={w3}x{h3} {'✅' if w3>0 and h3>0 else '❌'}")
        
        # Test interpretation 4: [x2, y2, x1, y1]
        x2, y2, x1, y1 = a, b, c, d
        w4 = x2 - x1
        h4 = y2 - y1
        print(f"  [x2,y2,x1,y1]: pos=({x1},{y1}) size={w4}x{h4} {'✅' if w4>0 and h4>0 else '❌'}")
        
        # Test interpretation 5: [center_x, center_y, w, h]
        cx, cy, w, h = a, b, c, d
        x = cx - w/2
        y = cy - h/2
        print(f"  [cx,cy,w,h]: pos=({x:.1f},{y:.1f}) size={w}x{h} {'✅' if w>0 and h>0 else '❌'}")

if __name__ == "__main__":
    analyze_coordinates()
