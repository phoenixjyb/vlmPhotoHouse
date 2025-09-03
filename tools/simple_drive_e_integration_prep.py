#!/usr/bin/env python3
"""
Simple Drive E AI Integration

This script starts small by processing a subset of Drive E files for AI processing.
"""

import json
import os
import sys
from pathlib import Path

def get_sample_drive_e_directories():
    """Get a small sample of Drive E directories to test integration."""
    
    # Load the state file
    try:
        with open('simple_drive_e_state.json', 'r') as f:
            data = json.load(f)
        print(f"Loaded {len(data)} files from Drive E state")
    except Exception as e:
        print(f"Error loading state file: {e}")
        return []
    
    # Extract unique directories
    directories = set()
    for file_path in data.keys():
        directories.add(str(Path(file_path).parent))
    
    # Get a small sample for testing
    sample_dirs = list(directories)[:5]  # Just first 5 directories
    
    print(f"Sample directories to process:")
    for i, dir_path in enumerate(sample_dirs, 1):
        # Count files in this directory
        files_in_dir = [f for f in data.keys() if Path(f).parent == Path(dir_path)]
        print(f"  {i}. {dir_path} ({len(files_in_dir)} files)")
    
    return sample_dirs

def create_integration_command(directories):
    """Create the backend integration command."""
    
    # Create the curl command for manual execution
    dirs_json = json.dumps(directories)
    
    command = f'''curl -X POST "http://localhost:8000/ingest/scan" \\
     -H "Content-Type: application/json" \\
     -d '{{"paths": {dirs_json}}}'
'''
    
    print("\nTo integrate these directories with the AI backend, run:")
    print("1. First ensure the backend is running:")
    print("   cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
    print("\n2. Then run this command:")
    print(command)
    
    # Also save to a file
    with open('drive_e_integration_command.txt', 'w') as f:
        f.write("# Drive E AI Integration Command\n\n")
        f.write("# 1. Start backend server:\n")
        f.write("cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000\n\n")
        f.write("# 2. Run integration command:\n")
        f.write(command)
    
    print(f"\nCommand also saved to: drive_e_integration_command.txt")

def main():
    """Main function."""
    print("Drive E AI Integration Prep")
    print("=" * 40)
    
    sample_dirs = get_sample_drive_e_directories()
    
    if sample_dirs:
        create_integration_command(sample_dirs)
        
        print(f"\nNext Steps:")
        print("1. Start the backend server in a separate terminal")
        print("2. Run the integration command provided above")
        print("3. Monitor AI task progress via backend metrics")
    else:
        print("No directories found to process")

if __name__ == "__main__":
    main()
