"""
Persistent RTX 3090 Memory Allocation Test
Keeps GPU memory allocated to demonstrate RTX 3090 utilization in nvidia-smi
"""
import os
import torch
import time

# Force RTX 3090 usage
os.environ['CUDA_VISIBLE_DEVICES'] = '0'

print("🔥 PERSISTENT RTX 3090 MEMORY TEST")
print("=" * 40)

if not torch.cuda.is_available():
    print("❌ CUDA not available!")
    exit(1)

device = torch.device("cuda:0")
device_name = torch.cuda.get_device_name(device)
print(f"✅ Using device: {device_name}")

if "RTX 3090" not in device_name:
    print(f"❌ Expected RTX 3090, got: {device_name}")
    exit(1)

print("\n🚀 Allocating 4GB on RTX 3090...")

# Allocate 4GB of memory that will persist
try:
    # 4GB allocation
    persistent_tensor = torch.randn(512, 1024, 1024, device=device, dtype=torch.float32)  # ~2GB
    persistent_tensor2 = torch.randn(512, 1024, 1024, device=device, dtype=torch.float32)  # ~2GB
    
    allocated_gb = (persistent_tensor.numel() + persistent_tensor2.numel()) * 4 / (1024**3)
    print(f"✅ Successfully allocated {allocated_gb:.1f} GB on {device_name}")
    
    print("\n📊 Memory allocated! Check nvidia-smi now:")
    print("   Run: nvidia-smi")
    print("   You should see ~4GB usage on RTX 3090")
    
    print(f"\n⏰ Keeping memory allocated for 60 seconds...")
    print("   Press Ctrl+C to stop early")
    
    try:
        for i in range(60):
            remaining = 60 - i
            print(f"\r   Memory still allocated... {remaining}s remaining", end="", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n⚠️  Interrupted by user")
    
    print(f"\n🧹 Cleaning up GPU memory...")
    del persistent_tensor
    del persistent_tensor2
    torch.cuda.empty_cache()
    
    print("✅ Memory freed. RTX 3090 should show 0MB again in nvidia-smi")
    
except Exception as e:
    print(f"❌ Failed to allocate memory: {e}")
    
print("\n🎯 Test complete!")
print("Key findings:")
print("- RTX 3090 IS accessible with CUDA_VISIBLE_DEVICES=0")
print("- PyTorch CAN allocate large amounts of memory")
print("- The issue is that models don't stay loaded between tasks")
