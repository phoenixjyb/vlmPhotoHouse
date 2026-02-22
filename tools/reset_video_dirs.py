#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reset Video Directories for Re-ingestion

This script identifies directories containing video files and resets their
ingestion status to 'pending' so they can be reprocessed with video support enabled.
"""

import json
import os
import sys
from pathlib import Path

# Ensure UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


def _state_file(name: str) -> Path:
    data_root = Path(os.getenv("VLM_DATA_ROOT", r"E:\VLM_DATA"))
    state_dir = Path(os.getenv("VLM_STATE_DIR", str(data_root / "state")))
    preferred = state_dir / name
    legacy = Path(name)
    if preferred.exists():
        return preferred
    if legacy.exists():
        return legacy
    return preferred

def main():
    # Video extensions to look for
    video_extensions = {'.mp4', '.mov', '.mkv', '.avi', '.m4v', '.webm'}
    
    # Load the drive E state to see all files
    try:
        drive_state_file = _state_file('simple_drive_e_state.json')
        with open(drive_state_file, 'r', encoding='utf-8') as f:
            drive_e_data = json.load(f)
        print(f"Loaded {len(drive_e_data)} files from Drive E state")
    except Exception as e:
        print(f"Error loading Drive E state: {e}")
        return
    
    # Load current ingestion state
    try:
        ingestion_file = _state_file('drive_e_ingestion_state.json')
        with open(ingestion_file, 'r', encoding='utf-8') as f:
            ingestion_state = json.load(f)
        print(f"Loaded ingestion state for {len(ingestion_state)} directories")
    except Exception as e:
        print(f"Error loading ingestion state: {e}")
        return
    
    # Find directories with video files
    video_directories = set()
    total_videos = 0
    
    for file_path, file_info in drive_e_data.items():
        file_path_obj = Path(file_path)
        if file_path_obj.suffix.lower() in video_extensions:
            parent_dir = str(file_path_obj.parent)
            video_directories.add(parent_dir)
            total_videos += 1
    
    print(f"\nFound {total_videos} video files across {len(video_directories)} directories")
    
    # Reset video directories to pending
    reset_count = 0
    for directory in video_directories:
        if directory in ingestion_state:
            if ingestion_state[directory]['status'] == 'completed':
                print(f"Resetting to pending: {directory}")
                ingestion_state[directory]['status'] = 'pending'
                ingestion_state[directory]['last_error'] = "Reset for video processing"
                reset_count += 1
            else:
                print(f"Already pending: {directory}")
        else:
            print(f"Not in ingestion state: {directory}")
    
    print(f"\nReset {reset_count} directories to pending status")
    
    # Save updated ingestion state
    if reset_count > 0:
        try:
            ingestion_file.parent.mkdir(parents=True, exist_ok=True)
            with open(ingestion_file, 'w', encoding='utf-8') as f:
                json.dump(ingestion_state, f, indent=2, ensure_ascii=False)
            print("Saved updated ingestion state")
        except Exception as e:
            print(f"Error saving ingestion state: {e}")
    
    # Show final status
    pending_count = sum(1 for state in ingestion_state.values() if state['status'] == 'pending')
    completed_count = sum(1 for state in ingestion_state.values() if state['status'] == 'completed')
    
    print(f"\nFinal status:")
    print(f"  Pending directories: {pending_count}")
    print(f"  Completed directories: {completed_count}")
    print(f"  Total video files to process: {total_videos}")

if __name__ == "__main__":
    main()
