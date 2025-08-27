#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Video Processing

Test video keyframe extraction on a single video to diagnose issues.
"""

import requests
import json
import sys
import time
from pathlib import Path

# Ensure UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def test_video_processing():
    """Test video processing on a recent video asset."""
    print("🔍 Testing Video Processing")
    print("=" * 40)
    
    try:
        # Get a recent video asset
        response = requests.get("http://localhost:8000/assets?limit=5&sort=id&order=desc")
        if response.status_code == 200:
            assets = response.json().get('assets', [])
            
            # Find a video asset
            video_extensions = {'.mp4', '.mov', '.mkv', '.avi', '.m4v', '.webm'}
            video_asset = None
            
            for asset in assets:
                path = asset.get('path', '')
                if Path(path).suffix.lower() in video_extensions:
                    video_asset = asset
                    break
            
            if not video_asset:
                print("❌ No video assets found in recent assets")
                return
            
            asset_id = video_asset['id']
            asset_path = video_asset['path']
            
            print(f"📹 Testing asset {asset_id}: {Path(asset_path).name}")
            print(f"📁 Full path: {asset_path}")
            print(f"📊 File size: {video_asset.get('file_size', 0):,} bytes")
            
            # Check if keyframes exist
            keyframe_dir = Path(f"backend/derived/video_frames/{asset_id}")
            if keyframe_dir.exists():
                keyframes = list(keyframe_dir.glob("frame_*.jpg"))
                print(f"✅ Keyframes found: {len(keyframes)} frames")
                for i, kf in enumerate(keyframes[:3]):
                    print(f"   📸 {kf.name} ({kf.stat().st_size:,} bytes)")
                if len(keyframes) > 3:
                    print(f"   ... and {len(keyframes) - 3} more")
            else:
                print(f"❌ No keyframe directory found: {keyframe_dir}")
            
            # Check video tasks for this asset
            print(f"\n🔍 Checking tasks for asset {asset_id}...")
            task_response = requests.get(f"http://localhost:8000/tasks?limit=20")
            if task_response.status_code == 200:
                all_tasks = task_response.json().get('tasks', [])
                video_tasks = []
                
                for task in all_tasks:
                    # Tasks don't directly reference asset IDs, but we can check for recent video tasks
                    if task.get('type', '').startswith('video'):
                        video_tasks.append(task)
                
                print(f"📋 Recent video tasks:")
                for task in video_tasks[:5]:
                    print(f"   {task.get('type')} (ID: {task.get('id')}) - {task.get('state')}")
            
            # Check if file exists and is accessible
            if Path(asset_path).exists():
                file_size = Path(asset_path).stat().st_size
                print(f"✅ Video file exists ({file_size:,} bytes)")
            else:
                print(f"❌ Video file not found: {asset_path}")
                
        else:
            print(f"❌ Failed to get assets: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing video processing: {e}")

if __name__ == "__main__":
    test_video_processing()
