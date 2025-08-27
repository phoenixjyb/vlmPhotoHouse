#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video Processing Progress Monitor

Real-time monitoring of video keyframe extraction and processing.
"""

import requests
import json
import time
import sys
from datetime import datetime
from pathlib import Path

# Ensure UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def get_task_stats():
    """Get video task statistics."""
    try:
        # Get video keyframe task counts
        pending_resp = requests.get("http://localhost:8000/tasks?type=video_keyframes&state=pending&limit=1", timeout=5)
        running_resp = requests.get("http://localhost:8000/tasks?type=video_keyframes&state=running&limit=1", timeout=5)
        done_resp = requests.get("http://localhost:8000/tasks?type=video_keyframes&state=done&limit=1", timeout=5)
        
        if all(r.status_code == 200 for r in [pending_resp, running_resp, done_resp]):
            pending_count = pending_resp.json().get('total', 0)
            running_count = running_resp.json().get('total', 0)
            done_count = done_resp.json().get('total', 0)
            
            return pending_count, running_count, done_count
    except Exception as e:
        print(f"Error getting task stats: {e}")
    
    return None, None, None

def count_keyframe_directories():
    """Count how many video assets have keyframe directories."""
    keyframes_dir = Path("backend/derived/video_frames")
    if keyframes_dir.exists():
        return len(list(keyframes_dir.iterdir()))
    return 0

def get_backend_health():
    """Get backend health info."""
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

def monitor_video_processing():
    """Monitor video processing progress."""
    print("🎬 Video Processing Progress Monitor")
    print("=" * 60)
    
    start_time = datetime.now()
    last_done_count = 0
    
    while True:
        try:
            current_time = datetime.now()
            elapsed = current_time - start_time
            
            # Get task statistics
            pending, running, done = get_task_stats()
            keyframe_dirs = count_keyframe_directories()
            health = get_backend_health()
            
            print(f"\n⏰ {current_time.strftime('%H:%M:%S')} | Elapsed: {str(elapsed).split('.')[0]}")
            print("-" * 60)
            
            if pending is not None:
                total_tasks = pending + running + done
                completion_pct = (done / total_tasks * 100) if total_tasks > 0 else 0
                
                print(f"📋 Video Keyframe Tasks:")
                print(f"   ✅ Completed: {done:,}/{total_tasks:,} ({completion_pct:.1f}%)")
                print(f"   🔄 Running:   {running:,}")
                print(f"   ⏳ Pending:   {pending:,}")
                
                # Calculate processing rate
                new_completed = done - last_done_count
                if new_completed > 0:
                    print(f"   🚀 Just completed: {new_completed} tasks")
                
                last_done_count = done
                
            if keyframe_dirs > 0:
                print(f"📂 Videos with keyframes: {keyframe_dirs:,}")
                
            if health:
                print(f"🖥️  Backend: {health.get('pending_tasks', 'N/A'):,} pending total | {health.get('running_tasks', 'N/A')} running")
                
            # Show completion estimate
            if pending is not None and done > 0 and elapsed.total_seconds() > 60:
                rate_per_minute = done / (elapsed.total_seconds() / 60)
                if rate_per_minute > 0:
                    remaining_minutes = pending / rate_per_minute
                    from datetime import timedelta
                    eta = current_time + timedelta(minutes=remaining_minutes)
                    print(f"⏱️  Processing rate: {rate_per_minute:.1f} tasks/min")
                    print(f"🎯 ETA for completion: {eta.strftime('%H:%M:%S')}")
            
            print("=" * 60)
            time.sleep(30)  # Check every 30 seconds
            
        except KeyboardInterrupt:
            print("\n👋 Monitoring stopped by user")
            break
        except Exception as e:
            print(f"❌ Error during monitoring: {e}")
            time.sleep(10)

if __name__ == "__main__":
    monitor_video_processing()
