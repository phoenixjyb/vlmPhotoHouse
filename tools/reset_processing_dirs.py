#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reset Processing Directories

Reset directories that are stuck in 'processing' state back to 'pending' 
so they can be reprocessed to complete video ingestion.
"""

import json
import sys

# Ensure UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def reset_processing_directories():
    try:
        # Load current ingestion state
        with open('drive_e_ingestion_state.json', 'r', encoding='utf-8') as f:
            ingestion_state = json.load(f)
        print(f"Loaded ingestion state for {len(ingestion_state)} directories")
        
        # Find directories in processing state
        processing_dirs = []
        for directory, state in ingestion_state.items():
            if state['status'] == 'processing':
                processing_dirs.append(directory)
                print(f"Found processing directory: {directory}")
        
        print(f"\nFound {len(processing_dirs)} directories in processing state")
        
        if processing_dirs:
            # Reset them to pending
            for directory in processing_dirs:
                ingestion_state[directory]['status'] = 'pending'
                ingestion_state[directory]['last_error'] = "Reset from processing state"
                print(f"Reset to pending: {directory}")
            
            # Save updated state
            with open('drive_e_ingestion_state.json', 'w', encoding='utf-8') as f:
                json.dump(ingestion_state, f, indent=2, ensure_ascii=False)
            print(f"\nReset {len(processing_dirs)} directories to pending status")
        else:
            print("No directories found in processing state")
        
        # Show final status summary
        status_counts = {}
        for state in ingestion_state.values():
            status = state['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"\nFinal status summary:")
        for status, count in status_counts.items():
            print(f"  {status}: {count}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    reset_processing_directories()
