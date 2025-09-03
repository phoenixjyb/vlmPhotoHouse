"""
GPU Pre-Check Validation for Multi-Environment AI Pipeline
Tests PyTorch GPU access across all environments before AI inference
"""
import os
import sys
import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime

class GPUPreChecker:
    def __init__(self):
        self.environments = {
            "vlm_main": {
                "name": "Main VLM Environment",
                "python_path": r".\.venv\Scripts\python.exe",
                "work_dir": ".",
                "expected_modules": ["torch", "transformers"]
            },
            "lvface": {
                "name": "LVFace Environment", 
                "python_path": r"C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace\.venv-lvface-311\Scripts\python.exe",
                "work_dir": r"C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace",
                "expected_modules": ["torch", "numpy", "cv2"]
            },
            "blip2": {
                "name": "BLIP2 Caption Environment",
                "python_path": r"C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels\.venv\Scripts\python.exe", 
                "work_dir": r"C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels",
                "expected_modules": ["torch", "transformers", "PIL"]
            }
        }
        
        self.results = {}
        
    def get_nvidia_smi_info(self) -> Dict:
        """Get GPU info from nvidia-smi"""
        try:
            import subprocess
            result = subprocess.run([
                "nvidia-smi", 
                "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits"
            ], capture_output=True, text=True, check=True)
            
            gpus = []
            rtx3090_index = None
            
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = [p.strip() for p in line.split(',')]
                    gpu_info = {
                        "nvidia_index": int(parts[0]),
                        "name": parts[1],
                        "memory_total_mb": int(parts[2]),
                        "memory_used_mb": int(parts[3]),
                        "utilization_percent": int(parts[4])
                    }
                    gpus.append(gpu_info)
                    
                    if "RTX 3090" in parts[1]:
                        rtx3090_index = int(parts[0])
            
            return {
                "success": True,
                "gpus": gpus,
                "rtx3090_nvidia_index": rtx3090_index,
                "total_gpus": len(gpus)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "gpus": [],
                "rtx3090_nvidia_index": None
            }
    
    def test_pytorch_environment(self, env_key: str, cuda_visible_devices: str) -> Dict:
        """Test PyTorch GPU access in specific environment"""
        env_config = self.environments[env_key]
        
        test_script = f'''
import os
import sys
os.environ["CUDA_VISIBLE_DEVICES"] = "{cuda_visible_devices}"

result = {{
    "env_name": "{env_config['name']}",
    "cuda_visible_devices": "{cuda_visible_devices}",
    "success": False,
    "pytorch_version": None,
    "cuda_available": False,
    "device_count": 0,
    "devices": [],
    "rtx3090_found": False,
    "error": None
}}

try:
    import torch
    result["pytorch_version"] = torch.__version__
    result["cuda_available"] = torch.cuda.is_available()
    
    if torch.cuda.is_available():
        result["device_count"] = torch.cuda.device_count()
        
        for i in range(result["device_count"]):
            try:
                name = torch.cuda.get_device_name(i)
                props = torch.cuda.get_device_properties(i)
                memory_gb = props.total_memory / (1024**3)
                
                device_info = {{
                    "pytorch_index": i,
                    "name": name,
                    "memory_gb": round(memory_gb, 1),
                    "memory_allocation_test": False
                }}
                
                # Test memory allocation
                try:
                    device = torch.device(f"cuda:{{i}}")
                    x = torch.randn(100, 100).to(device)
                    del x  # Clean up
                    torch.cuda.empty_cache()
                    device_info["memory_allocation_test"] = True
                except Exception as alloc_e:
                    device_info["allocation_error"] = str(alloc_e)
                
                result["devices"].append(device_info)
                
                if "RTX 3090" in name:
                    result["rtx3090_found"] = True
                    
            except Exception as device_e:
                result["devices"].append({{
                    "pytorch_index": i,
                    "error": str(device_e)
                }})
        
        result["success"] = result["rtx3090_found"]
    
except ImportError as e:
    result["error"] = f"PyTorch import failed: {{str(e)}}"
except Exception as e:
    result["error"] = f"General error: {{str(e)}}"

import json
print(json.dumps(result, indent=2))
'''
        
        try:
            import subprocess
            import json as json_lib
            
            # Execute in target environment
            proc = subprocess.run([
                env_config["python_path"], "-c", test_script
            ], capture_output=True, text=True, cwd=env_config["work_dir"], timeout=30)
            
            if proc.returncode == 0:
                return json_lib.loads(proc.stdout)
            else:
                return {
                    "env_name": env_config["name"],
                    "success": False,
                    "error": f"Process failed: {proc.stderr}",
                    "returncode": proc.returncode
                }
                
        except Exception as e:
            return {
                "env_name": env_config["name"], 
                "success": False,
                "error": f"Execution error: {str(e)}"
            }
    
    def run_comprehensive_check(self) -> Dict:
        """Run complete GPU pre-check across all environments"""
        print("🔍 Starting Comprehensive GPU Pre-Check...")
        
        # Step 1: nvidia-smi baseline
        print("\n📊 Step 1: nvidia-smi GPU Detection")
        nvidia_info = self.get_nvidia_smi_info()
        
        if not nvidia_info["success"]:
            print(f"❌ nvidia-smi failed: {nvidia_info['error']}")
            return {"success": False, "error": "nvidia-smi check failed"}
        
        print(f"✅ Found {nvidia_info['total_gpus']} GPUs")
        for gpu in nvidia_info["gpus"]:
            print(f"  GPU {gpu['nvidia_index']}: {gpu['name']} ({gpu['memory_total_mb']} MB)")
            
        if nvidia_info["rtx3090_nvidia_index"] is None:
            print("❌ RTX 3090 not found!")
            return {"success": False, "error": "RTX 3090 not detected"}
            
        print(f"🎯 RTX 3090 at nvidia-smi index: {nvidia_info['rtx3090_nvidia_index']}")
        
        # Step 2: Test PyTorch environments 
        print("\n🧪 Step 2: PyTorch Environment Tests")
        env_results = {}
        
        # Test both CUDA_VISIBLE_DEVICES configurations
        for cuda_devices in ["0", "1"]:
            print(f"\n  Testing CUDA_VISIBLE_DEVICES={cuda_devices}")
            
            for env_key in self.environments:
                env_name = self.environments[env_key]["name"]
                print(f"    {env_name}...")
                
                result = self.test_pytorch_environment(env_key, cuda_devices)
                
                if env_key not in env_results:
                    env_results[env_key] = {}
                env_results[env_key][f"cuda_{cuda_devices}"] = result
                
                if result.get("success"):
                    print(f"      ✅ RTX 3090 accessible")
                else:
                    error = result.get("error", "Unknown error") 
                    print(f"      ❌ Failed: {error}")
        
        # Step 3: Determine optimal configuration
        print("\n📋 Step 3: Configuration Analysis")
        
        optimal_config = None
        all_envs_success = True
        
        for cuda_devices in ["0", "1"]:
            cuda_success_count = 0
            
            for env_key in self.environments:
                result = env_results[env_key][f"cuda_{cuda_devices}"]
                if result.get("success"):
                    cuda_success_count += 1
            
            print(f"  CUDA_VISIBLE_DEVICES={cuda_devices}: {cuda_success_count}/{len(self.environments)} environments successful")
            
            if cuda_success_count == len(self.environments):
                optimal_config = cuda_devices
                print(f"    🎯 Optimal configuration found!")
                break
            elif cuda_success_count > 0 and optimal_config is None:
                optimal_config = cuda_devices
                all_envs_success = False
        
        # Results summary
        final_result = {
            "timestamp": datetime.now().isoformat(),
            "nvidia_smi_info": nvidia_info,
            "environment_results": env_results,
            "optimal_cuda_visible_devices": optimal_config,
            "all_environments_success": all_envs_success,
            "success": optimal_config is not None
        }
        
        if optimal_config:
            print(f"\n✅ RECOMMENDED CONFIGURATION:")
            print(f"   CUDA_VISIBLE_DEVICES={optimal_config}")
            print(f"   This gives RTX 3090 access as cuda:0")
        else:
            print(f"\n❌ NO WORKING CONFIGURATION FOUND")
            print(f"   RTX 3090 not accessible in any environment")
        
        return final_result

if __name__ == "__main__":
    checker = GPUPreChecker()
    results = checker.run_comprehensive_check()
    
    # Save detailed results
    with open("gpu_precheck_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Detailed results saved to: gpu_precheck_results.json")
    
    # Exit with appropriate code
    sys.exit(0 if results["success"] else 1)
