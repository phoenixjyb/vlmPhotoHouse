"""Quick test script to validate caption subprocess integration."""

import os
import tempfile
from PIL import Image
import numpy as np

# Test with a simple image
def create_test_image():
    """Create a simple test image."""
    # Create a 224x224 RGB image with some pattern
    img_array = np.zeros((224, 224, 3), dtype=np.uint8)
    
    # Add some pattern - blue square in center
    img_array[75:150, 75:150, 2] = 255  # Blue channel
    
    # Add some red diagonal
    for i in range(224):
        if i < 224:
            img_array[i, i, 0] = 255  # Red channel
    
    return Image.fromarray(img_array)

def test_caption_service():
    """Test caption service with both built-in and external modes."""
    import sys
    sys.path.insert(0, 'backend')
    
    from app.caption_service import get_caption_provider
    from app.config import get_settings
    
    print("Testing Caption Service Integration")
    print("=" * 50)
    
    settings = get_settings()
    print(f"Current provider config: {settings.caption_provider}")
    print(f"External dir config: {settings.caption_external_dir}")
    
    # Test built-in provider (should be stub)
    print("\n1. Testing built-in provider:")
    provider = get_caption_provider()
    print(f"   Provider: {provider.__class__.__name__}")
    print(f"   Model: {provider.get_model_name()}")
    
    # Test caption generation
    test_img = create_test_image()
    
    try:
        caption = provider.generate_caption(test_img)
        print(f"   Caption: '{caption}'")
        print("   ✅ Caption generation successful")
    except Exception as e:
        print(f"   ❌ Caption generation failed: {e}")
    
    # Test external provider (if configured)
    if settings.caption_external_dir:
        print("\n2. Testing external provider:")
        print(f"   External dir: {settings.caption_external_dir}")
        
        # Test validation
        try:
            from app.caption_validation import validate_caption_external_setup
            validate_caption_external_setup()
            print("   ✅ External setup validation passed")
        except Exception as e:
            print(f"   ❌ External setup validation failed: {e}")
    else:
        print("\n2. External provider not configured")
        print("   Set CAPTION_EXTERNAL_DIR to test external mode")
    
    print("\n3. Testing health endpoints:")
    from app.main import app
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    
    # Test main health endpoint
    response = client.get('/health')
    if response.status_code == 200:
        caption_info = response.json().get('caption', {})
        print(f"   Main health: {caption_info.get('provider', 'N/A')}")
        print("   ✅ Main health endpoint working")
    else:
        print(f"   ❌ Main health endpoint failed: {response.status_code}")
    
    # Test caption health endpoint
    response = client.get('/health/caption')
    if response.status_code == 200:
        data = response.json()
        print(f"   Caption health: {data.get('provider', 'N/A')} / {data.get('mode', 'N/A')}")
        print("   ✅ Caption health endpoint working")
    else:
        print(f"   ❌ Caption health endpoint failed: {response.status_code}")

if __name__ == "__main__":
    test_caption_service()
