#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video Ingestion Progress Monitor

Monitor the progress of video ingestion in real-time.
"""

import requests
import json
import time
import sys
from datetime import datetime

# Ensure UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def get_backend_status():
    """Get current backend status."""
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error getting backend status: {e}")
    return None

def get_recent_assets(limit=5):
    """Get most recently ingested assets."""
    try:
        response = requests.get(f"http://localhost:8000/assets?limit={limit}&sort=id&order=desc", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('assets', []), data.get('total', 0)
    except Exception as e:
        print(f"Error getting recent assets: {e}")
    return [], 0

def monitor_progress():
    """Monitor video ingestion progress."""
    print("🎬 Video Ingestion Progress Monitor")
    print("=" * 50)
    
    start_time = datetime.now()
    last_total = 0
    
    while True:
        try:
            # Get current status
            status = get_backend_status()
            assets, total_assets = get_recent_assets(3)
            
            current_time = datetime.now()
            elapsed = current_time - start_time
            
            if status:
                print(f"\n⏰ {current_time.strftime('%H:%M:%S')} | Elapsed: {str(elapsed).split('.')[0]}")
                print(f"📊 Total Assets: {total_assets} | Index Size: {status.get('index', {}).get('size', 'N/A')}")
                print(f"📋 Pending Tasks: {status.get('pending_tasks', 'N/A')} | Running: {status.get('running_tasks', 'N/A')}")
                
                # Show new assets added
                new_assets = total_assets - last_total
                if new_assets > 0:
                    print(f"🆕 New assets since last check: {new_assets}")
                
                # Show recent video assets
                video_assets = [a for a in assets if a.get('path', '').lower().endswith(('.mp4', '.mov', '.mkv', '.avi', '.m4v', '.webm'))]
                if video_assets:
                    print(f"🎬 Recent video assets:")
                    for asset in video_assets[:2]:
                        filename = asset.get('path', '').split('\\')[-1]
                        size_mb = round(asset.get('file_size', 0) / (1024*1024), 1)
                        print(f"   • {filename} ({size_mb} MB)")
                
                last_total = total_assets
            
            print("-" * 50)
            time.sleep(30)  # Check every 30 seconds
            
        except KeyboardInterrupt:
            print("\n👋 Monitoring stopped by user")
            break
        except Exception as e:
            print(f"❌ Error during monitoring: {e}")
            time.sleep(10)

if __name__ == "__main__":
    monitor_progress()
