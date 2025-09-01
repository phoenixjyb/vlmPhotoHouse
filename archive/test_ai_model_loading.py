#!/usr/bin/env python3
"""
Test AI Model Loading for RTX 3090
Tests face embedding and caption services initialization
"""
import os
import sys
import traceback

# Set up environment for RTX 3090
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
os.environ['EMBED_DEVICE'] = 'cuda:0'
os.environ['CAPTION_DEVICE'] = 'cuda:0'
os.environ['FACE_EMBED_PROVIDER'] = 'lvface'
os.environ['CAPTION_PROVIDER'] = 'blip2'
os.environ['LVFACE_EXTERNAL_DIR'] = r'C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace'
os.environ['CAPTION_EXTERNAL_DIR'] = r'C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels'

print("🧪 Testing AI Model Loading with RTX 3090...")
print(f"CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES')}")
print(f"Working Directory: {os.getcwd()}")

# Add backend to Python path
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

try:
    print("\n📦 Testing imports...")
    from app.face_embedding_service import get_face_embedding_provider
    from app.caption_service import get_caption_provider
    print("✅ Imports successful")
    
    print("\n🔍 Testing face embedding provider (LVFace)...")
    try:
        face_provider = get_face_embedding_provider()
        print(f"✅ Face provider initialized: {type(face_provider)}")
        if hasattr(face_provider, 'device'):
            print(f"Face provider device: {face_provider.device}")
        
        # Test if it can access GPU
        if hasattr(face_provider, 'model'):
            print(f"Face model loaded: {type(face_provider.model)}")
        
    except Exception as e:
        print(f"❌ Face provider failed: {e}")
        traceback.print_exc()
    
    print("\n📝 Testing caption provider (BLIP2)...")
    try:
        caption_provider = get_caption_provider()
        print(f"✅ Caption provider initialized: {type(caption_provider)}")
        if hasattr(caption_provider, 'device'):
            print(f"Caption provider device: {caption_provider.device}")
            
        # Test if it can access GPU
        if hasattr(caption_provider, 'model'):
            print(f"Caption model loaded: {type(caption_provider.model)}")
        
    except Exception as e:
        print(f"❌ Caption provider failed: {e}")
        traceback.print_exc()

except ImportError as e:
    print(f"❌ Import failed: {e}")
    print("Backend modules not found. Checking backend structure...")
    
    backend_path = os.path.join(os.getcwd(), 'backend')
    if os.path.exists(backend_path):
        print(f"✅ Backend directory exists: {backend_path}")
        app_path = os.path.join(backend_path, 'app')
        if os.path.exists(app_path):
            print(f"✅ App directory exists: {app_path}")
            services_path = os.path.join(app_path, 'services')
            if os.path.exists(services_path):
                print(f"✅ Services directory exists: {services_path}")
                files = os.listdir(services_path)
                print(f"Services files: {files}")
            else:
                print(f"❌ Services directory missing: {services_path}")
        else:
            print(f"❌ App directory missing: {app_path}")
    else:
        print(f"❌ Backend directory missing: {backend_path}")

print("\n🎯 Model Loading Test Complete")
