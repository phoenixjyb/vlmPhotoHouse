#!/usr/bin/env python3
"""
Quick test script to validate AI automation setup
Tests all AI scripts for basic functionality without running full processing
"""

import sys
import subprocess
import json
from pathlib import Path

def run_python_check(script_path: Path, args: list = None) -> dict:
    """Run a Python script with validation args and capture result"""
    if not script_path.exists():
        return {"status": "error", "message": f"Script not found: {script_path}"}
    
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)
    
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=30,
            cwd=script_path.parent
        )
        
        return {
            "status": "success" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip() if result.stderr else None
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": "Script timed out after 30 seconds"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to run: {str(e)}"}

def main():
    print("🔍 AI Automation Setup Validation")
    print("=" * 50)
    
    # Define script paths
    workspace_root = Path(__file__).parent
    scripts_to_test = {
        "AI Orchestrator": workspace_root / "ai_orchestrator.py",
        "Caption Processor": workspace_root / "caption_processor.py", 
        "Drive E Integrator": workspace_root / "drive_e_backend_integrator.py",
        "AI Task Manager": workspace_root / "ai_task_manager.py"
    }
    
    results = {}
    
    # Test each script with --help or validation args
    for name, script_path in scripts_to_test.items():
        print(f"\n📋 Testing {name}...")
        print(f"   Script: {script_path}")
        
        # Try --help first
        result = run_python_check(script_path, ["--help"])
        if result["status"] == "success":
            print(f"   ✅ Help output working")
            results[name] = "✅ Working"
        else:
            # Try --mode=status if help fails
            result = run_python_check(script_path, ["--mode=status"])
            if result["status"] == "success":
                print(f"   ✅ Status mode working")
                results[name] = "✅ Working"
            else:
                print(f"   ❌ Error: {result.get('message', 'Unknown error')}")
                if result.get("stderr"):
                    print(f"   Error details: {result['stderr'][:200]}...")
                results[name] = "❌ Error"
    
    # Check Drive E state file
    print(f"\n📋 Testing Drive E State File...")
    state_file = workspace_root / "simple_drive_e_state.json"
    if state_file.exists():
        try:
            with open(state_file) as f:
                state_data = json.load(f)
            # Files are stored as top-level keys, not in a "files" dict
            file_count = len([k for k in state_data.keys() if k.startswith('E:\\')])
            print(f"   ✅ State file found with {file_count:,} files")
            results["Drive E State"] = f"✅ {file_count:,} files"
        except Exception as e:
            print(f"   ❌ Error reading state file: {e}")
            results["Drive E State"] = "❌ Invalid"
    else:
        print(f"   ⚠️  State file not found: {state_file}")
        results["Drive E State"] = "⚠️ Missing"
    
    # Check backend directory
    print(f"\n📋 Testing Backend Directory...")
    backend_dir = workspace_root / "backend"
    if backend_dir.exists():
        main_py = backend_dir / "app" / "main.py"
        if main_py.exists():
            print(f"   ✅ Backend app found: {main_py}")
            results["Backend"] = "✅ Found"
        else:
            print(f"   ⚠️  Backend app not found: {main_py}")
            results["Backend"] = "⚠️ Incomplete"
    else:
        print(f"   ❌ Backend directory not found: {backend_dir}")
        results["Backend"] = "❌ Missing"
    
    # Summary
    print(f"\n" + "=" * 50)
    print("📊 Validation Summary:")
    print("=" * 50)
    
    for component, status in results.items():
        print(f"  {component:<20} {status}")
    
    # Quick recommendation
    all_working = all("✅" in status for status in results.values())
    if all_working:
        print(f"\n🎉 All components validated successfully!")
        print(f"💡 Ready to run: .\\scripts\\start-ai-multiproc.ps1")
    else:
        print(f"\n⚠️  Some components need attention before running full automation")
        print(f"💡 You can still test individual components")
    
    print(f"\n🔧 Next Steps:")
    print(f"  1. Run PowerShell script: .\\scripts\\start-ai-multiproc.ps1")
    print(f"  2. Or single mode: .\\scripts\\start-ai-multiproc.ps1 -SingleMode")
    print(f"  3. Check individual components in the terminal tabs")

if __name__ == "__main__":
    main()
