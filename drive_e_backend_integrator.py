#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Drive E Backend Integration Script

This script handles the initial ingestion of Drive E files into the VLM Photo Engine backend,
creating the foundation for AI processing tasks.

Features:
- Incremental ingestion (only new files)
- Batch processing for efficiency
- State tracking and recovery
- Integration with AI task manager
- Full Unicode/Chinese character support
"""

import json
import requests
import time
import logging
import sys
from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime
from dataclasses import dataclass, asdict

# Ensure UTF-8 encoding for all operations
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

@dataclass
class IngestionState:
    """Track ingestion state for directories and files."""
    directory_path: str
    last_processed: str
    file_count: int
    ingested_count: int
    skipped_count: int
    status: str  # 'pending', 'processing', 'completed', 'failed'
    last_error: str = ""

class DriveEBackendIntegrator:
    """Handles Drive E file integration with the backend."""
    
    def __init__(self, backend_url: str = "http://localhost:8000"):
        self.backend_url = backend_url
        self.drive_e_state_file = "simple_drive_e_state.json"
        self.ingestion_state_file = "drive_e_ingestion_state.json"
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('drive_e_integration.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('DriveEIntegrator')
        
        # Load states
        self.drive_e_files = self.load_drive_e_state()
        self.ingestion_state = self.load_ingestion_state()
    
    def normalize_path_for_api(self, path: str) -> str:
        """Normalize path for API calls with proper Unicode handling."""
        try:
            # Ensure string is properly encoded
            if isinstance(path, bytes):
                path = path.decode('utf-8')
            
            # Normalize path separators
            normalized = path.replace('\\', '/')
            
            # Validate Chinese characters are properly encoded
            try:
                # Test JSON serialization
                json.dumps({"test": normalized}, ensure_ascii=False)
            except UnicodeError as e:
                self.logger.warning(f"Unicode encoding issue with path: {path} - {e}")
                # Fallback: encode/decode to ensure clean UTF-8
                normalized = normalized.encode('utf-8', errors='replace').decode('utf-8')
            
            return normalized
        except Exception as e:
            self.logger.error(f"Error normalizing path {path}: {e}")
            return path.replace('\\', '/')
    
    def validate_chinese_characters(self, path: str) -> bool:
        """Validate that Chinese characters in path are properly handled."""
        chinese_chars = [c for c in path if '\u4e00' <= c <= '\u9fff']
        if chinese_chars:
            self.logger.debug(f"Path contains {len(chinese_chars)} Chinese characters: {path}")
            # Test encoding/decoding
            try:
                test_encoded = path.encode('utf-8')
                test_decoded = test_encoded.decode('utf-8')
                return test_decoded == path
            except UnicodeError:
                return False
        return True
    
    def load_drive_e_state(self) -> Dict:
        """Load Drive E processing state."""
        try:
            with open(self.drive_e_state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.logger.info(f"Loaded {len(data)} files from Drive E state")
            return data
        except Exception as e:
            self.logger.error(f"Failed to load Drive E state: {e}")
            return {}
    
    def load_ingestion_state(self) -> Dict[str, IngestionState]:
        """Load existing ingestion state."""
        try:
            with open(self.ingestion_state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Convert to IngestionState objects
            state = {}
            for path, state_data in data.items():
                state[path] = IngestionState(**state_data)
            
            self.logger.info(f"Loaded ingestion state for {len(state)} directories")
            return state
        except FileNotFoundError:
            return {}
        except Exception as e:
            self.logger.error(f"Error loading ingestion state: {e}")
            return {}
    
    def save_ingestion_state(self):
        """Save current ingestion state."""
        try:
            # Convert to dict format
            data = {}
            for path, state in self.ingestion_state.items():
                data[path] = asdict(state)
            
            # Atomic write with UTF-8 encoding
            temp_file = f"{self.ingestion_state_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            Path(temp_file).replace(self.ingestion_state_file)
            self.logger.debug(f"Saved ingestion state for {len(data)} directories")
        except Exception as e:
            self.logger.error(f"Error saving ingestion state: {e}")
    
    def check_backend_health(self) -> bool:
        """Check if backend is available."""
        try:
            response = requests.get(f"{self.backend_url}/health", timeout=10)
            if response.status_code == 200:
                self.logger.info("Backend is healthy")
                return True
            else:
                self.logger.error(f"Backend health check failed: {response.status_code}")
                return False
        except Exception as e:
            self.logger.error(f"Backend connection failed: {e}")
            return False
    
    def get_directory_mapping(self) -> Dict[str, List[str]]:
        """Map directories to their files from Drive E state."""
        directory_files = {}
        
        for file_path, file_info in self.drive_e_files.items():
            directory = str(Path(file_path).parent)
            
            if directory not in directory_files:
                directory_files[directory] = []
            
            directory_files[directory].append(file_path)
        
        self.logger.info(f"Found {len(directory_files)} directories with files")
        return directory_files
    
    def get_pending_directories(self, limit: int = None) -> List[str]:
        """Get directories that need processing."""
        directory_files = self.get_directory_mapping()
        pending = []
        
        for directory, files in directory_files.items():
            state = self.ingestion_state.get(directory)
            
            if not state or state.status in ['pending', 'failed']:
                pending.append(directory)
        
        # Sort by file count (smaller directories first for quicker feedback)
        pending.sort(key=lambda d: len(directory_files.get(d, [])))
        
        if limit:
            pending = pending[:limit]
        
        return pending
    
    def ingest_directory(self, directory_path: str) -> Dict:
        """Ingest a single directory into the backend."""
        try:
            self.logger.info(f"Ingesting directory: {directory_path}")
            
            # Update state to processing
            if directory_path not in self.ingestion_state:
                directory_files = self.get_directory_mapping()
                file_count = len(directory_files.get(directory_path, []))
                
                self.ingestion_state[directory_path] = IngestionState(
                    directory_path=directory_path,
                    last_processed=datetime.now().isoformat(),
                    file_count=file_count,
                    ingested_count=0,
                    skipped_count=0,
                    status='processing'
                )
            else:
                self.ingestion_state[directory_path].status = 'processing'
                self.ingestion_state[directory_path].last_processed = datetime.now().isoformat()
            
            self.save_ingestion_state()
            
            # Call backend ingest API with proper encoding
            try:
                # Validate and normalize path for Chinese characters
                if not self.validate_chinese_characters(directory_path):
                    self.logger.warning(f"Chinese character encoding issue detected: {directory_path}")
                
                # Normalize path using our utility method
                normalized_path = self.normalize_path_for_api(directory_path)
                
                self.logger.debug(f"Ingesting path: {normalized_path}")
                
                # Prepare JSON payload with explicit UTF-8 handling
                payload = {"roots": [normalized_path]}
                
                response = requests.post(
                    f"{self.backend_url}/ingest/scan",
                    json=payload,
                    timeout=300,  # 5 minutes timeout
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "Accept": "application/json",
                        "Accept-Charset": "utf-8"
                    }
                )
                
                self.logger.debug(f"API response status: {response.status_code}")
                
            except UnicodeError as e:
                error_msg = f"Unicode encoding error for {directory_path}: {e}"
                self.logger.error(error_msg)
                self.ingestion_state[directory_path].status = 'failed'
                self.ingestion_state[directory_path].last_error = error_msg
                self.save_ingestion_state()
                return {}
            except Exception as e:
                error_msg = f"Error making API request for {directory_path}: {e}"
                self.logger.error(error_msg)
                self.ingestion_state[directory_path].status = 'failed'
                self.ingestion_state[directory_path].last_error = error_msg
                self.save_ingestion_state()
                return {}
            
            if response.status_code == 200:
                result = response.json()
                
                # Update state with results
                state = self.ingestion_state[directory_path]
                state.ingested_count = result.get('new_assets', 0)
                state.skipped_count = result.get('skipped', 0)
                state.status = 'completed'
                state.last_error = ""
                
                self.logger.info(f"Directory ingested successfully: {directory_path}")
                self.logger.info(f"  New assets: {state.ingested_count}")
                self.logger.info(f"  Skipped: {state.skipped_count}")
                
                self.save_ingestion_state()
                return result
            else:
                error_msg = f"Ingestion failed: {response.status_code} - {response.text}"
                self.logger.error(error_msg)
                
                # Update state with error
                self.ingestion_state[directory_path].status = 'failed'
                self.ingestion_state[directory_path].last_error = error_msg
                self.save_ingestion_state()
                
                return {}
                
        except Exception as e:
            error_msg = f"Error ingesting directory {directory_path}: {e}"
            self.logger.error(error_msg)
            
            if directory_path in self.ingestion_state:
                self.ingestion_state[directory_path].status = 'failed'
                self.ingestion_state[directory_path].last_error = error_msg
                self.save_ingestion_state()
            
            return {}
    
    def run_incremental_ingestion(self, batch_size: int = 10, max_directories: int = None):
        """Run incremental ingestion process."""
        if not self.check_backend_health():
            raise Exception("Backend is not available")
        
        self.logger.info("Starting incremental Drive E ingestion")
        
        # Get pending directories
        pending_dirs = self.get_pending_directories(limit=max_directories)
        
        if not pending_dirs:
            self.logger.info("No directories need ingestion")
            return
        
        self.logger.info(f"Found {len(pending_dirs)} directories to ingest")
        
        # Process in batches
        total_ingested = 0
        total_skipped = 0
        successful_dirs = 0
        
        for i in range(0, len(pending_dirs), batch_size):
            batch = pending_dirs[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            self.logger.info(f"Processing batch {batch_num}: {len(batch)} directories")
            
            for directory in batch:
                result = self.ingest_directory(directory)
                
                if result:
                    total_ingested += result.get('new_assets', 0)
                    total_skipped += result.get('skipped', 0)
                    successful_dirs += 1
                
                # Small delay between directories
                time.sleep(1)
            
            # Longer pause between batches
            if i + batch_size < len(pending_dirs):
                self.logger.info(f"Batch {batch_num} complete, pausing before next batch...")
                time.sleep(5)
        
        self.logger.info("Incremental ingestion complete")
        self.logger.info(f"  Directories processed: {successful_dirs}/{len(pending_dirs)}")
        self.logger.info(f"  New assets: {total_ingested}")
        self.logger.info(f"  Skipped assets: {total_skipped}")
    
    def get_ingestion_statistics(self) -> Dict:
        """Get comprehensive ingestion statistics."""
        directory_files = self.get_directory_mapping()
        
        stats = {
            'total_directories': len(directory_files),
            'total_files': len(self.drive_e_files),
            'ingestion_status': {},
            'processed_directories': len(self.ingestion_state),
            'total_ingested': 0,
            'total_skipped': 0
        }
        
        # Count by status
        for state in self.ingestion_state.values():
            status = state.status
            stats['ingestion_status'][status] = stats['ingestion_status'].get(status, 0) + 1
            stats['total_ingested'] += state.ingested_count
            stats['total_skipped'] += state.skipped_count
        
        # Calculate pending
        pending_count = stats['total_directories'] - stats['processed_directories']
        if pending_count > 0:
            stats['ingestion_status']['pending'] = pending_count
        
        return stats
    
    def print_status_report(self):
        """Print comprehensive status report."""
        stats = self.get_ingestion_statistics()
        
        print("\n" + "="*60)
        print("DRIVE E INGESTION STATUS REPORT")
        print("="*60)
        
        print(f"\nOVERALL STATISTICS:")
        print(f"  Total directories: {stats['total_directories']}")
        print(f"  Total files: {stats['total_files']}")
        print(f"  Processed directories: {stats['processed_directories']}")
        
        print(f"\nINGESTION STATUS:")
        for status, count in stats['ingestion_status'].items():
            print(f"  {status}: {count}")
        
        print(f"\nINGESTION RESULTS:")
        print(f"  Total ingested: {stats['total_ingested']}")
        print(f"  Total skipped: {stats['total_skipped']}")
        
        # Show failed directories if any
        failed_dirs = [
            state.directory_path for state in self.ingestion_state.values()
            if state.status == 'failed'
        ]
        
        if failed_dirs:
            print(f"\nFAILED DIRECTORIES ({len(failed_dirs)}):")
            for directory in failed_dirs[:10]:  # Show first 10
                state = self.ingestion_state[directory]
                print(f"  {directory}")
                print(f"    Error: {state.last_error}")
            
            if len(failed_dirs) > 10:
                print(f"    ... and {len(failed_dirs) - 10} more")
        
        print("="*60)


def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Drive E Backend Integration')
    parser.add_argument('--backend-url', default='http://localhost:8000', help='Backend URL')
    parser.add_argument('--batch-size', type=int, default=10, help='Directories per batch')
    parser.add_argument('--max-dirs', type=int, help='Maximum directories to process')
    parser.add_argument('--status', action='store_true', help='Show status report only')
    
    args = parser.parse_args()
    
    integrator = DriveEBackendIntegrator(args.backend_url)
    
    try:
        if args.status:
            integrator.print_status_report()
        else:
            integrator.run_incremental_ingestion(
                batch_size=args.batch_size,
                max_directories=args.max_dirs
            )
            integrator.print_status_report()
            
    except Exception as e:
        print(f"Integration failed: {e}")
        integrator.logger.error(f"Integration failed: {e}")


if __name__ == "__main__":
    main()
