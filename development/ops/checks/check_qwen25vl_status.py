#!/usr/bin/env python3
"""
Check Qwen2.5-VL External Caption Model Setup
"""

import os
import subprocess
import json
from pathlib import Path

def check_qwen25vl_status():
    external_dir = os.getenv('CAPTION_EXTERNAL_DIR')
    if not external_dir:
        print("CAPTION_EXTERNAL_DIR not set")
        return False
    
    ext = Path(external_dir)
    if not ext.exists():
        print(f"External dir does not exist: {ext}")
        return False
    
    py = ext / '.venv' / 'Scripts' / 'python.exe'
    infer = ext / 'inference.py'
    if not py.exists() or not infer.exists():
        print("Missing external venv or inference.py")
        return False
    
    cmd = [str(py), str(infer), '--provider','qwen25vl','--model','auto','--ping']
    print("Running:", ' '.join(cmd))
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            try:
                data = json.loads(res.stdout.strip())
                print("OK:", data)
                return True
            except json.JSONDecodeError:
                print("Invalid JSON:", res.stdout)
        else:
            print("Error:", res.stderr)
    except Exception as e:
        print("Exec error:", e)
    return False

if __name__ == '__main__':
    check_qwen25vl_status()
