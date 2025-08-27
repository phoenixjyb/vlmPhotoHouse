#!/usr/bin/env python3
"""
Smart E: Drive Photo Processor
Processes photos on E: drive with resume capability and progress tracking.
Respects existing directory structure with in-place processing.
"""

import os
import sys
import json
import time
import pickle
import argparse
import requests
from pathlib import Path
from typing import Dict, List, Set, Optional
from datetime import datetime


class SmartEdriveProcessor:
    """Smart processor for E: drive photos with resume capability."""
    
    def __init__(self, base_url: str = "http://localhost:8002"):
        self.base_url = base_url
        self.progress_file = "edrive_processing_progress.json"
        self.cache_file = "processed_directories.pkl"
        
        # E: drive directory structure
        self.edrive_directories = {
            "E:\\01_INCOMING": "New photos awaiting processing",
            "E:\\02_PROCESSING": "Photos currently being processed", 
            "E:\\03_ARCHIVE": "Processed and archived photos",
            "E:\\04_EVENTS": "Event-based photo collections",
            "E:\\05_PEOPLE": "People-focused photo collections",
            "E:\\06_FAVORITES": "Curated favorite photos",
            "E:\\07_RAW": "Raw camera files",
            "E:\\08_BACKUP": "Backup copies",
            "E:\\VLM_DATA": "AI processing data and embeddings"
        }
        
        self.progress = self.load_progress()
        self.processed_dirs = self.load_processed_cache()
        
    def load_progress(self) -> Dict:
        """Load processing progress from file."""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load progress file: {e}")
        
        return {
            "started_at": None,
            "last_update": None,
            "directories_processed": [],
            "directories_failed": [],
            "total_files_processed": 0,
            "current_directory": None,
            "status": "not_started"
        }
    
    def save_progress(self):
        """Save current progress to file."""
        self.progress["last_update"] = datetime.now().isoformat()
        try:
            with open(self.progress_file, 'w') as f:
                json.dump(self.progress, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save progress: {e}")
    
    def load_processed_cache(self) -> Set[str]:
        """Load cache of already processed directories."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                print(f"Warning: Could not load processed cache: {e}")
        return set()
    
    def save_processed_cache(self):
        """Save cache of processed directories."""
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.processed_dirs, f)
        except Exception as e:
            print(f"Warning: Could not save processed cache: {e}")
    
    def check_vlm_health(self) -> bool:
        """Check if VLM service is running and healthy."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            if response.status_code == 200:
                health = response.json()
                print(f"✅ VLM Service is healthy")
                print(f"   - API Version: {health.get('api_version', 'Unknown')}")
                print(f"   - Database: {'✅' if health.get('db_ok') else '❌'}")
                print(f"   - Profile: {health.get('profile', 'Unknown')}")
                print(f"   - Face Provider: {health.get('face', {}).get('embed_provider', 'Unknown')}")
                print(f"   - Caption Provider: {health.get('caption', {}).get('provider', 'Unknown')}")
                print(f"   - Device: {health.get('caption', {}).get('device', 'Unknown')}")
                return True
            else:
                print(f"❌ VLM Service health check failed: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Could not connect to VLM service: {e}")
            return False
    
    def get_photo_files(self, directory: str) -> List[str]:
        """Get list of photo/video files in directory."""
        photo_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp',
                          '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm'}
        
        files = []
        try:
            for root, dirs, filenames in os.walk(directory):
                for filename in filenames:
                    if Path(filename).suffix.lower() in photo_extensions:
                        files.append(os.path.join(root, filename))
        except Exception as e:
            print(f"Error scanning directory {directory}: {e}")
        
        return files
    
    def ingest_directory(self, directory: str) -> bool:
        """Ingest a directory via VLM API."""
        try:
            print(f"🔄 Ingesting directory: {directory}")
            
            # Use the /ingest/scan endpoint
            response = requests.post(
                f"{self.base_url}/ingest/scan",
                json={"path": directory},
                timeout=300  # 5 minute timeout for large directories
            )
            
            if response.status_code == 200:
                result = response.json()
                task_id = result.get('task_id')
                
                if task_id:
                    print(f"✅ Ingestion started, task ID: {task_id}")
                    success = self.monitor_task_progress(task_id)
                    
                    if success:
                        self.processed_dirs.add(directory)
                        self.progress["directories_processed"].append(directory)
                        print(f"✅ Successfully processed: {directory}")
                        return True
                    else:
                        self.progress["directories_failed"].append(directory)
                        print(f"❌ Failed to process: {directory}")
                        return False
                else:
                    print(f"❌ No task ID returned for {directory}")
                    return False
            else:
                print(f"❌ Ingestion failed: HTTP {response.status_code}")
                if response.text:
                    print(f"   Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error ingesting {directory}: {e}")
            self.progress["directories_failed"].append(directory)
            return False
    
    def monitor_task_progress(self, task_id: str) -> bool:
        """Monitor task progress until completion."""
        print(f"📊 Monitoring task {task_id}...")
        
        while True:
            try:
                response = requests.get(f"{self.base_url}/tasks/{task_id}")
                
                if response.status_code == 200:
                    task = response.json()
                    status = task.get('status', 'unknown')
                    progress = task.get('progress', 0)
                    
                    print(f"   Status: {status}, Progress: {progress}%", end='\r')
                    
                    if status == 'completed':
                        print(f"\n✅ Task {task_id} completed successfully")
                        return True
                    elif status == 'failed':
                        print(f"\n❌ Task {task_id} failed")
                        error = task.get('error', 'Unknown error')
                        print(f"   Error: {error}")
                        return False
                    elif status in ['pending', 'running']:
                        time.sleep(2)  # Wait 2 seconds before checking again
                    else:
                        print(f"\n⚠️ Unknown task status: {status}")
                        time.sleep(5)
                else:
                    print(f"\n❌ Could not check task status: HTTP {response.status_code}")
                    return False
                    
            except Exception as e:
                print(f"\n❌ Error monitoring task: {e}")
                return False
    
    def process_directory(self, directory: str, skip_processed: bool = True) -> bool:
        if skip_processed and directory in self.processed_dirs:
            print(f"⏭️ Skipping already processed: {directory}")
            return True
        
        if not os.path.exists(directory):
            print(f"⚠️ Directory does not exist: {directory}")
            return False
        
        files = self.get_photo_files(directory)
        if not files:
            print(f"📁 No photo/video files found in: {directory}")
            return True
        
        print(f"📁 Found {len(files)} files in {directory}")
        self.progress["current_directory"] = directory
        self.progress["status"] = "processing"
        self.save_progress()
        success = self.ingest_directory(directory)
        if success:
            self.progress["total_files_processed"] += len(files)
            self.save_processed_cache()
        self.save_progress()
        return success
    
    def process_all_directories(self, skip_processed: bool = True, target_dirs: List[str] = None):
        if not self.check_vlm_health():
            print("❌ VLM service is not available. Cannot proceed.")
            return
        if self.progress["status"] == "not_started":
            self.progress["started_at"] = datetime.now().isoformat()
            self.progress["status"] = "running"
            self.save_progress()
        if target_dirs:
            directories = target_dirs
        else:
            directories = [d for d in self.edrive_directories.keys() if os.path.exists(d)]
        print(f"🚀 Starting Smart E: Drive Processing")
        print(f"📊 Found {len(directories)} directories to process")
        if skip_processed:
            print(f"⏭️ Will skip {len(self.processed_dirs)} already processed directories")
        processed_count = 0
        failed_count = 0
        for i, directory in enumerate(directories, 1):
            print(f"\n{'='*60}")
            print(f"Processing {i}/{len(directories)}: {directory}")
            print(f"Purpose: {self.edrive_directories.get(directory, 'Custom directory')}")
            print(f"{'='*60}")
            try:
                success = self.process_directory(directory, skip_processed)
                if success:
                    processed_count += 1
                else:
                    failed_count += 1
            except KeyboardInterrupt:
                print(f"\n⚠️ Processing interrupted by user")
                print(f"📊 Progress saved. You can resume later with the same command.")
                self.progress["status"] = "interrupted"
                self.save_progress()
                break
            except Exception as e:
                print(f"❌ Unexpected error processing {directory}: {e}")
                failed_count += 1
                continue
        print(f"\n{'='*60}")
        print(f"🎯 Processing Complete!")
        print(f"✅ Successfully processed: {processed_count} directories")
        print(f"❌ Failed: {failed_count} directories")
        print(f"📊 Total files processed: {self.progress['total_files_processed']}")
        print(f"{'='*60}")
        self.progress["status"] = "completed"
        self.save_progress()
    
    def show_status(self):
        print(f"Smart E: Drive Processor Status")
        print(f"{'='*40}")
        print(f"Status: {self.progress['status']}")
        print(f"Started: {self.progress['started_at']}")
        print(f"Last Update: {self.progress['last_update']}")
        print(f"Total Files Processed: {self.progress['total_files_processed']}")
        print(f"Directories Processed: {len(self.progress['directories_processed'])}")
        print(f"Directories Failed: {len(self.progress['directories_failed'])}")
        if self.progress['current_directory']:
            print(f"Current Directory: {self.progress['current_directory']}")
        print(f"\nProcessed Directories:")
        for d in self.progress['directories_processed']:
            print(f"  ✅ {d}")
        if self.progress['directories_failed']:
            print(f"\nFailed Directories:")
            for d in self.progress['directories_failed']:
                print(f"  ❌ {d}")


def main():
    parser = argparse.ArgumentParser(description='Smart E: Drive Photo Processor')
    parser.add_argument('--status', action='store_true', help='Show processing status')
    parser.add_argument('--reset', action='store_true', help='Reset progress and start fresh')
    parser.add_argument('--directory', '-d', help='Process specific directory only')
    parser.add_argument('--no-skip', action='store_true', help='Don\'t skip already processed directories')
    parser.add_argument('--url', default='http://localhost:8002', help='VLM service URL')
    args = parser.parse_args()
    processor = SmartEdriveProcessor(base_url=args.url)
    if args.status:
        processor.show_status()
        return
    if args.reset:
        if os.path.exists(processor.progress_file):
            os.remove(processor.progress_file)
            print("✅ Progress reset")
        if os.path.exists(processor.cache_file):
            os.remove(processor.cache_file)
            print("✅ Cache reset")
        return
    if args.directory:
        if not os.path.exists(args.directory):
            print(f"❌ Directory does not exist: {args.directory}")
            sys.exit(1)
        target_dirs = [args.directory]
    else:
        target_dirs = None
    skip_processed = not args.no_skip
    processor.process_all_directories(skip_processed=skip_processed, target_dirs=target_dirs)


if __name__ == "__main__":
    main()
