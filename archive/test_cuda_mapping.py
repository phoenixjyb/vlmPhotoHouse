import torch
import os

print("=== CUDA DEVICE MAPPING TEST ===")

# Test 1: All GPUs visible
print("Test 1: All GPUs visible")
for i in range(torch.cuda.device_count()):
    name = torch.cuda.get_device_name(i)
    print(f"  cuda:{i} -> {name}")

print()
print("Test 2: Setting CUDA_VISIBLE_DEVICES=1 (RTX 3090 only)")
os.environ['CUDA_VISIBLE_DEVICES'] = '1'

# Force CUDA to reinitialize
torch.cuda.empty_cache()

# Check what CUDA sees now
device_count = torch.cuda.device_count()
print(f"Device count: {device_count}")
for i in range(device_count):
    name = torch.cuda.get_device_name(i)
    print(f"  cuda:{i} -> {name}")

# Test memory allocation
try:
    device = torch.device('cuda:0')
    x = torch.randn(1000, 1000).to(device)
    memory_allocated = torch.cuda.memory_allocated(0) / 1024**2
    print(f"✅ Allocated {memory_allocated:.1f} MB on cuda:0")
    print(f"✅ cuda:0 device: {torch.cuda.get_device_name(0)}")
except Exception as e:
    print(f"❌ Failed: {e}")
