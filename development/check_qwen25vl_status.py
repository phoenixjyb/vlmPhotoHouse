#!/usr/bin/env python3
"""
Quick test to check Qwen2.5-VL model availability and status
"""

import json
import subprocess
import time
import sys
from pathlib import Path

def test_qwen25vl_health():
    """Test if Qwen2.5-VL model is ready for inference."""
    
    print("🔍 Checking Qwen2.5-VL model status...")
    
    # Check if external directory exists
    external_dir = Path("C:/Users/yanbo/wSpace/vlm-photo-engine/vlmCaptionModels")
    if not external_dir.exists():
        print("❌ External caption models directory not found")
        return False
    
    # Check if inference script exists
    inference_script = external_dir / "inference.py"
    if not inference_script.exists():
        print("❌ Inference script not found")
        return False
    
    # Check if virtual environment exists
    python_exe = external_dir / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        print("❌ Virtual environment not found")
        return False
    
    print("✅ All required files found")
    
    # Test if model can be contacted
    try:
        print("🚀 Testing model health...")
        process = subprocess.Popen(
            [str(python_exe), str(inference_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait a bit for model to start
        time.sleep(5)
        
        # Send health check
        health_request = {"action": "health"}
        process.stdin.write(json.dumps(health_request) + "\n")
        process.stdin.flush()
        
        # Try to read response with timeout
        try:
            response_line = process.stdout.readline()
            if response_line:
                response = json.loads(response_line.strip())
                if response.get("status") == "healthy":
                    print("✅ Qwen2.5-VL model is ready and healthy!")
                    print(f"   Model: {response.get('model', 'Unknown')}")
                    print(f"   Device: {response.get('device', 'Unknown')}")
                    return True
                else:
                    print(f"⚠️  Model status: {response.get('status', 'Unknown')}")
                    return False
            else:
                print("⏳ Model is still loading (no response yet)")
                return False
        except json.JSONDecodeError as e:
            print(f"⚠️  Got non-JSON response: {response_line}")
            return False
        except Exception as e:
            print(f"⚠️  Error reading response: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing model: {e}")
        return False
    finally:
        try:
            # Send exit request
            exit_request = {"action": "exit"}
            process.stdin.write(json.dumps(exit_request) + "\n")
            process.stdin.flush()
            process.wait(timeout=5)
        except:
            process.terminate()

if __name__ == "__main__":
    is_ready = test_qwen25vl_health()
    if is_ready:
        print("\n🎉 Qwen2.5-VL is ready for captioning!")
    else:
        print("\n⏳ Qwen2.5-VL is not ready yet (may still be downloading/loading)")
    
    sys.exit(0 if is_ready else 1)
