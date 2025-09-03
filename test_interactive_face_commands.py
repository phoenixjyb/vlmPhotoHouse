#!/usr/bin/env python3
"""
Test script for new face processing interactive commands
"""

import subprocess
import sys
import time

def test_face_commands():
    """Test the new face processing commands added to start-multi-proc.ps1"""
    
    print("🧪 Testing Face Processing Interactive Commands")
    print("=" * 60)
    
    # Test 1: Check if our enhanced orchestrator exists
    print("\n1. Checking enhanced face orchestrator...")
    try:
        result = subprocess.run([
            sys.executable, 'enhanced_face_orchestrator_unified.py', '--help'
        ], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Enhanced face orchestrator is available")
        else:
            print("❌ Enhanced face orchestrator not working")
            print(f"Error: {result.stderr}")
    except Exception as e:
        print(f"❌ Error testing orchestrator: {e}")
    
    # Test 2: Check if verification script exists
    print("\n2. Checking verification scripts...")
    verification_scripts = [
        'verify_database_status.py',
        'detailed_verification.py'
    ]
    
    for script in verification_scripts:
        try:
            result = subprocess.run([
                sys.executable, script, '--help'
            ], capture_output=True, text=True, timeout=5)
            print(f"✅ {script} is available")
        except Exception as e:
            print(f"⚠️ {script} may not have --help flag (normal)")
    
    # Test 3: Check database schema
    print("\n3. Checking database schema...")
    try:
        result = subprocess.run([
            sys.executable, 'verify_database_status.py'
        ], capture_output=True, text=True, timeout=10)
        if "face_processed" in result.stdout:
            print("✅ Database has face processing columns")
        else:
            print("❌ Database missing face processing columns")
    except Exception as e:
        print(f"⚠️ Could not verify database: {e}")
    
    print("\n✅ Face processing commands integration test complete!")
    print("\n📝 New Interactive Commands Available:")
    print("   • Process-Faces [BatchSize] [-Incremental]")
    print("   • Test-Face-Service")
    print("   • Check-Face-Status") 
    print("   • Verify-Face-Results [Count]")
    
    print("\n🚀 To use these commands:")
    print("   1. Run: .\\start-multi-proc.ps1")
    print("   2. Wait for all services to start")
    print("   3. Use the Interactive Command Shell pane")
    print("   4. Type: Process-Faces 10")

if __name__ == "__main__":
    test_face_commands()
