#!/usr/bin/env python3
"""
Test backend integration with external Qwen2.5-VL setup
"""

import os
import sys
from pathlib import Path

# Add the backend to the path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

def test_caption_config():
    """Test that caption configuration is properly loaded."""
    
    from app.config import get_settings
    
    settings = get_settings()
    
    print("Caption Configuration:")
    print(f"  Provider: {settings.caption_provider}")
    print(f"  External Dir: {settings.caption_external_dir}")
    print(f"  Device: {settings.caption_device}")
    
    # Check if external directory exists
    if settings.caption_external_dir:
        external_path = Path(settings.caption_external_dir)
        print(f"  External directory exists: {external_path.exists()}")
        
        if external_path.exists():
            venv_path = external_path / ".venv"
            inference_path = external_path / "inference.py"
            print(f"  Virtual environment exists: {venv_path.exists()}")
            print(f"  Inference script exists: {inference_path.exists()}")
    
    return settings

def test_caption_service_init():
    """Test that caption service can initialize with external setup."""
    
    try:
        from app.caption_service import get_caption_provider
        
        caption_provider = get_caption_provider()
        print("Caption Provider initialized successfully")
        print(f"  Provider type: {type(caption_provider).__name__}")
        print(f"  Model name: {caption_provider.get_model_name()}")
        
        return caption_provider
        
    except Exception as e:
        print(f"Error initializing caption provider: {e}")
        return None

def test_caption_subprocess_provider():
    """Test the subprocess provider for Qwen2.5-VL."""
    
    try:
        from app.caption_subprocess import Qwen2VLSubprocessProvider
        from app.config import get_settings
        
        settings = get_settings()
        
        if not settings.caption_external_dir:
            print("No external directory configured")
            return None
        
        provider = Qwen2VLSubprocessProvider(
            external_dir=settings.caption_external_dir,
            model_name="default"
        )
        
        print("Subprocess provider created successfully")
        print(f"  Provider type: {type(provider).__name__}")
        print(f"  External dir: {provider.external_dir}")
        print(f"  Python path: {provider.python_path}")
        print(f"  Script path: {provider.script_path}")
        
        # Check if paths exist
        print(f"  Python executable exists: {Path(provider.python_path).exists()}")
        print(f"  Inference script exists: {Path(provider.script_path).exists()}")
        
        return provider
        
    except Exception as e:
        print(f"Error creating subprocess provider: {e}")
        return None

if __name__ == "__main__":
    print("=== Testing Caption Configuration ===")
    settings = test_caption_config()
    
    print("\n=== Testing Caption Service ===")
    caption_provider = test_caption_service_init()
    
    print("\n=== Testing Subprocess Provider ===")
    provider = test_caption_subprocess_provider()
    
    print("\n=== Summary ===")
    if settings.caption_external_dir and caption_provider:
        print("✅ External Qwen2.5-VL setup is properly configured!")
        print("   Model download may still be in progress.")
        print("   Once download completes, captioning will be available.")
    else:
        print("❌ External setup not properly configured.")
