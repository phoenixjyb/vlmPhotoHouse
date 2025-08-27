#!/usr/bin/env python3
"""
Drive E Photo and Video Processing Script with Incremental Processing

Enhanced script with:
- Bookkeeping and checkpoint system
- Incremental processing (only new/changed files)
- Processing history and state management
- File watching for automatic processing
- Robust error handling and recovery

Integrates with running vlmPhotoHouse services.
"""

import os
import sys
import json
import time
import requests
import hashlib
import mimetypes
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime, timedelta
import argparse
import logging
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import exifread
from PIL import Image, ExifTags
import sqlite3
import threading
from collections import defaultdict
import uuid

# Configuration
DRIVE_E_ROOT = Path("E:/")
INCOMING_FOLDER = "01_INCOMING"
API_BASE_URL = "http://127.0.0.1:8002"
VOICE_BASE_URL = "http://127.0.0.1:8001"
MAX_WORKERS = 4
BATCH_SIZE = 100
CHECKPOINT_DB = "drive_e_processing.db"

# Supported file types
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.webp', '.tiff', '.bmp', '.gif'}
SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v'}
SUPPORTED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac'}

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('drive_e_processing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class ProcessingResult:
    """Result of processing a single file."""
    file_path: str
    success: bool
    error: Optional[str] = None
    caption: Optional[str] = None
    faces_detected: int = 0
    asset_id: Optional[int] = None
    processing_time: float = 0.0
    metadata: Dict = None
    session_id: Optional[str] = None

@dataclass
class FileState:
    """State of a file in the processing system."""
    file_path: str
    file_hash: str
    file_size: int
    modified_time: datetime
    processing_status: str  # 'pending', 'processing', 'completed', 'failed', 'skipped'
    last_processed: Optional[datetime] = None
    error_count: int = 0
    asset_id: Optional[int] = None

class ProcessingDatabase:
    """Database for tracking processing state and history."""
    
    def __init__(self, db_path: str = CHECKPOINT_DB):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize the processing database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # File processing history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                modified_time TIMESTAMP NOT NULL,
                processing_status TEXT NOT NULL DEFAULT 'pending',
                last_processed TIMESTAMP,
                error_count INTEGER DEFAULT 0,
                asset_id INTEGER,
                session_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Processing sessions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_sessions (
                session_id TEXT PRIMARY KEY,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                total_files INTEGER DEFAULT 0,
                completed_files INTEGER DEFAULT 0,
                failed_files INTEGER DEFAULT 0,
                skipped_files INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running',
                config_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_path ON processing_history(file_path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_hash ON processing_history(file_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_status ON processing_history(processing_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_session ON processing_history(session_id)")
        
        conn.commit()
        conn.close()
    
    def get_file_state(self, file_path: str) -> Optional[FileState]:
        """Get the processing state of a file."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT file_path, file_hash, file_size, modified_time, processing_status, 
                   last_processed, error_count, asset_id
            FROM processing_history WHERE file_path = ?
        """, (str(file_path),))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return FileState(
                file_path=row[0],
                file_hash=row[1], 
                file_size=row[2],
                modified_time=datetime.fromisoformat(row[3]),
                processing_status=row[4],
                last_processed=datetime.fromisoformat(row[5]) if row[5] else None,
                error_count=row[6],
                asset_id=row[7]
            )
        return None
    
    def update_file_state(self, file_state: FileState, session_id: str = None):
        """Update or insert file state."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO processing_history 
            (file_path, file_hash, file_size, modified_time, processing_status, 
             last_processed, error_count, asset_id, session_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            file_state.file_path,
            file_state.file_hash,
            file_state.file_size,
            file_state.modified_time.isoformat(),
            file_state.processing_status,
            file_state.last_processed.isoformat() if file_state.last_processed else None,
            file_state.error_count,
            file_state.asset_id,
            session_id
        ))
        
        conn.commit()
        conn.close()
    
    def create_session(self, config: Dict = None) -> str:
        """Create a new processing session."""
        session_id = str(uuid.uuid4())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO processing_sessions (session_id, start_time, config_json)
            VALUES (?, CURRENT_TIMESTAMP, ?)
        """, (session_id, json.dumps(config) if config else None))
        
        conn.commit()
        conn.close()
        
        return session_id
    
    def update_session(self, session_id: str, **kwargs):
        """Update session statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        set_clauses = []
        values = []
        
        for key, value in kwargs.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)
        
        if set_clauses:
            query = f"UPDATE processing_sessions SET {', '.join(set_clauses)} WHERE session_id = ?"
            values.append(session_id)
            cursor.execute(query, values)
        
        conn.commit()
        conn.close()
    
    def get_pending_files(self, limit: int = None) -> List[str]:
        """Get files that need processing."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = """
            SELECT file_path FROM processing_history 
            WHERE processing_status IN ('pending', 'failed') 
            AND error_count < 3
            ORDER BY created_at
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query)
        files = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        return files
    
    def get_stats(self) -> Dict:
        """Get processing statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT processing_status, COUNT(*) 
            FROM processing_history 
            GROUP BY processing_status
        """)
        status_counts = dict(cursor.fetchall())
        
        cursor.execute("SELECT COUNT(*) FROM processing_history")
        total_files = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM processing_sessions WHERE status = 'running'
        """)
        active_sessions = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_files': total_files,
            'status_counts': status_counts,
            'active_sessions': active_sessions
        }

class IncrementalDriveEProcessor:
    """Enhanced Drive E processor with incremental processing and bookkeeping."""
    
    def __init__(self, drive_root: Path = DRIVE_E_ROOT, api_base: str = API_BASE_URL):
        self.drive_root = drive_root
        self.api_base = api_base
        self.voice_base = VOICE_BASE_URL
        self.session = requests.Session()
        self.db = ProcessingDatabase()
        self.current_session_id = None
        
        # State tracking
        self.processed_files: Set[str] = set()
        self.failed_files: Set[str] = set()
        self.skipped_files: Set[str] = set()
        
        # Verify services
        self._verify_services()
    
    def _verify_services(self):
        """Verify that required services are running."""
        try:
            response = self.session.get(f"{self.api_base}/health", timeout=5)
            if response.status_code != 200:
                raise ConnectionError(f"Main API not responding: {response.status_code}")
            
            logger.info("✅ Services verified")
            
        except Exception as e:
            logger.error(f"❌ Service verification failed: {e}")
            raise
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file."""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate hash for {file_path}: {e}")
            return ""
    
    def should_process_file(self, file_path: Path) -> Tuple[bool, str]:
        """Determine if a file should be processed."""
        try:
            # Check if file exists
            if not file_path.exists():
                return False, "File not found"
            
            # Get current file stats
            stat = file_path.stat()
            current_hash = self.calculate_file_hash(file_path)
            current_modified = datetime.fromtimestamp(stat.st_mtime)
            
            # Check database state
            file_state = self.db.get_file_state(str(file_path))
            
            if not file_state:
                # New file
                return True, "New file"
            
            # Check if file has changed
            if (file_state.file_hash != current_hash or 
                file_state.modified_time != current_modified):
                return True, "File modified"
            
            # Check processing status
            if file_state.processing_status == 'completed':
                return False, "Already processed"
            
            if file_state.processing_status == 'failed' and file_state.error_count >= 3:
                return False, "Too many failures"
            
            # Needs processing
            return True, f"Status: {file_state.processing_status}"
            
        except Exception as e:
            logger.error(f"Error checking file {file_path}: {e}")
            return False, f"Error: {e}"
    
    def discover_files_incremental(self, extensions: Set[str] = None, 
                                 focus_incoming: bool = True,
                                 max_files: int = None) -> List[Path]:
        """Discover files that need processing."""
        if extensions is None:
            extensions = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS
        
        files_to_process = []
        
        # Focus on incoming folder first
        if focus_incoming:
            incoming_path = self.drive_root / INCOMING_FOLDER
            if incoming_path.exists():
                logger.info(f"🔍 Prioritizing incoming folder: {incoming_path}")
                for ext in extensions:
                    pattern = f"**/*{ext}"
                    found = list(incoming_path.rglob(pattern))
                    
                    for file_path in found:
                        should_process, reason = self.should_process_file(file_path)
                        if should_process:
                            files_to_process.append(file_path)
                            logger.debug(f"📝 Queued: {file_path} ({reason})")
                        else:
                            self.skipped_files.add(str(file_path))
                            logger.debug(f"⏭️ Skipped: {file_path} ({reason})")
                        
                        if max_files and len(files_to_process) >= max_files:
                            break
                    
                    if max_files and len(files_to_process) >= max_files:
                        break
        
        # Process rest of drive if we have capacity
        if not max_files or len(files_to_process) < max_files:
            remaining_capacity = max_files - len(files_to_process) if max_files else None
            
            logger.info(f"🔍 Scanning remaining drive ({remaining_capacity or 'unlimited'} files)")
            
            for ext in extensions:
                pattern = f"**/*{ext}"
                found = list(self.drive_root.rglob(pattern))
                
                for file_path in found:
                    # Skip if already in incoming folder (already processed above)
                    if focus_incoming and INCOMING_FOLDER in str(file_path.relative_to(self.drive_root)):
                        continue
                    
                    should_process, reason = self.should_process_file(file_path)
                    if should_process:
                        files_to_process.append(file_path)
                        logger.debug(f"📝 Queued: {file_path} ({reason})")
                    else:
                        self.skipped_files.add(str(file_path))
                        logger.debug(f"⏭️ Skipped: {file_path} ({reason})")
                    
                    if remaining_capacity and len(files_to_process) >= max_files:
                        break
                
                if remaining_capacity and len(files_to_process) >= max_files:
                    break
        
        logger.info(f"📁 Files to process: {len(files_to_process)}")
        logger.info(f"⏭️ Files skipped: {len(self.skipped_files)}")
        
        return files_to_process
    
    def extract_metadata(self, file_path: Path) -> Dict:
        """Extract metadata from file."""
        metadata = {
            'file_size': file_path.stat().st_size,
            'modified_time': datetime.fromtimestamp(file_path.stat().st_mtime),
            'file_extension': file_path.suffix.lower(),
            'mime_type': mimetypes.guess_type(str(file_path))[0]
        }
        
        if file_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            metadata.update(self._extract_image_metadata(file_path))
        elif file_path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS:
            metadata.update(self._extract_video_metadata(file_path))
            
        return metadata
    
    def _extract_image_metadata(self, file_path: Path) -> Dict:
        """Extract image-specific metadata."""
        metadata = {}
        
        try:
            with Image.open(file_path) as img:
                metadata['width'] = img.width
                metadata['height'] = img.height
                metadata['format'] = img.format
                
                # EXIF data
                if hasattr(img, '_getexif') and img._getexif():
                    exif = img._getexif()
                    for tag_id, value in exif.items():
                        tag = ExifTags.TAGS.get(tag_id, tag_id)
                        if tag == 'DateTime':
                            try:
                                metadata['taken_at'] = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                            except:
                                pass
                        elif tag in ['Make', 'Model']:
                            metadata[f'camera_{tag.lower()}'] = str(value)[:64]
                            
        except Exception as e:
            logger.warning(f"Failed to extract image metadata for {file_path}: {e}")
            
        return metadata
    
    def _extract_video_metadata(self, file_path: Path) -> Dict:
        """Extract video-specific metadata."""
        metadata = {'is_video': True}
        # TODO: Add ffprobe integration
        return metadata
    
    def ingest_asset(self, file_path: Path, metadata: Dict) -> Optional[int]:
        """Ingest asset into the backend system via scan endpoint."""
        try:
            # Use the ingest/scan endpoint to register the file path
            scan_data = {
                'roots': [str(file_path.resolve())],
                'recursive': False
            }
            
            response = self.session.post(
                f"{self.api_base}/ingest/scan",
                json=scan_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                scanned_assets = result.get('scanned_assets', [])
                if scanned_assets:
                    asset_info = scanned_assets[0]
                    asset_id = asset_info.get('id')
                    if asset_id:
                        logger.info(f"✅ Asset ingested with ID: {asset_id}")
                        return asset_id
                    
                # If not found in scanned assets, try to get asset by path
                path_response = self.session.get(
                    f"{self.api_base}/assets/by-path",
                    params={'path': str(file_path.resolve())},
                    timeout=30
                )
                if path_response.status_code == 200:
                    asset = path_response.json()
                    asset_id = asset.get('id')
                    logger.info(f"📄 Asset found by path with ID: {asset_id}")
                    return asset_id
                else:
                    logger.warning(f"Asset scanned but ID not found for {file_path}")
                    return None
            else:
                logger.error(f"Failed to scan asset: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error ingesting asset {file_path}: {e}")
            return None
    
    def process_caption(self, file_path: Path, asset_id: int) -> Optional[str]:
        """Process caption for image/video."""
        if file_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            return None
            
        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                response = self.session.post(
                    f"{self.api_base}/caption/generate",
                    files=files,
                    data={'asset_id': asset_id},
                    timeout=60
                )
            
            if response.status_code == 200:
                result = response.json()
                caption = result.get('caption', '')
                logger.info(f"📝 Caption generated: {caption[:100]}...")
                return caption
            else:
                logger.warning(f"Caption generation failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating caption for {file_path}: {e}")
            return None
    
    def process_faces(self, file_path: Path, asset_id: int) -> int:
        """Process face detection and embedding."""
        if file_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            return 0
            
        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                response = self.session.post(
                    f"{self.api_base}/face/detect",
                    files=files,
                    data={'asset_id': asset_id},
                    timeout=60
                )
            
            if response.status_code == 200:
                result = response.json()
                faces_count = len(result.get('faces', []))
                logger.info(f"👤 Detected {faces_count} faces")
                return faces_count
            else:
                logger.warning(f"Face detection failed: {response.status_code}")
                return 0
                
        except Exception as e:
            logger.error(f"Error detecting faces for {file_path}: {e}")
            return 0
    
    def process_single_file(self, file_path: Path) -> ProcessingResult:
        """Process a single file through the entire pipeline."""
        start_time = time.time()
        
        try:
            logger.info(f"🔄 Processing: {file_path}")
            
            # Update file state to processing
            file_stat = file_path.stat()
            file_state = FileState(
                file_path=str(file_path),
                file_hash=self.calculate_file_hash(file_path),
                file_size=file_stat.st_size,
                modified_time=datetime.fromtimestamp(file_stat.st_mtime),
                processing_status='processing'
            )
            self.db.update_file_state(file_state, self.current_session_id)
            
            # Extract metadata
            metadata = self.extract_metadata(file_path)
            
            # Ingest asset
            asset_id = self.ingest_asset(file_path, metadata)
            if not asset_id:
                # Update state to failed
                file_state.processing_status = 'failed'
                file_state.error_count += 1
                self.db.update_file_state(file_state, self.current_session_id)
                
                return ProcessingResult(
                    file_path=str(file_path),
                    success=False,
                    error="Failed to ingest asset",
                    session_id=self.current_session_id
                )
            
            # Process caption (for images)
            caption = None
            if file_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                caption = self.process_caption(file_path, asset_id)
            
            # Process faces (for images)
            faces_count = 0
            if file_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                faces_count = self.process_faces(file_path, asset_id)
            
            processing_time = time.time() - start_time
            
            # Update state to completed
            file_state.processing_status = 'completed'
            file_state.last_processed = datetime.now()
            file_state.asset_id = asset_id
            self.db.update_file_state(file_state, self.current_session_id)
            
            return ProcessingResult(
                file_path=str(file_path),
                success=True,
                caption=caption,
                faces_detected=faces_count,
                asset_id=asset_id,
                processing_time=processing_time,
                metadata=metadata,
                session_id=self.current_session_id
            )
            
        except Exception as e:
            logger.error(f"❌ Error processing {file_path}: {e}")
            
            # Update state to failed
            try:
                existing_state = self.db.get_file_state(str(file_path))
                if existing_state:
                    existing_state.processing_status = 'failed'
                    existing_state.error_count += 1
                    self.db.update_file_state(existing_state, self.current_session_id)
            except:
                pass
            
            return ProcessingResult(
                file_path=str(file_path),
                success=False,
                error=str(e),
                processing_time=time.time() - start_time,
                session_id=self.current_session_id
            )
    
    def process_batch(self, files: List[Path], max_workers: int = MAX_WORKERS) -> List[ProcessingResult]:
        """Process a batch of files concurrently."""
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(self.process_single_file, file_path): file_path 
                for file_path in files
            }
            
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    if result.success:
                        self.processed_files.add(str(file_path))
                        logger.info(f"✅ Completed: {file_path}")
                    else:
                        self.failed_files.add(str(file_path))
                        logger.error(f"❌ Failed: {file_path} - {result.error}")
                        
                except Exception as e:
                    logger.error(f"❌ Exception processing {file_path}: {e}")
                    self.failed_files.add(str(file_path))
                    results.append(ProcessingResult(
                        file_path=str(file_path),
                        success=False,
                        error=str(e),
                        session_id=self.current_session_id
                    ))
        
        return results
    
    def start_processing_session(self, config: Dict = None) -> str:
        """Start a new processing session."""
        self.current_session_id = self.db.create_session(config)
        logger.info(f"🚀 Started processing session: {self.current_session_id}")
        return self.current_session_id
    
    def end_processing_session(self):
        """End the current processing session."""
        if self.current_session_id:
            self.db.update_session(
                self.current_session_id,
                end_time=datetime.now().isoformat(),
                completed_files=len(self.processed_files),
                failed_files=len(self.failed_files),
                skipped_files=len(self.skipped_files),
                status='completed'
            )
            logger.info(f"🏁 Ended processing session: {self.current_session_id}")
    
    def generate_report(self, results: List[ProcessingResult]) -> Dict:
        """Generate processing report."""
        total_files = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total_files - successful
        
        total_faces = sum(r.faces_detected for r in results if r.faces_detected)
        captioned_files = sum(1 for r in results if r.caption)
        
        total_time = sum(r.processing_time for r in results)
        avg_time = total_time / total_files if total_files > 0 else 0
        
        # Get database stats
        db_stats = self.db.get_stats()
        
        report = {
            'session_id': self.current_session_id,
            'timestamp': datetime.now().isoformat(),
            'batch_stats': {
                'total_files': total_files,
                'successful': successful,
                'failed': failed,
                'success_rate': (successful / total_files * 100) if total_files > 0 else 0,
                'total_faces_detected': total_faces,
                'files_with_captions': captioned_files,
                'total_processing_time': total_time,
                'average_processing_time': avg_time,
            },
            'overall_stats': db_stats,
            'failed_files': list(self.failed_files),
            'skipped_files': list(self.skipped_files)
        }
        
        return report

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Process photos and videos from Drive E (incremental)")
    parser.add_argument("--drive-root", "-d", default="E:/", help="Drive E root path")
    parser.add_argument("--max-files", "-m", type=int, help="Maximum files to process")
    parser.add_argument("--file-types", "-t", choices=["images", "videos", "all"], default="all",
                       help="Types of files to process")
    parser.add_argument("--workers", "-w", type=int, default=MAX_WORKERS,
                       help="Number of worker threads")
    parser.add_argument("--batch-size", "-b", type=int, default=BATCH_SIZE,
                       help="Batch size for processing")
    parser.add_argument("--report-path", "-r", default="drive_e_processing_report.json",
                       help="Output path for processing report")
    parser.add_argument("--dry-run", action="store_true",
                       help="Discover files but don't process them")
    parser.add_argument("--focus-incoming", action="store_true", default=True,
                       help="Prioritize 01_INCOMING folder")
    parser.add_argument("--force-reprocess", action="store_true",
                       help="Force reprocessing of all files (ignore checkpoints)")
    parser.add_argument("--show-stats", action="store_true",
                       help="Show processing statistics and exit")
    parser.add_argument("--resume", action="store_true",
                       help="Resume processing pending files")
    
    args = parser.parse_args()
    
    if args.show_stats:
        # Show stats and exit
        db = ProcessingDatabase()
        stats = db.get_stats()
        print(json.dumps(stats, indent=2))
        return
    
    # Determine file extensions to process
    if args.file_types == "images":
        extensions = SUPPORTED_IMAGE_EXTENSIONS
    elif args.file_types == "videos":
        extensions = SUPPORTED_VIDEO_EXTENSIONS
    else:
        extensions = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS
    
    logger.info(f"🚀 Starting incremental Drive E processing")
    logger.info(f"📁 Root: {args.drive_root}")
    logger.info(f"🔢 Max files: {args.max_files or 'unlimited'}")
    logger.info(f"📋 File types: {args.file_types}")
    logger.info(f"👥 Workers: {args.workers}")
    logger.info(f"📦 Batch size: {args.batch_size}")
    logger.info(f"🎯 Focus incoming: {args.focus_incoming}")
    logger.info(f"🔄 Force reprocess: {args.force_reprocess}")
    
    try:
        # Initialize processor
        processor = IncrementalDriveEProcessor(drive_root=Path(args.drive_root))
        
        # Start processing session
        session_config = {
            'drive_root': args.drive_root,
            'max_files': args.max_files,
            'file_types': args.file_types,
            'workers': args.workers,
            'batch_size': args.batch_size,
            'focus_incoming': args.focus_incoming,
            'force_reprocess': args.force_reprocess
        }
        processor.start_processing_session(session_config)
        
        if args.resume:
            # Resume processing pending files
            pending_files = processor.db.get_pending_files(args.max_files)
            files = [Path(f) for f in pending_files if Path(f).exists()]
            logger.info(f"📄 Resuming {len(files)} pending files")
        else:
            # Discover files to process
            files = processor.discover_files_incremental(
                extensions=extensions, 
                focus_incoming=args.focus_incoming,
                max_files=args.max_files
            )
        
        if args.dry_run:
            logger.info(f"🔍 Dry run completed. Found {len(files)} files to process.")
            processor.end_processing_session()
            return
        
        if not files:
            logger.info("✨ No new files to process!")
            processor.end_processing_session()
            return
        
        # Process files in batches
        all_results = []
        for i in range(0, len(files), args.batch_size):
            batch = files[i:i + args.batch_size]
            logger.info(f"📦 Processing batch {i//args.batch_size + 1}: {len(batch)} files")
            
            batch_results = processor.process_batch(batch, max_workers=args.workers)
            all_results.extend(batch_results)
            
            # Log progress
            successful_batch = sum(1 for r in batch_results if r.success)
            logger.info(f"✅ Batch completed: {successful_batch}/{len(batch)} successful")
        
        # End processing session
        processor.end_processing_session()
        
        # Generate and save report
        report = processor.generate_report(all_results)
        
        with open(args.report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        logger.info(f"📊 Report saved to: {args.report_path}")
        
        # Log final summary
        batch_stats = report['batch_stats']
        overall_stats = report['overall_stats']
        
        logger.info(f"🎉 Processing completed!")
        logger.info(f"📊 This session: {batch_stats['total_files']} files")
        logger.info(f"✅ Successful: {batch_stats['successful']} ({batch_stats['success_rate']:.1f}%)")
        logger.info(f"❌ Failed: {batch_stats['failed']}")
        logger.info(f"⏭️ Skipped: {len(report['skipped_files'])}")
        logger.info(f"👤 Faces detected: {batch_stats['total_faces_detected']}")
        logger.info(f"📝 Files with captions: {batch_stats['files_with_captions']}")
        logger.info(f"⏱️  Average processing time: {batch_stats['average_processing_time']:.2f}s")
        logger.info(f"🗄️ Total in database: {overall_stats['total_files']} files")
        
    except KeyboardInterrupt:
        logger.info("🛑 Processing interrupted by user")
        if 'processor' in locals() and processor.current_session_id:
            processor.end_processing_session()
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        if 'processor' in locals() and processor.current_session_id:
            processor.end_processing_session()
        sys.exit(1)

if __name__ == "__main__":
    main()
