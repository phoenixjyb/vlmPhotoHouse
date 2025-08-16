#!/usr/bin/env python3
"""
Test script for caption backend integration
"""

import os
import sys
import tempfile
from pathlib import Path

# Add the backend to the path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from PIL import Image
import numpy as np
from app.caption_service import get_caption_provider
from app.caption_subprocess import Qwen2VLSubprocessProvider
from app.config import Settings

def create_test_image():
    """Create a simple test image for captioning."""
    test_image_path = Path(tempfile.gettempdir()) / "test_caption_backend.jpg"
    
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

def test_caption_backend():
    """Test caption backend with Qwen2.5-VL."""
    
    # Create test image
    image_path = create_test_image()
    print(f"Created test image: {image_path}")
    
    try:
        print("\n=== Testing Caption Configuration ===")
        settings = Settings()
        print(f"Caption Configuration:")
        print(f"  Provider: {settings.caption_provider}")
        print(f"  External Dir: {settings.caption_external_dir}")
        print(f"  Device: {settings.caption_device}")
        
        print(f"\n=== Testing Caption Provider ===")
        try:
            provider = get_caption_provider()
            print(f"✅ Provider initialized: {provider.get_model_name()}")
            
            # Load image
            image = Image.open(image_path)
            print(f"✅ Image loaded: {image.size}")
            
            # Generate caption
            print("Generating caption...")
            caption = provider.generate_caption(image)
            print(f"✅ Generated caption: {caption}")
            
        except Exception as e:
            print(f"❌ Error with caption provider: {e}")
        
        print(f"\n=== Testing Subprocess Provider ===")
        if settings.caption_external_dir:
            try:
                subprocess_provider = Qwen2VLSubprocessProvider(settings.caption_external_dir)
                print(f"✅ Subprocess provider initialized: {subprocess_provider.get_model_name()}")
                
                # Load image
                image = Image.open(image_path)
                
                # Generate caption
                print("Generating caption with subprocess...")
                caption = subprocess_provider.generate_caption(image)
                print(f"✅ Generated caption: {caption}")
                
            except Exception as e:
                print(f"❌ Error with subprocess provider: {e}")
        else:
            print("No external directory configured")
        
        print(f"\n=== Summary ===")
        if settings.caption_external_dir and settings.caption_provider == "qwen2.5-vl":
            print("✅ Qwen2.5-VL setup is properly configured.")
        else:
            print("❌ External setup not properly configured.")
            
    except Exception as e:
        print(f"❌ Error during testing: {e}")
    finally:
        # Clean up test image
        if Path(image_path).exists():
            try:
                Path(image_path).unlink()
                print("Cleaned up test image")
            except PermissionError:
                print("Note: Could not delete test image (file in use)")
                pass

if __name__ == "__main__":
    test_caption_backend()
