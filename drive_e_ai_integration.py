#!/usr/bin/env python3
"""
Drive E AI Integration Script

This script integrates the processed Drive E files with the VLM Photo Engine
backend for AI processing (captions, face recognition, embeddings, etc.).

Features:
- Reads processed files from simple_drive_e_state.json
- Batches files for efficient processing
- Calls backend /ingest/scan API
- Monitors AI task progress
- Provides detailed logging and progress tracking
"""

import json
import requests
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('drive_e_ai_integration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DriveEAIIntegrator:
    def __init__(self, backend_url: str = "http://localhost:8000"):
        self.backend_url = backend_url
        self.state_file = "simple_drive_e_state.json"
        
    def load_drive_e_state(self) -> Dict:
        """Load the Drive E processing state file."""
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            logger.info(f"Loaded {len(data)} files from Drive E state")
            return data
        except Exception as e:
            logger.error(f"Failed to load state file: {e}")
            raise
    
    def check_backend_health(self) -> bool:
        """Check if the backend is running and healthy."""
        try:
            response = requests.get(f"{self.backend_url}/health", timeout=10)
            if response.status_code == 200:
                logger.info("Backend is healthy")
                return True
            else:
                logger.error(f"Backend health check failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Backend connection failed: {e}")
            return False
    
    def get_directory_paths(self, file_paths: List[str]) -> List[str]:
        """Extract unique directory paths from file paths."""
        directories = set()
        for file_path in file_paths:
            directories.add(str(Path(file_path).parent))
        return list(directories)
    
    def ingest_directories(self, directories: List[str]) -> Dict:
        """Call the backend ingest API for the given directories."""
        try:
            logger.info(f"Ingesting {len(directories)} directories into backend")
            response = requests.post(
                f"{self.backend_url}/ingest/scan",
                json={"paths": directories},
                timeout=300  # 5 minutes timeout for large directories
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Ingest completed: {result}")
                return result
            else:
                logger.error(f"Ingest failed: {response.status_code} - {response.text}")
                return {}
        except Exception as e:
            logger.error(f"Ingest request failed: {e}")
            return {}
    
    def get_metrics(self) -> Dict:
        """Get current backend metrics including task counts."""
        try:
            response = requests.get(f"{self.backend_url}/metrics", timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Metrics request failed: {response.status_code}")
                return {}
        except Exception as e:
            logger.warning(f"Metrics request error: {e}")
            return {}
    
    def monitor_ai_tasks(self, check_interval: int = 30, max_wait: int = 3600) -> None:
        """Monitor AI task progress."""
        logger.info("Starting AI task monitoring...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            metrics = self.get_metrics()
            if metrics:
                pending_tasks = metrics.get('pending_tasks', 0)
                completed_tasks = metrics.get('completed_tasks', 0)
                failed_tasks = metrics.get('failed_tasks', 0)
                
                logger.info(f"Tasks - Pending: {pending_tasks}, Completed: {completed_tasks}, Failed: {failed_tasks}")
                
                if pending_tasks == 0:
                    logger.info("All AI tasks completed!")
                    break
            
            time.sleep(check_interval)
        
        if time.time() - start_time >= max_wait:
            logger.warning(f"Monitoring timeout reached ({max_wait}s)")
    
    def process_drive_e_integration(self, batch_size: int = 1000, monitor_tasks: bool = True) -> Dict:
        """Main integration process."""
        logger.info("Starting Drive E AI Integration")
        
        # Check backend health
        if not self.check_backend_health():
            raise Exception("Backend is not available")
        
        # Load Drive E state
        drive_e_data = self.load_drive_e_state()
        file_paths = list(drive_e_data.keys())
        
        # Extract directory paths
        directories = self.get_directory_paths(file_paths)
        logger.info(f"Found {len(directories)} unique directories to process")
        
        # Process directories in batches
        total_ingested = 0
        total_skipped = 0
        
        for i in range(0, len(directories), batch_size):
            batch = directories[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}: {len(batch)} directories")
            
            result = self.ingest_directories(batch)
            if result:
                total_ingested += result.get('new_assets', 0)
                total_skipped += result.get('skipped', 0)
        
        logger.info(f"Integration complete - New assets: {total_ingested}, Skipped: {total_skipped}")
        
        # Monitor AI tasks if requested
        if monitor_tasks and total_ingested > 0:
            logger.info("Starting AI task monitoring...")
            self.monitor_ai_tasks()
        
        return {
            'total_files': len(file_paths),
            'total_directories': len(directories),
            'new_assets': total_ingested,
            'skipped_assets': total_skipped,
            'integration_time': datetime.now().isoformat()
        }

def main():
    """Main execution function."""
    integrator = DriveEAIIntegrator()
    
    try:
        result = integrator.process_drive_e_integration(
            batch_size=50,  # Process 50 directories at a time
            monitor_tasks=True  # Monitor AI task progress
        )
        
        logger.info("Drive E AI Integration Summary:")
        for key, value in result.items():
            logger.info(f"  {key}: {value}")
        
        # Save results
        with open('drive_e_ai_integration_results.json', 'w') as f:
            json.dump(result, f, indent=2)
        
        logger.info("Integration results saved to drive_e_ai_integration_results.json")
        
    except Exception as e:
        logger.error(f"Integration failed: {e}")
        raise

if __name__ == "__main__":
    main()
