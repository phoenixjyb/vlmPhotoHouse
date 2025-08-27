#!/usr/bin/env import os
import sys
import json
import time
import requests
import hashlib
import mimetypes
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime
import argparse
import logging
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import exifread
from PIL import Image, ExifTags
import sqlite3
import threading
from collections import defaultdict
import uuidve E Photo and Video Processing Script

Comprehensive script to process photos and videos from Drive E using the running services:
- Caption service (Qwen2.5-VL + BLIP2 fallback)
- LVFace service (face detection and embedding)
- ASR/TTS services for metadata extraction
- Asset management and organization

Integrates with the existing backend API services running on:
- Main API: http://127.0.0.1:8002
- Voice/TTS: http://127.0.0.1:8001
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
from datetime import datetime
import argparse
import logging
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import exifread
from PIL import Image, ExifTags
import sqlite3
import pickle
from threading import Lock

# Configuration
DRIVE_E_ROOT = Path("E:/")
API_BASE_URL = "http://127.0.0.1:8002"
VOICE_BASE_URL = "http://127.0.0.1:8001"
MAX_WORKERS = 4
BATCH_SIZE = 100

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

@dataclass
class ProcessingCheckpoint:
    """Checkpoint data for resuming processing."""
    session_id: str
    timestamp: datetime
    total_files: int
    processed_files: int
    successful_files: int
    failed_files: int
    current_batch: int
    processed_paths: Set[str]
    failed_paths: Set[str]
    last_file_processed: Optional[str] = None
    
    def save_to_file(self, checkpoint_path: Path):
        """Save checkpoint to file."""
        checkpoint_data = asdict(self)
        checkpoint_data['timestamp'] = self.timestamp.isoformat()
        checkpoint_data['processed_paths'] = list(self.processed_paths)
        checkpoint_data['failed_paths'] = list(self.failed_paths)
        
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
    
    @classmethod
    def load_from_file(cls, checkpoint_path: Path) -> Optional['ProcessingCheckpoint']:
        """Load checkpoint from file."""
        try:
            with open(checkpoint_path, 'r') as f:
                data = json.load(f)
            
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
            data['processed_paths'] = set(data['processed_paths'])
            data['failed_paths'] = set(data['failed_paths'])
            
            return cls(**data)
        except Exception as e:
            logging.warning(f"Failed to load checkpoint: {e}")
            return None

class DriveEProcessor:
    """Main processor for Drive E files."""
    
    def __init__(self, drive_root: Path = DRIVE_E_ROOT, api_base: str = API_BASE_URL, 
                 resume_from_checkpoint: bool = True, force_reprocess: bool = False):
        self.drive_root = drive_root
        self.api_base = api_base
        self.voice_base = VOICE_BASE_URL
        self.session = requests.Session()
        self.resume_from_checkpoint = resume_from_checkpoint
        self.force_reprocess = force_reprocess
        
        # Session tracking
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.checkpoint_path = Path(f"drive_e_checkpoint_{self.session_id}.json")
        self.processing_db_path = Path("drive_e_processing.db")
        self.checkpoint_lock = Lock()
        
        # Processing state
        self.processed_files: Set[str] = set()
        self.failed_files: Set[str] = set()
        self.current_checkpoint: Optional[ProcessingCheckpoint] = None
        
        # Initialize processing database
        self._init_processing_db()
        
        # Load previous checkpoint if resuming
        if self.resume_from_checkpoint and not self.force_reprocess:
            self._load_latest_checkpoint()
        
        # Verify services are running
        self._verify_services()
    
    def _init_processing_db(self):
        """Initialize local processing database for bookkeeping."""
        try:
            conn = sqlite3.connect(self.processing_db_path)
            cursor = conn.cursor()
            
            # Create processing history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processing_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    file_hash TEXT,
                    last_modified REAL,
                    processing_status TEXT, -- 'pending', 'processing', 'completed', 'failed', 'skipped'
                    asset_id INTEGER,
                    caption_generated BOOLEAN DEFAULT FALSE,
                    faces_detected INTEGER DEFAULT 0,
                    processing_time REAL,
                    error_message TEXT,
                    first_processed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_processed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    session_id TEXT
                )
            ''')
            
            # Create processing sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processing_sessions (
                    session_id TEXT PRIMARY KEY,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    drive_root TEXT,
                    total_files INTEGER,
                    completed_files INTEGER,
                    failed_files INTEGER,
                    status TEXT DEFAULT 'active' -- 'active', 'completed', 'interrupted'
                )
            ''')
            
            # Create indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_file_path ON processing_history(file_path)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON processing_history(processing_status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_session ON processing_history(session_id)')
            
            conn.commit()
            conn.close()
            
            logger.info(f"📊 Processing database initialized: {self.processing_db_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize processing database: {e}")
            raise
    
    def _load_latest_checkpoint(self):
        """Load the latest checkpoint if available."""
        try:
            # Find the most recent checkpoint file
            checkpoint_files = list(Path('.').glob('drive_e_checkpoint_*.json'))
            if not checkpoint_files:
                logger.info("No previous checkpoint found, starting fresh")
                return
            
            latest_checkpoint_file = max(checkpoint_files, key=lambda p: p.stat().st_mtime)
            
            checkpoint = ProcessingCheckpoint.load_from_file(latest_checkpoint_file)
            if checkpoint:
                self.current_checkpoint = checkpoint
                self.processed_files = checkpoint.processed_paths
                self.failed_files = checkpoint.failed_paths
                self.session_id = checkpoint.session_id
                self.checkpoint_path = latest_checkpoint_file
                
                logger.info(f"📥 Loaded checkpoint from {latest_checkpoint_file}")
                logger.info(f"   Previous session: {checkpoint.session_id}")
                logger.info(f"   Processed: {checkpoint.processed_files}/{checkpoint.total_files}")
                logger.info(f"   Last file: {checkpoint.last_file_processed}")
                
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
    
    def _save_checkpoint(self, total_files: int, processed_count: int, successful_count: int, 
                        failed_count: int, current_batch: int, last_file: str = None):
        """Save current processing state to checkpoint."""
        try:
            with self.checkpoint_lock:
                checkpoint = ProcessingCheckpoint(
                    session_id=self.session_id,
                    timestamp=datetime.now(),
                    total_files=total_files,
                    processed_files=processed_count,
                    successful_files=successful_count,
                    failed_files=failed_count,
                    current_batch=current_batch,
                    processed_paths=self.processed_files.copy(),
                    failed_paths=self.failed_files.copy(),
                    last_file_processed=last_file
                )
                
                checkpoint.save_to_file(self.checkpoint_path)
                self.current_checkpoint = checkpoint
                
        except Exception as e:
            logger.warning(f"Failed to save checkpoint: {e}")
    
    def _is_file_processed(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """Check if file has been processed successfully."""
        if self.force_reprocess:
            return False, "force_reprocess_enabled"
        
        file_path_str = str(file_path.resolve())
        
        # Check in-memory cache first
        if file_path_str in self.processed_files:
            return True, "in_memory_cache"
        
        # Check database
        try:
            conn = sqlite3.connect(self.processing_db_path)
            cursor = conn.cursor()
            
            # Get file stats for comparison
            file_stat = file_path.stat()
            file_modified = file_stat.st_mtime
            
            cursor.execute('''
                SELECT processing_status, last_modified, asset_id, error_message
                FROM processing_history 
                WHERE file_path = ?
                ORDER BY last_processed DESC
                LIMIT 1
            ''', (file_path_str,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                status, last_modified, asset_id, error_message = result
                
                # Check if file was modified since last processing
                if last_modified and abs(last_modified - file_modified) > 1:  # 1 second tolerance
                    return False, "file_modified_since_last_processing"
                
                if status == 'completed' and asset_id:
                    # Verify asset still exists in main database
                    if self._verify_asset_exists(asset_id):
                        return True, "previously_completed"
                    else:
                        return False, "asset_no_longer_exists"
                elif status == 'failed':
                    return False, f"previously_failed: {error_message}"
                
            return False, "not_processed"
            
        except Exception as e:
            logger.warning(f"Error checking processing status for {file_path}: {e}")
            return False, "check_error"
    
    def _verify_asset_exists(self, asset_id: int) -> bool:
        """Verify that an asset still exists in the main database."""
        try:
            response = self.session.get(f"{self.api_base}/assets/{asset_id}", timeout=10)
            return response.status_code == 200
        except Exception:
            return False
    
    def _update_processing_status(self, file_path: Path, status: str, **kwargs):
        """Update processing status in database."""
        try:
            conn = sqlite3.connect(self.processing_db_path)
            cursor = conn.cursor()
            
            file_path_str = str(file_path.resolve())
            file_stat = file_path.stat()
            
            # Prepare update data
            update_data = {
                'processing_status': status,
                'last_modified': file_stat.st_mtime,
                'last_processed': datetime.now().isoformat(),
                'session_id': self.session_id
            }
            update_data.update(kwargs)
            
            # Insert or update record
            cursor.execute('''
                INSERT OR REPLACE INTO processing_history 
                (file_path, file_hash, last_modified, processing_status, asset_id, 
                 caption_generated, faces_detected, processing_time, error_message, 
                 last_processed, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_path_str,
                update_data.get('file_hash'),
                update_data['last_modified'],
                status,
                update_data.get('asset_id'),
                update_data.get('caption_generated', False),
                update_data.get('faces_detected', 0),
                update_data.get('processing_time'),
                update_data.get('error_message'),
                update_data['last_processed'],
                update_data['session_id']
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.warning(f"Failed to update processing status: {e}")
        
    def _verify_services(self):
        """Verify that required services are running."""
        try:
            # Check main API
            response = self.session.get(f"{self.api_base}/health", timeout=5)
            if response.status_code != 200:
                raise ConnectionError(f"Main API not responding: {response.status_code}")
            
            # Check caption service
            response = self.session.get(f"{self.api_base}/caption/health", timeout=5)
            if response.status_code != 200:
                logger.warning("Caption service may not be available")
            
            # Check face service
            response = self.session.get(f"{self.api_base}/face/health", timeout=5)
            if response.status_code != 200:
                logger.warning("Face service may not be available")
                
            # Check voice service
            try:
                response = self.session.get(f"{self.voice_base}/api/voice-chat/health", timeout=5)
                if response.status_code != 200:
                    logger.warning("Voice service may not be available")
            except:
                logger.warning("Voice service not accessible")
                
            logger.info("✅ Service verification complete")
            
        except Exception as e:
            logger.error(f"❌ Service verification failed: {e}")
            raise
    
    def discover_files(self, extensions: Set[str] = None, max_files: int = None) -> Tuple[List[Path], List[Path]]:
        """Discover files to process on Drive E.
        
        Returns:
            Tuple of (files_to_process, files_already_processed)
        """
        if extensions is None:
            extensions = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS
            
        logger.info(f"🔍 Discovering files in {self.drive_root}")
        all_files = []
        files_to_process = []
        files_already_processed = []
        
        try:
            for ext in extensions:
                pattern = f"**/*{ext}"
                found = list(self.drive_root.rglob(pattern))
                all_files.extend(found)
                logger.info(f"Found {len(found)} {ext} files")
                
                if max_files and len(all_files) >= max_files:
                    all_files = all_files[:max_files]
                    break
                    
        except Exception as e:
            logger.error(f"Error discovering files: {e}")
            
        logger.info(f"📁 Total files discovered: {len(all_files)}")
        
        # Filter out already processed files (unless force reprocess)
        if not self.force_reprocess:
            logger.info("🔍 Checking processing status of discovered files...")
            
            for file_path in all_files:
                is_processed, reason = self._is_file_processed(file_path)
                
                if is_processed:
                    files_already_processed.append(file_path)
                    if len(files_already_processed) % 100 == 0:
                        logger.info(f"   Skipped {len(files_already_processed)} already processed files...")
                else:
                    files_to_process.append(file_path)
            
            logger.info(f"📊 Processing status:")
            logger.info(f"   📄 Total discovered: {len(all_files)}")
            logger.info(f"   ✅ Already processed: {len(files_already_processed)}")
            logger.info(f"   🔄 To be processed: {len(files_to_process)}")
            
        else:
            files_to_process = all_files
            logger.info(f"🔄 Force reprocess enabled - will process all {len(files_to_process)} files")
            
        return files_to_process, files_already_processed
    
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
            # PIL metadata
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
        metadata = {}
        
        try:
            # Basic video metadata - could be enhanced with ffprobe
            metadata['is_video'] = True
            # TODO: Add ffprobe integration for duration, resolution, codec info
            
        except Exception as e:
            logger.warning(f"Failed to extract video metadata for {file_path}: {e}")
            
        return metadata
    
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
    
    def ingest_asset(self, file_path: Path, metadata: Dict) -> Optional[int]:
        """Ingest asset into the backend system."""
        try:
            # Prepare asset data
            asset_data = {
                'path': str(file_path.resolve()),
                'hash_sha256': self.calculate_file_hash(file_path),
                'file_size': metadata['file_size'],
                'mime_type': metadata['mime_type'],
                'width': metadata.get('width'),
                'height': metadata.get('height'),
                'taken_at': metadata.get('taken_at').isoformat() if metadata.get('taken_at') else None,
                'camera_make': metadata.get('camera_make'),
                'camera_model': metadata.get('camera_model')
            }
            
            # Post to assets endpoint
            response = self.session.post(
                f"{self.api_base}/assets/",
                json=asset_data,
                timeout=30
            )
            
            if response.status_code == 201:
                asset_id = response.json().get('id')
                logger.info(f"✅ Asset ingested with ID: {asset_id}")
                return asset_id
            elif response.status_code == 409:
                # Asset already exists
                existing_asset = response.json()
                logger.info(f"📄 Asset already exists with ID: {existing_asset.get('id')}")
                return existing_asset.get('id')
            else:
                logger.error(f"Failed to ingest asset: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error ingesting asset {file_path}: {e}")
            return None
    
    def process_caption(self, file_path: Path, asset_id: int) -> Optional[str]:
        """Process caption for image/video."""
        if file_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            return None
            
        try:
            # Prepare image for captioning
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
            
            # Mark as processing
            self._update_processing_status(file_path, 'processing')
            
            # Extract metadata
            metadata = self.extract_metadata(file_path)
            
            # Calculate file hash for tracking
            file_hash = self.calculate_file_hash(file_path)
            
            # Ingest asset
            asset_id = self.ingest_asset(file_path, metadata)
            if not asset_id:
                error_msg = "Failed to ingest asset"
                self._update_processing_status(
                    file_path, 'failed', 
                    error_message=error_msg,
                    file_hash=file_hash,
                    processing_time=time.time() - start_time
                )
                return ProcessingResult(
                    file_path=str(file_path),
                    success=False,
                    error=error_msg
                )
            
            # Process caption (for images)
            caption = None
            caption_generated = False
            if file_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                caption = self.process_caption(file_path, asset_id)
                caption_generated = caption is not None
            
            # Process faces (for images)
            faces_count = 0
            if file_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                faces_count = self.process_faces(file_path, asset_id)
            
            processing_time = time.time() - start_time
            
            # Mark as completed
            self._update_processing_status(
                file_path, 'completed',
                asset_id=asset_id,
                file_hash=file_hash,
                caption_generated=caption_generated,
                faces_detected=faces_count,
                processing_time=processing_time
            )
            
            return ProcessingResult(
                file_path=str(file_path),
                success=True,
                caption=caption,
                faces_detected=faces_count,
                asset_id=asset_id,
                processing_time=processing_time,
                metadata=metadata
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = str(e)
            
            # Mark as failed
            self._update_processing_status(
                file_path, 'failed',
                error_message=error_msg,
                processing_time=processing_time
            )
            
            logger.error(f"❌ Error processing {file_path}: {e}")
            return ProcessingResult(
                file_path=str(file_path),
                success=False,
                error=error_msg,
                processing_time=processing_time
            )
    
    def process_batch(self, files: List[Path], max_workers: int = MAX_WORKERS, 
                     total_files: int = None, batch_number: int = 0) -> List[ProcessingResult]:
        """Process a batch of files concurrently."""
        results = []
        
        if total_files is None:
            total_files = len(files)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(self.process_single_file, file_path): file_path 
                for file_path in files
            }
            
            # Collect results
            completed_in_batch = 0
            successful_in_batch = 0
            
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    result = future.result()
                    results.append(result)
                    completed_in_batch += 1
                    
                    if result.success:
                        successful_in_batch += 1
                        self.processed_files.add(str(file_path))
                        logger.info(f"✅ Completed: {file_path}")
                    else:
                        self.failed_files.add(str(file_path))
                        logger.error(f"❌ Failed: {file_path} - {result.error}")
                    
                    # Save checkpoint every 10 files
                    if completed_in_batch % 10 == 0:
                        total_processed = len(self.processed_files)
                        total_successful = total_processed - len(self.failed_files)
                        total_failed = len(self.failed_files)
                        
                        self._save_checkpoint(
                            total_files=total_files,
                            processed_count=total_processed,
                            successful_count=total_successful,
                            failed_count=total_failed,
                            current_batch=batch_number,
                            last_file=str(file_path)
                        )
                        
                except Exception as e:
                    logger.error(f"❌ Exception processing {file_path}: {e}")
                    self.failed_files.add(str(file_path))
                    self._update_processing_status(file_path, 'failed', error_message=str(e))
                    results.append(ProcessingResult(
                        file_path=str(file_path),
                        success=False,
                        error=str(e)
                    ))
        
        # Save checkpoint after batch completion
        total_processed = len(self.processed_files)
        total_successful = total_processed - len(self.failed_files)
        total_failed = len(self.failed_files)
        
        self._save_checkpoint(
            total_files=total_files,
            processed_count=total_processed,
            successful_count=total_successful,
            failed_count=total_failed,
            current_batch=batch_number,
            last_file=str(files[-1]) if files else None
        )
        
        return results
    
    def generate_report(self, results: List[ProcessingResult]) -> Dict:
        """Generate processing report."""
        total_files = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total_files - successful
        
        total_faces = sum(r.faces_detected for r in results if r.faces_detected)
        captioned_files = sum(1 for r in results if r.caption)
        
        total_time = sum(r.processing_time for r in results)
        avg_time = total_time / total_files if total_files > 0 else 0
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_files': total_files,
            'successful': successful,
            'failed': failed,
            'success_rate': (successful / total_files * 100) if total_files > 0 else 0,
            'total_faces_detected': total_faces,
            'files_with_captions': captioned_files,
            'total_processing_time': total_time,
            'average_processing_time': avg_time,
            'failed_files': list(self.failed_files)
        }
        
        return report
    
    def save_report(self, report: Dict, output_path: str = "drive_e_processing_report.json"):
        """Save processing report to file."""
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        logger.info(f"📊 Report saved to: {output_path}")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Process photos and videos from Drive E")
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
    parser.add_argument("--force-reprocess", "-f", action="store_true",
                       help="Force reprocessing of all files, ignoring previous status")
    parser.add_argument("--no-resume", action="store_true",
                       help="Don't resume from previous checkpoint, start fresh")
    parser.add_argument("--checkpoint-interval", type=int, default=10,
                       help="Save checkpoint every N files")
    parser.add_argument("--show-processed", action="store_true",
                       help="Show already processed files in discovery")
    
    args = parser.parse_args()
    
    # Determine file extensions to process
    if args.file_types == "images":
        extensions = SUPPORTED_IMAGE_EXTENSIONS
    elif args.file_types == "videos":
        extensions = SUPPORTED_VIDEO_EXTENSIONS
    else:
        extensions = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS
    
    logger.info(f"🚀 Starting Drive E processing")
    logger.info(f"📁 Root: {args.drive_root}")
    logger.info(f"🔢 Max files: {args.max_files or 'unlimited'}")
    logger.info(f"📋 File types: {args.file_types}")
    logger.info(f"👥 Workers: {args.workers}")
    logger.info(f"📦 Batch size: {args.batch_size}")
    logger.info(f"🔄 Force reprocess: {args.force_reprocess}")
    logger.info(f"📥 Resume from checkpoint: {not args.no_resume}")
    
    try:
        # Initialize processor
        processor = DriveEProcessor(
            drive_root=Path(args.drive_root),
            resume_from_checkpoint=not args.no_resume,
            force_reprocess=args.force_reprocess
        )
        
        # Discover files
        files_to_process, files_already_processed = processor.discover_files(
            extensions=extensions, 
            max_files=args.max_files
        )
        
        if args.show_processed and files_already_processed:
            logger.info(f"📄 Already processed files ({len(files_already_processed)}):")
            for i, file_path in enumerate(files_already_processed[:10]):
                logger.info(f"   {i+1}. {file_path}")
            if len(files_already_processed) > 10:
                logger.info(f"   ... and {len(files_already_processed) - 10} more")
        
        if args.dry_run:
            logger.info(f"🔍 Dry run completed.")
            logger.info(f"   📄 Total discovered: {len(files_to_process) + len(files_already_processed)}")
            logger.info(f"   ✅ Already processed: {len(files_already_processed)}")
            logger.info(f"   🔄 Would process: {len(files_to_process)}")
            return
        
        if not files_to_process:
            logger.info("✅ All discovered files have already been processed!")
            if not args.force_reprocess:
                logger.info("💡 Use --force-reprocess to reprocess all files")
            return
        
        # Process files in batches
        all_results = []
        total_files = len(files_to_process)
        
        for i in range(0, len(files_to_process), args.batch_size):
            batch = files_to_process[i:i + args.batch_size]
            batch_number = i // args.batch_size + 1
            
            logger.info(f"📦 Processing batch {batch_number}: {len(batch)} files")
            logger.info(f"   Progress: {i + len(batch)}/{total_files} files")
            
            batch_results = processor.process_batch(
                batch, 
                max_workers=args.workers,
                total_files=total_files,
                batch_number=batch_number
            )
            all_results.extend(batch_results)
            
            # Log progress
            successful_batch = sum(1 for r in batch_results if r.success)
            logger.info(f"✅ Batch {batch_number} completed: {successful_batch}/{len(batch)} successful")
            
            # Show overall progress
            total_processed = len(processor.processed_files)
            total_successful = total_processed - len(processor.failed_files)
            logger.info(f"📊 Overall progress: {total_processed}/{total_files} "
                       f"({total_processed/total_files*100:.1f}%)")
        
        # Generate and save report
        report = processor.generate_report(all_results)
        report['files_already_processed'] = len(files_already_processed)
        report['total_discovered'] = len(files_to_process) + len(files_already_processed)
        
        processor.save_report(report, args.report_path)
        
        # Log final summary
        logger.info(f"🎉 Processing completed!")
        logger.info(f"📊 Total: {report['total_files']} files")
        logger.info(f"✅ Successful: {report['successful']} ({report['success_rate']:.1f}%)")
        logger.info(f"❌ Failed: {report['failed']}")
        logger.info(f"👤 Faces detected: {report['total_faces_detected']}")
        logger.info(f"📝 Files with captions: {report['files_with_captions']}")
        logger.info(f"⏱️  Average processing time: {report['average_processing_time']:.2f}s")
        
    except KeyboardInterrupt:
        logger.info("🛑 Processing interrupted by user")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
