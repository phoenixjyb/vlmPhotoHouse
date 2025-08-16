#!/usr/bin/env python3
"""
Direct test of Qwen2.5-VL inference script
"""

import json
import subprocess
import tempfile
import time
from pathlib import Path
from PIL import Image
import numpy as np

def create_test_image():
    """Create a simple test image for captioning."""
    test_image_path = Path(tempfile.gettempdir()) / "test_qwen25vl_direct.jpg"
    
    # Generate a simple test image (red square with blue circle)
    img = Image.new('RGB', (200, 200), color='red')
    pixels = np.array(img)
    center_x, center_y = 100, 100
    radius = 50
    y, x = np.ogrid[:200, :200]
    mask = (x - center_x)**2 + (y - center_y)**2 <= radius**2
    pixels[mask] = [0, 0, 255]  # Blue circle
    img = Image.fromarray(pixels)
    img.save(test_image_path)
    
    return str(test_image_path)

def test_inference_script():
    """Test the Qwen2.5-VL inference script directly."""
    
    # Create test image
    image_path = create_test_image()
    print(f"Created test image: {image_path}")
    
    try:
        # Path to the inference script
        script_path = r"C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels\inference.py"
        python_path = r"C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels\.venv\Scripts\python.exe"
        
        # Start the inference process
        print("Starting Qwen2.5-VL inference process...")
        process = subprocess.Popen(
            [python_path, script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # Wait for ready status
        print("Waiting for model to load...")
        while True:
            line = process.stdout.readline()
            if not line:
                break
            
            try:
                response = json.loads(line.strip())
                print(f"Status: {response}")
                
                if response.get("status") == "ready":
                    print("Model loaded successfully!")
                    break
                elif response.get("status") == "error":
                    print(f"Error loading model: {response.get('message')}")
                    return
            except json.JSONDecodeError:
                print(f"Non-JSON output: {line.strip()}")
        
        # Send caption request
        caption_request = {
            "action": "caption",
            "image_path": image_path,
            "prompt": "Describe this image in detail."
        }
        
        print("Sending caption request...")
        process.stdin.write(json.dumps(caption_request) + "\n")
        process.stdin.flush()
        
        # Read response
        response_line = process.stdout.readline()
        if response_line:
            try:
                response = json.loads(response_line.strip())
                print(f"Caption response: {response}")
                
                if response.get("status") == "success":
                    print(f"Generated caption: {response.get('caption')}")
                else:
                    print(f"Caption error: {response.get('message')}")
            except json.JSONDecodeError:
                print(f"Non-JSON response: {response_line.strip()}")
        
        # Send exit request
        exit_request = {"action": "exit"}
        process.stdin.write(json.dumps(exit_request) + "\n")
        process.stdin.flush()
        
        # Wait for process to complete
        process.wait(timeout=10)
        
    except Exception as e:
        print(f"Error testing inference script: {e}")
    finally:
        # Clean up
        if Path(image_path).exists():
            Path(image_path).unlink()
            print("Cleaned up test image")

if __name__ == "__main__":
    test_inference_script()
