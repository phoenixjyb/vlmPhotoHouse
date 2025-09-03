#!/usr/bin/env python3
"""
Direct WSL Face Processing - Bypass networking issues
Run face processing directly in WSL environment
"""

import subprocess
import json
import sys

def run_wsl_face_processing(image_path, batch_size=10):
    """Run face processing directly in WSL"""
    
    print(f"🚀 Starting WSL Direct Face Processing")
    print(f"📁 Processing path: {image_path}")
    
    # Create WSL command to process images
    wsl_script = f"""
cd /mnt/c/Users/yanbo/wSpace/vlm-photo-engine/LVFace
source .venv-cuda124-wsl/bin/activate

# Process images directly with Python script
python3 << 'EOF'
import os
import sys
import cv2
import numpy as np
import sqlite3
import json
from pathlib import Path

def process_images_directly():
    # Connect to database
    db_path = "/mnt/c/Users/yanbo/wSpace/vlm-photo-engine/vlmPhotoHouse/app.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get unprocessed images
    cursor.execute(\"\"\"
        SELECT a.id, a.path FROM assets a 
        LEFT JOIN face_detections fd ON a.id = fd.asset_id 
        WHERE fd.id IS NULL 
        AND a.path LIKE '%.jpg' OR a.path LIKE '%.jpeg' OR a.path LIKE '%.png'
        LIMIT {batch_size}
    \"\"\")
    
    images = cursor.fetchall()
    conn.close()
    
    print(f"📊 Found {{len(images)}} unprocessed images")
    
    for asset_id, image_path in images:
        try:
            # Convert Windows path to WSL path
            wsl_path = image_path.replace('\\\\', '/').replace('E:/', '/mnt/e/')
            
            if os.path.exists(wsl_path):
                print(f"🔍 Processing: {{os.path.basename(wsl_path)}}")
                
                # Simple OpenCV detection for now
                image = cv2.imread(wsl_path)
                if image is not None:
                    # Basic face detection
                    face_cascade = cv2.CascadeClassifier('/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml')
                    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(gray, 1.3, 5)
                    
                    if len(faces) > 0:
                        print(f"✅ Found {{len(faces)}} faces")
                        
                        # Save basic detection to database
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        
                        for i, (x, y, w, h) in enumerate(faces):
                            cursor.execute(\"\"\"
                                INSERT INTO face_detections 
                                (asset_id, bbox_x, bbox_y, bbox_w, bbox_h, confidence, 
                                 embedding_path, detection_model, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                            \"\"\", (asset_id, int(x), int(y), int(w), int(h), 0.8, 
                                   f"temp_embedding_{{asset_id}}_{{i}}.json", "opencv_direct"))
                        
                        conn.commit()
                        conn.close()
                    else:
                        print(f"❌ No faces detected")
                else:
                    print(f"❌ Could not load image")
            else:
                print(f"❌ Image not found: {{wsl_path}}")
                
        except Exception as e:
            print(f"❌ Error processing {{image_path}}: {{e}}")

if __name__ == "__main__":
    process_images_directly()
EOF
"""
    
    try:
        print("🔄 Executing WSL face processing...")
        result = subprocess.run(['wsl', '-d', 'Ubuntu-22.04', '--', 'bash', '-c', wsl_script], 
                              capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print("✅ WSL processing completed successfully!")
            print("📄 Output:")
            print(result.stdout)
        else:
            print("❌ WSL processing failed!")
            print("📄 Error:")
            print(result.stderr)
            
    except subprocess.TimeoutExpired:
        print("⏰ WSL processing timed out!")
    except Exception as e:
        print(f"❌ WSL execution error: {e}")

if __name__ == "__main__":
    run_wsl_face_processing("/mnt/e/01_INCOMING/", batch_size=50)
