import os
import sys

# Set environment BEFORE importing torch
os.environ['CUDA_VISIBLE_DEVICES'] = sys.argv[1] if len(sys.argv) > 1 else '1'

import torch

print(f"CUDA_VISIBLE_DEVICES: {os.environ['CUDA_VISIBLE_DEVICES']}")
print(f"PyTorch CUDA available: {torch.cuda.is_available()}")
print(f"Device count: {torch.cuda.device_count()}")

for i in range(torch.cuda.device_count()):
    name = torch.cuda.get_device_name(i)
    memory = torch.cuda.get_device_properties(i).total_memory / 1024**3
    print(f"  cuda:{i} -> {name} ({memory:.1f} GB)")

# Test allocation on cuda:0
if torch.cuda.is_available():
    device = torch.device('cuda:0')
    x = torch.randn(1000, 1000).to(device)
    print(f"✅ Successfully using cuda:0: {torch.cuda.get_device_name(0)}")
