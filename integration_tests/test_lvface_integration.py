#!/usr/bin/env python3
"""Demo script for testing LVFace integration modes."""

import os
import sys
from pathlib import Path
from PIL import Image
import numpy as np

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

def test_builtin_mode():
    """Test using built-in ONNX model."""
    print("=== Testing Built-in LVFace Mode ===")
    
    # Set environment for built-in mode
    os.environ['FACE_EMBED_PROVIDER'] = 'lvface'
    os.environ['LVFACE_MODEL_PATH'] = 'models/lvface.onnx'
    # Clear external dir to force built-in mode
    os.environ.pop('LVFACE_EXTERNAL_DIR', None)
    
    try:
        from app.face_embedding_service import get_face_embedding_provider
        from app.config import get_settings
        
        # Clear caches
        get_face_embedding_provider.cache_clear()
        get_settings.cache_clear()
        
        provider = get_face_embedding_provider()
        print(f"Provider type: {type(provider).__name__}")
        
        # Test embedding
        image = Image.new('RGB', (112, 112), (128, 64, 192))
        embedding = provider.embed_face(image)
        
        print(f"Embedding shape: {embedding.shape}")
        print(f"Embedding norm: {np.linalg.norm(embedding):.3f}")
        print("✓ Built-in mode working")
        
    except Exception as e:
        print(f"✗ Built-in mode failed: {e}")

def test_subprocess_mode():
    """Test using external LVFace subprocess."""
    print("\n=== Testing Subprocess LVFace Mode ===")
    
    # Check if external dir is available
    external_dir = os.getenv('LVFACE_EXTERNAL_DIR', r"../LVFace")
    if not Path(external_dir).exists():
        print(f"✗ External LVFace directory not found: {external_dir}")
        return
    
    # Set environment for subprocess mode
    os.environ['FACE_EMBED_PROVIDER'] = 'lvface'
    os.environ['LVFACE_EXTERNAL_DIR'] = external_dir
    os.environ['LVFACE_MODEL_NAME'] = os.getenv('LVFACE_MODEL_NAME', 'LVFace-B_Glint360K.onnx')
    os.environ['FACE_EMBED_DIM'] = os.getenv('FACE_EMBED_DIM', '512')
    
    print(f"Using external dir: {external_dir}")
    print(f"Using model: {os.environ['LVFACE_MODEL_NAME']}")
    print(f"Target dimension: {os.environ['FACE_EMBED_DIM']}")
    
    try:
        from app.face_embedding_service import get_face_embedding_provider
        from app.config import get_settings
        
        # Clear caches
        get_face_embedding_provider.cache_clear()
        get_settings.cache_clear()
        
        provider = get_face_embedding_provider()
        print(f"Provider type: {type(provider).__name__}")
        
        # Test embedding
        image = Image.new('RGB', (112, 112), (64, 128, 255))
        embedding = provider.embed_face(image)
        
        print(f"Embedding shape: {embedding.shape}")
        print(f"Embedding norm: {np.linalg.norm(embedding):.3f}")
        print("✓ Subprocess mode working")
        
    except Exception as e:
        print(f"✗ Subprocess mode failed: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Run both tests."""
    print("LVFace Integration Demo")
    print("=" * 40)
    
    test_builtin_mode()
    test_subprocess_mode()
    
    print("\n=== Summary ===")
    print("Built-in mode: Uses models/lvface.onnx with current venv")
    print("Subprocess mode: Uses external LVFace installation with its own venv")
    print("\nTo use subprocess mode in production:")
    print("  FACE_EMBED_PROVIDER=lvface")
    print("  LVFACE_EXTERNAL_DIR=C:\\Users\\yanbo\\wSpace\\vlm-photo-engine\\LVFace")
    print("  LVFACE_MODEL_NAME=your_real_model.onnx")
    print("  FACE_EMBED_DIM=512  # or your model's dimension")

if __name__ == "__main__":
    main()
