#!/usr/bin/env python3
"""
Test script for Qwen2.5-VL captioning system
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Add the backend to the path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from PIL import Image
import numpy as np
from app.caption_service import CaptionService

async def test_qwen25vl_caption():
    """Test Qwen2.5-VL captioning with a simple test image."""
    
    # Create a simple test image
    test_image_path = Path(tempfile.gettempdir()) / "test_qwen25vl.jpg"
    
    # Generate a simple test image (red square with blue circle)
    img = Image.new('RGB', (200, 200), color='red')
    # Create a simple pattern
    pixels = np.array(img)
    center_x, center_y = 100, 100
    radius = 50
    y, x = np.ogrid[:200, :200]
    mask = (x - center_x)**2 + (y - center_y)**2 <= radius**2
    pixels[mask] = [0, 0, 255]  # Blue circle
    img = Image.fromarray(pixels)
    img.save(test_image_path)
    
    print(f"Created test image: {test_image_path}")
    
    try:
        # Initialize caption service
        caption_service = CaptionService()
        print("Initialized caption service")
        
        # Generate caption
        print("Generating caption with Qwen2.5-VL...")
        caption = await caption_service.generate_caption(str(test_image_path))
        
        print(f"Generated caption: {caption}")
        
        return caption
        
    except Exception as e:
        print(f"Error during captioning: {e}")
        return None
    finally:
        # Clean up test image
        if test_image_path.exists():
            test_image_path.unlink()
            print("Cleaned up test image")

if __name__ == "__main__":
    asyncio.run(test_qwen25vl_caption())
