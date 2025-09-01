#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Count Video Assets and Check Keyframes

Verify how many video assets are actually in the backend and check keyframe generation.
"""

import requests
import json
import sys
from pathlib import Path

# Ensure UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def count_video_assets():
    """Count video assets in the backend."""
    video_extensions = {'.mp4', '.mov', '.mkv', '.avi', '.m4v', '.webm'}
    video_count = 0
    page = 1
    page_size = 1000
    
    print("Counting video assets in backend...")
    
    while True:
        try:
            response = requests.get(
                f"http://localhost:8000/assets?page={page}&limit={page_size}&sort=id&order=asc", 
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"Error: HTTP {response.status_code}")
                break
                
            data = response.json()
            assets = data.get('assets', [])
            
            if not assets:
                break
                
            # Count videos in this page
            page_videos = 0
            for asset in assets:
                asset_path = asset.get('path', '')
                if Path(asset_path).suffix.lower() in video_extensions:
                    page_videos += 1
                    video_count += 1
            
            print(f"Page {page}: {page_videos} videos found ({len(assets)} total assets)")
            
            # Check if this is the last page
            if len(assets) < page_size:
                break
                
            page += 1
            
        except Exception as e:
            print(f"Error on page {page}: {e}")
            break
    
    return video_count

def check_keyframes_sample():
    """Check if keyframes exist for a sample of video assets."""
    print("\nChecking keyframe generation for sample videos...")
    
    # Get a few recent video assets
    try:
        response = requests.get("http://localhost:8000/assets?limit=10&sort=id&order=desc")
        if response.status_code == 200:
            data = response.json()
            assets = data.get('assets', [])
            
            video_extensions = {'.mp4', '.mov', '.mkv', '.avi', '.m4v', '.webm'}
            video_assets = [a for a in assets if Path(a.get('path', '')).suffix.lower() in video_extensions]
            
            print(f"Found {len(video_assets)} video assets in recent sample")
            
            keyframes_found = 0
            for asset in video_assets[:5]:  # Check first 5 videos
                asset_id = asset.get('id')
                keyframe_dir = f"backend/derived/video_frames/{asset_id}"
                
                if Path(keyframe_dir).exists():
                    keyframe_files = list(Path(keyframe_dir).glob("frame_*.jpg"))
                    if keyframe_files:
                        keyframes_found += 1
                        print(f"✅ Asset {asset_id}: {len(keyframe_files)} keyframes found")
                    else:
                        print(f"❌ Asset {asset_id}: No keyframes found")
                else:
                    print(f"❌ Asset {asset_id}: No keyframe directory")
            
            print(f"\nKeyframes generated for {keyframes_found}/{len(video_assets[:5])} sampled videos")
            
    except Exception as e:
        print(f"Error checking keyframes: {e}")

def main():
    print("🎬 Video Asset Verification Report")
    print("=" * 50)
    
    # Count video assets
    video_count = count_video_assets()
    print(f"\n📊 Total video assets in backend: {video_count}")
    print(f"📊 Expected video files from Drive E: 2357")
    print(f"📊 Difference: {2357 - video_count}")
    
    if video_count == 2357:
        print("✅ All videos successfully ingested!")
    elif video_count < 2357:
        print(f"⚠️  Missing {2357 - video_count} videos")
    else:
        print(f"❓ More videos than expected (+{video_count - 2357})")
    
    # Check keyframes
    check_keyframes_sample()

if __name__ == "__main__":
    main()
