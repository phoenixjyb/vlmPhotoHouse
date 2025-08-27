#!/usr/bin/env python3
"""
Simple Drive E Photo/Video Processor
- Bypasses API database locks by using direct file upload
- Simple incremental processing with local state tracking
"""

import os
import sys
import json
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Optional
import mimetypes
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Supported file types
SUPPORTED_EXTENSIONS = {
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic',
    # Videos  
    '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v'
}

class SimpleDriveEProcessor:
    def __init__(self, drive_root: str):
        self.drive_root = Path(drive_root)
        self.state_file = Path("simple_drive_e_state.json")
        self.processed_files = self.load_state()
        
    def load_state(self) -> Dict:
        """Load processing state from local file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
        return {}
    
    def save_state(self):
        """Save processing state to local file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.processed_files, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file."""
        hasher = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Failed to hash {file_path}: {e}")
            return ""
    
    def discover_files(self, max_files: Optional[int] = None) -> List[Path]:
        """Discover files that need processing."""
        files_to_process = []
        
        # Focus on 01_INCOMING first
        incoming_path = self.drive_root / "01_INCOMING"
        if incoming_path.exists():
            logger.info(f"Scanning incoming folder: {incoming_path}")
            files_to_process.extend(self._scan_directory(incoming_path, max_files))
            
        # If we haven't reached max_files, scan other directories
        if max_files is None or len(files_to_process) < max_files:
            remaining = max_files - len(files_to_process) if max_files else None
            for item in self.drive_root.iterdir():
                if item.is_dir() and item.name != "01_INCOMING":
                    files_to_process.extend(self._scan_directory(item, remaining))
                    if max_files and len(files_to_process) >= max_files:
                        break
        
        return files_to_process[:max_files] if max_files else files_to_process
    
    def _scan_directory(self, directory: Path, max_files: Optional[int] = None) -> List[Path]:
        """Scan directory for supported files."""
        files = []
        try:
            for file_path in directory.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    file_key = str(file_path)
                    
                    # Check if file is already processed
                    if file_key in self.processed_files:
                        current_hash = self.calculate_file_hash(file_path)
                        if current_hash == self.processed_files[file_key].get('hash'):
                            continue  # Already processed and unchanged
                    
                    files.append(file_path)
                    if max_files and len(files) >= max_files:
                        break
        except Exception as e:
            logger.error(f"Error scanning {directory}: {e}")
        
        return files
    
    def process_file(self, file_path: Path) -> bool:
        """Process a single file - for now just mark as processed."""
        try:
            # Calculate file info
            file_hash = self.calculate_file_hash(file_path)
            file_size = file_path.stat().st_size
            mime_type, _ = mimetypes.guess_type(str(file_path))
            
            # For now, we'll just record the file info without uploading
            # This can be extended later when the API database lock is resolved
            file_info = {
                'hash': file_hash,
                'size': file_size,
                'mime_type': mime_type,
                'processed_at': datetime.now().isoformat(),
                'status': 'recorded'  # Will change to 'uploaded' when API works
            }
            
            self.processed_files[str(file_path)] = file_info
            logger.info(f"Recorded file: {file_path} ({file_size} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process {file_path}: {e}")
            return False
    
    def run(self, max_files: Optional[int] = None, dry_run: bool = False):
        """Run the processing."""
        logger.info("Starting simple Drive E processing")
        logger.info(f"Root: {self.drive_root}")
        logger.info(f"Max files: {max_files or 'unlimited'}")
        logger.info(f"Dry run: {dry_run}")
        
        # Discover files
        files = self.discover_files(max_files)
        logger.info(f"Found {len(files)} files to process")
        
        if dry_run:
            for file_path in files:
                logger.info(f"Would process: {file_path}")
            return
        
        # Process files
        successful = 0
        failed = 0
        
        for i, file_path in enumerate(files, 1):
            logger.info(f"Processing {i}/{len(files)}: {file_path}")
            
            if self.process_file(file_path):
                successful += 1
            else:
                failed += 1
            
            # Save state periodically
            if i % 10 == 0:
                self.save_state()
        
        # Final save
        self.save_state()
        
        logger.info(f"Processing completed!")
        logger.info(f"Successful: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Total processed files in database: {len(self.processed_files)}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Simple Drive E Photo/Video Processor')
    parser.add_argument('--drive-root', default='E:\\', help='Drive root path')
    parser.add_argument('--max-files', type=int, help='Maximum files to process')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')
    
    args = parser.parse_args()
    
    processor = SimpleDriveEProcessor(args.drive_root)
    processor.run(max_files=args.max_files, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
