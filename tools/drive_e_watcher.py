#!/usr/bin/env python3
"""
Drive E File Watcher Service

Automatically detects new files added to Drive E (especially 01_INCOMING folder)
and triggers processing. Runs as a background service.
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Set, Dict, List
import threading
import queue
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
import argparse

# Configuration
DRIVE_E_ROOT = Path("E:/")
INCOMING_FOLDER = "01_INCOMING"
WATCH_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.webp', '.tiff', '.bmp', '.gif', 
                   '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v'}
PROCESSING_SCRIPT = "tools/drive_e_processor_v2.py"
SETTLE_TIME = 30  # seconds to wait for file to finish copying
BATCH_SIZE = 10
BATCH_TIMEOUT = 300  # 5 minutes

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('drive_e_watcher.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class FileWatcherHandler(FileSystemEventHandler):
    """Handle file system events."""
    
    def __init__(self, file_queue: queue.Queue):
        super().__init__()
        self.file_queue = file_queue
        self.pending_files: Dict[str, datetime] = {}
        self.lock = threading.Lock()
    
    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory:
            self._handle_file_event(event.src_path, "created")
    
    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory:
            self._handle_file_event(event.src_path, "modified")
    
    def _handle_file_event(self, file_path: str, event_type: str):
        """Handle file events with debouncing."""
        file_path = Path(file_path)
        
        # Check if it's a supported file type
        if file_path.suffix.lower() not in WATCH_EXTENSIONS:
            return
        
        # Ignore temporary files
        if file_path.name.startswith('.') or file_path.name.startswith('~'):
            return
        
        logger.info(f"📁 File {event_type}: {file_path}")
        
        with self.lock:
            # Add to pending files with current timestamp
            self.pending_files[str(file_path)] = datetime.now()
    
    def get_settled_files(self) -> List[str]:
        """Get files that have settled (no changes for SETTLE_TIME)."""
        settled_files = []
        current_time = datetime.now()
        
        with self.lock:
            files_to_remove = []
            
            for file_path, last_modified in self.pending_files.items():
                if current_time - last_modified > timedelta(seconds=SETTLE_TIME):
                    # Check if file still exists and is readable
                    if Path(file_path).exists():
                        try:
                            # Try to open file to ensure it's not being written to
                            with open(file_path, 'rb') as f:
                                f.read(1)
                            settled_files.append(file_path)
                            files_to_remove.append(file_path)
                            logger.info(f"✅ File settled: {file_path}")
                        except (IOError, OSError):
                            # File still being written to
                            logger.debug(f"⏳ File still being written: {file_path}")
                    else:
                        # File was deleted, remove from pending
                        files_to_remove.append(file_path)
                        logger.debug(f"🗑️ File removed: {file_path}")
            
            # Remove settled files from pending
            for file_path in files_to_remove:
                del self.pending_files[file_path]
        
        return settled_files

class DriveEWatcher:
    """Main file watcher service."""
    
    def __init__(self, drive_root: Path = DRIVE_E_ROOT):
        self.drive_root = drive_root
        self.file_queue = queue.Queue()
        self.observer = None
        self.handler = None
        self.processing_thread = None
        self.running = False
        
        # Stats
        self.files_detected = 0
        self.files_processed = 0
        self.processing_errors = 0
        self.start_time = datetime.now()
    
    def start(self):
        """Start the file watcher service."""
        logger.info(f"🚀 Starting Drive E File Watcher")
        logger.info(f"📁 Watching: {self.drive_root}")
        logger.info(f"🎯 Priority folder: {INCOMING_FOLDER}")
        logger.info(f"⏱️ Settle time: {SETTLE_TIME}s")
        logger.info(f"📦 Batch size: {BATCH_SIZE}")
        
        self.running = True
        
        # Create file system observer
        self.observer = Observer()
        self.handler = FileWatcherHandler(self.file_queue)
        
        # Watch the entire drive, but prioritize incoming folder
        self.observer.schedule(self.handler, str(self.drive_root), recursive=True)
        
        # Start observer
        self.observer.start()
        logger.info("👁️ File system observer started")
        
        # Start processing thread
        self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.processing_thread.start()
        logger.info("⚙️ Processing thread started")
        
        logger.info("✅ Drive E File Watcher is running")
    
    def stop(self):
        """Stop the file watcher service."""
        logger.info("🛑 Stopping Drive E File Watcher")
        
        self.running = False
        
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        if self.processing_thread:
            self.processing_thread.join(timeout=5)
        
        logger.info("✅ Drive E File Watcher stopped")
    
    def _processing_loop(self):
        """Main processing loop that runs in a separate thread."""
        batch = []
        last_batch_time = datetime.now()
        
        while self.running:
            try:
                # Check for settled files
                if self.handler:
                    settled_files = self.handler.get_settled_files()
                    
                    for file_path in settled_files:
                        batch.append(file_path)
                        self.files_detected += 1
                        logger.info(f"📝 Added to batch: {file_path}")
                
                # Process batch if it's full or timeout reached
                current_time = datetime.now()
                should_process = (
                    len(batch) >= BATCH_SIZE or 
                    (batch and (current_time - last_batch_time).total_seconds() > BATCH_TIMEOUT)
                )
                
                if should_process:
                    logger.info(f"🔄 Processing batch of {len(batch)} files")
                    success = self._process_batch(batch)
                    
                    if success:
                        self.files_processed += len(batch)
                        logger.info(f"✅ Batch processed successfully")
                    else:
                        self.processing_errors += 1
                        logger.error(f"❌ Batch processing failed")
                    
                    # Reset batch
                    batch = []
                    last_batch_time = current_time
                
                # Sleep briefly to avoid busy waiting
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                time.sleep(5)
    
    def _process_batch(self, file_paths: List[str]) -> bool:
        """Process a batch of files using the Drive E processor."""
        try:
            # Create a temporary file list
            temp_file = Path("temp_batch_files.txt")
            with open(temp_file, 'w') as f:
                for file_path in file_paths:
                    f.write(f"{file_path}\n")
            
            # Build command
            cmd = [
                sys.executable,
                PROCESSING_SCRIPT,
                "--focus-incoming",
                "--workers", "2",  # Conservative for background processing
                "--batch-size", str(min(len(file_paths), 5)),
                "--max-files", str(len(file_paths))
            ]
            
            logger.info(f"🔧 Running: {' '.join(cmd)}")
            
            # Execute processing
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()
            
            if result.returncode == 0:
                logger.info("✅ Processing completed successfully")
                logger.debug(f"Output: {result.stdout}")
                return True
            else:
                logger.error(f"❌ Processing failed with code {result.returncode}")
                logger.error(f"Error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("❌ Processing timed out")
            return False
        except Exception as e:
            logger.error(f"❌ Error running processing: {e}")
            return False
    
    def get_stats(self) -> Dict:
        """Get watcher statistics."""
        runtime = datetime.now() - self.start_time
        
        return {
            'start_time': self.start_time.isoformat(),
            'runtime_seconds': runtime.total_seconds(),
            'files_detected': self.files_detected,
            'files_processed': self.files_processed,
            'processing_errors': self.processing_errors,
            'pending_files': len(self.handler.pending_files) if self.handler else 0,
            'is_running': self.running
        }
    
    def print_stats(self):
        """Print current statistics."""
        stats = self.get_stats()
        
        print("=" * 50)
        print("Drive E File Watcher Statistics")
        print("=" * 50)
        print(f"Status: {'Running' if stats['is_running'] else 'Stopped'}")
        print(f"Runtime: {timedelta(seconds=int(stats['runtime_seconds']))}")
        print(f"Files detected: {stats['files_detected']}")
        print(f"Files processed: {stats['files_processed']}")
        print(f"Processing errors: {stats['processing_errors']}")
        print(f"Pending files: {stats['pending_files']}")
        
        if stats['files_detected'] > 0:
            success_rate = (stats['files_processed'] / stats['files_detected']) * 100
            print(f"Success rate: {success_rate:.1f}%")
        
        print("=" * 50)

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Drive E File Watcher Service")
    parser.add_argument("--drive-root", "-d", default="E:/", help="Drive E root path")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--stats-interval", type=int, default=300, 
                       help="Stats logging interval in seconds")
    
    args = parser.parse_args()
    
    # Create watcher
    watcher = DriveEWatcher(drive_root=Path(args.drive_root))
    
    try:
        # Start watcher
        watcher.start()
        
        # Stats logging timer
        last_stats_time = datetime.now()
        
        if args.daemon:
            # Run indefinitely
            logger.info("🔄 Running in daemon mode (Ctrl+C to stop)")
            while True:
                time.sleep(10)
                
                # Log stats periodically
                if (datetime.now() - last_stats_time).total_seconds() > args.stats_interval:
                    watcher.print_stats()
                    last_stats_time = datetime.now()
        else:
            # Interactive mode
            print("\nDrive E File Watcher is running...")
            print("Commands:")
            print("  'stats' - Show statistics")
            print("  'quit' - Stop and exit")
            print()
            
            while True:
                try:
                    command = input("> ").strip().lower()
                    
                    if command == 'quit':
                        break
                    elif command == 'stats':
                        watcher.print_stats()
                    elif command == '':
                        continue
                    else:
                        print("Unknown command. Use 'stats' or 'quit'.")
                        
                except EOFError:
                    break
    
    except KeyboardInterrupt:
        logger.info("🛑 Received interrupt signal")
    
    finally:
        watcher.stop()
        logger.info("👋 Goodbye!")

if __name__ == "__main__":
    main()
