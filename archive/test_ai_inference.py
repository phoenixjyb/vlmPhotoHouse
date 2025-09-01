#!/usr/bin/env python3
"""
Test AI Model GPU Loading with Actual Inference
Forces models to load by running actual inference tasks
"""
import os
import sys
import traceback
from PIL import Image
import numpy as np

# Set up environment for RTX 3090
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
os.environ['EMBED_DEVICE'] = 'cuda:0'
os.environ['CAPTION_DEVICE'] = 'cuda:0'
os.environ['FACE_EMBED_PROVIDER'] = 'lvface'
os.environ['CAPTION_PROVIDER'] = 'blip2'
os.environ['LVFACE_EXTERNAL_DIR'] = r'C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace'
os.environ['CAPTION_EXTERNAL_DIR'] = r'C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels'

print("🔥 Testing RTX 3090 Model Loading with Actual Inference...")
print(f"CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES')}")

# Add backend to Python path
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

try:
    from app.face_embedding_service import get_face_embedding_provider
    from app.caption_service import get_caption_provider
    
    # Create a test image
    print("\n🖼️ Creating test image...")
    test_image = Image.new('RGB', (224, 224), color='red')
    
    print("\n🔍 Testing Face Embedding (LVFace) - This should load RTX 3090!")
    print("📋 Watch nvidia-smi in another window for memory spike...")
    
    try:
        face_provider = get_face_embedding_provider()
        print(f"✅ Face provider ready: {type(face_provider)}")
        
        print("🚀 Running face embedding inference...")
        embedding = face_provider.embed_face(test_image)
        print(f"✅ Face embedding completed: shape {embedding.shape}")
        print(f"✅ Embedding type: {type(embedding)}")
        
    except Exception as e:
        print(f"❌ Face embedding failed: {e}")
        traceback.print_exc()
    
    print("\n📝 Testing Caption Generation (BLIP2) - This should also use RTX 3090!")
    print("📋 Watch nvidia-smi for additional memory usage...")
    
    try:
        caption_provider = get_caption_provider()
        print(f"✅ Caption provider ready: {type(caption_provider)}")
        
        print("🚀 Running caption generation inference...")
        caption = caption_provider.caption_image(test_image)
        print(f"✅ Caption generated: '{caption}'")
        
    except Exception as e:
        print(f"❌ Caption generation failed: {e}")
        traceback.print_exc()
    
    print("\n🎯 Inference Test Complete!")
    print("💡 Check nvidia-smi now to see if RTX 3090 memory is allocated")
    
except Exception as e:
    print(f"❌ Setup failed: {e}")
    traceback.print_exc()
