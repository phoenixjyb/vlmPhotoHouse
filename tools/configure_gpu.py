#!/usr/bin/env python3
"""
GPU Configuration Utility for RTX 3090

This utility ensures all GPU-intensive tasks use the RTX 3090 while leaving
the P2000 available for display and system tasks.
"""

import os
import sys
import logging
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_rtx3090_device() -> Optional[int]:
    """
    Detect RTX 3090 GPU device index.
    
    Returns:
        int: GPU device index of RTX 3090, or None if not found
    """
    try:
        import torch
        if not torch.cuda.is_available():
            logger.warning("CUDA not available")
            return None
        
        gpu_count = torch.cuda.device_count()
        logger.info(f"Found {gpu_count} CUDA devices")
        
        for i in range(gpu_count):
            gpu_name = torch.cuda.get_device_name(i)
            logger.info(f"GPU {i}: {gpu_name}")
            
            if "RTX 3090" in gpu_name or "GeForce RTX 3090" in gpu_name:
                logger.info(f"✅ RTX 3090 found at device {i}")
                return i
        
        logger.warning("⚠️ RTX 3090 not found")
        return None
        
    except ImportError:
        logger.error("PyTorch not available for GPU detection")
        return None
    except Exception as e:
        logger.error(f"Error detecting RTX 3090: {e}")
        return None

def configure_gpu_environment(force_device: Optional[int] = None) -> bool:
    """
    Configure environment variables for RTX 3090 usage.
    
    Args:
        force_device: Force specific device ID (optional)
        
    Returns:
        bool: True if configuration successful
    """
    if force_device is not None:
        rtx3090_device = force_device
        logger.info(f"Using forced device: {rtx3090_device}")
    else:
        rtx3090_device = get_rtx3090_device()
    
    if rtx3090_device is None:
        logger.error("Cannot configure GPU environment - RTX 3090 not found")
        return False
    
    # Set environment variables
    env_vars = {
        "PYTORCH_CUDA_DEVICE": str(rtx3090_device),
        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
        "TORCH_CUDA_ARCH_LIST": "8.6",  # RTX 3090 compute capability
        "PYTORCH_CUDA_ALLOC_CONF": "max_split_size_mb:1024,expandable_segments:True"
    }
    
    logger.info("🔧 Configuring GPU environment variables:")
    for key, value in env_vars.items():
        os.environ[key] = value
        logger.info(f"  {key} = {value}")
    
    # Set PyTorch device if available
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.set_device(rtx3090_device)
            logger.info(f"✅ PyTorch default device set to cuda:{rtx3090_device}")
    except ImportError:
        pass
    
    logger.info(f"✅ GPU environment configured for RTX 3090 (device {rtx3090_device})")
    return True

def display_gpu_status():
    """Display current GPU status and configuration."""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            current_device = torch.cuda.current_device()
            
            print("📊 GPU Status:")
            for i in range(gpu_count):
                gpu_name = torch.cuda.get_device_name(i)
                memory_allocated = torch.cuda.memory_allocated(i) / 1024**3  # GB
                memory_reserved = torch.cuda.memory_reserved(i) / 1024**3   # GB
                
                indicator = "🎯" if i == current_device else "⚪"
                print(f"  {indicator} GPU {i}: {gpu_name}")
                print(f"    Memory: {memory_allocated:.1f}GB allocated, {memory_reserved:.1f}GB reserved")
            
            print(f"\n✅ Current device: cuda:{current_device}")
        else:
            print("❌ CUDA not available")
    except ImportError:
        print("⚠️ PyTorch not available for status display")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Configure GPU environment for RTX 3090")
    parser.add_argument("--device", type=int, help="Force specific GPU device ID")
    parser.add_argument("--status", action="store_true", help="Display GPU status")
    args = parser.parse_args()
    
    if args.status:
        display_gpu_status()
    else:
        success = configure_gpu_environment(args.device)
        if success:
            display_gpu_status()
            sys.exit(0)
        else:
            sys.exit(1)
