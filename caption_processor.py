#!/usr/bin/env python3
"""
AI Caption Generation Processor

Specialized processor for generating image captions using the VLM Photo Engine backend.
Handles incremental processing with state tracking and retry logic.
"""

import json
import requests
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class CaptionTask:
    """Track caption generation task state."""
    asset_id: int
    file_path: str
    status: str  # 'pending', 'processing', 'completed', 'failed', 'skipped'
    created_at: str
    updated_at: str
    attempts: int = 0
    caption_text: Optional[str] = None
    confidence_score: Optional[float] = None
    model_used: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None

class CaptionProcessor:
    """Handles AI caption generation tasks."""
    
    def __init__(self, backend_url: str = "http://localhost:8000"):
        self.backend_url = backend_url
        self.state_file = "caption_processing_state.json"
        self.max_retries = 3
        self.batch_size = 20
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('caption_processor.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('CaptionProcessor')
        
        # Load existing state
        self.task_state = self.load_state()
        self.logger.info(f"Loaded {len(self.task_state)} caption tasks")
    
    def load_state(self) -> Dict[int, CaptionTask]:
        """Load existing task state."""
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            
            # Convert to CaptionTask objects
            state = {}
            for asset_id_str, task_data in data.items():
                asset_id = int(asset_id_str)
                state[asset_id] = CaptionTask(**task_data)
            
            return state
        except FileNotFoundError:
            return {}
        except Exception as e:
            self.logger.error(f"Error loading state: {e}")
            return {}
    
    def save_state(self):
        """Save current task state."""
        try:
            # Convert to serializable format
            data = {}
            for asset_id, task in self.task_state.items():
                data[str(asset_id)] = asdict(task)
            
            # Atomic write
            temp_file = f"{self.state_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            Path(temp_file).replace(self.state_file)
            self.logger.debug(f"Saved state for {len(data)} tasks")
        except Exception as e:
            self.logger.error(f"Error saving state: {e}")
    
    def check_backend_health(self) -> bool:
        """Check if backend is available."""
        try:
            response = requests.get(f"{self.backend_url}/health", timeout=10)
            return response.status_code == 200
        except Exception:
            return False
    
    def discover_assets_needing_captions(self) -> List[Dict]:
        """Find assets that need caption generation."""
        try:
            # Get all image assets from backend
            response = requests.get(f"{self.backend_url}/assets?type=image", timeout=30)
            if response.status_code != 200:
                self.logger.error(f"Failed to get assets: {response.status_code}")
                return []
            
            assets = response.json().get('assets', [])
            needs_captions = []
            
            for asset in assets:
                asset_id = asset['id']
                
                # Skip if we already have this task
                if asset_id in self.task_state:
                    continue
                
                # Check if asset already has captions
                try:
                    caption_response = requests.get(
                        f"{self.backend_url}/assets/{asset_id}/captions",
                        timeout=10
                    )
                    
                    if caption_response.status_code == 200:
                        captions = caption_response.json().get('captions', [])
                        if captions:
                            # Already has captions, mark as completed
                            self.task_state[asset_id] = CaptionTask(
                                asset_id=asset_id,
                                file_path=asset['path'],
                                status='completed',
                                created_at=datetime.now().isoformat(),
                                updated_at=datetime.now().isoformat(),
                                caption_text=captions[0].get('text', '') if captions else None
                            )
                            continue
                except Exception:
                    pass  # If caption check fails, assume it needs captions
                
                needs_captions.append(asset)
            
            self.logger.info(f"Found {len(needs_captions)} assets needing captions")
            return needs_captions
            
        except Exception as e:
            self.logger.error(f"Error discovering assets: {e}")
            return []
    
    def create_caption_tasks(self, assets: List[Dict]):
        """Create caption tasks for given assets."""
        current_time = datetime.now().isoformat()
        
        for asset in assets:
            asset_id = asset['id']
            
            if asset_id not in self.task_state:
                task = CaptionTask(
                    asset_id=asset_id,
                    file_path=asset['path'],
                    status='pending',
                    created_at=current_time,
                    updated_at=current_time
                )
                self.task_state[asset_id] = task
        
        self.save_state()
    
    def get_pending_tasks(self, limit: Optional[int] = None) -> List[CaptionTask]:
        """Get pending caption tasks."""
        pending = [
            task for task in self.task_state.values()
            if task.status == 'pending' and task.attempts < self.max_retries
        ]
        
        # Sort by creation time (oldest first)
        pending.sort(key=lambda t: t.created_at)
        
        if limit:
            pending = pending[:limit]
        
        return pending
    
    def execute_caption_task(self, task: CaptionTask) -> bool:
        """Execute a single caption generation task."""
        try:
            self.logger.info(f"Generating caption for asset {task.asset_id}")
            
            # Update task status
            task.status = 'processing'
            task.updated_at = datetime.now().isoformat()
            task.attempts += 1
            self.save_state()
            
            start_time = time.time()
            
            # Call backend caption generation
            response = requests.post(
                f"{self.backend_url}/assets/{task.asset_id}/captions/regenerate",
                json={},
                timeout=120  # 2 minute timeout for caption generation
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            task.processing_time_ms = processing_time
            
            if response.status_code == 200:
                # Get the generated caption
                caption_response = requests.get(
                    f"{self.backend_url}/assets/{task.asset_id}/captions",
                    timeout=10
                )
                
                if caption_response.status_code == 200:
                    captions = caption_response.json().get('captions', [])
                    if captions:
                        latest_caption = captions[0]  # Assuming most recent is first
                        task.caption_text = latest_caption.get('text', '')
                        task.confidence_score = latest_caption.get('confidence')
                        task.model_used = latest_caption.get('model')
                
                task.status = 'completed'
                task.error_message = None
                self.logger.info(f"Caption generated for asset {task.asset_id} in {processing_time}ms")
                
                if task.caption_text:
                    self.logger.debug(f"Caption: {task.caption_text[:100]}...")
                
            elif response.status_code == 404:
                # Asset not found, mark as skipped
                task.status = 'skipped'
                task.error_message = "Asset not found in backend"
                self.logger.warning(f"Asset {task.asset_id} not found, skipping")
                
            else:
                # Other error
                error_msg = f"Caption generation failed: {response.status_code} - {response.text}"
                task.error_message = error_msg
                
                if task.attempts >= self.max_retries:
                    task.status = 'failed'
                    self.logger.error(f"Caption generation failed permanently for asset {task.asset_id}: {error_msg}")
                else:
                    task.status = 'pending'
                    self.logger.warning(f"Caption generation failed for asset {task.asset_id} (attempt {task.attempts}): {error_msg}")
            
            task.updated_at = datetime.now().isoformat()
            self.save_state()
            
            return task.status == 'completed'
            
        except Exception as e:
            error_msg = f"Error executing caption task: {e}"
            self.logger.error(error_msg)
            
            task.error_message = error_msg
            if task.attempts >= self.max_retries:
                task.status = 'failed'
            else:
                task.status = 'pending'
            
            task.updated_at = datetime.now().isoformat()
            self.save_state()
            
            return False
    
    def run_caption_generation(self, max_tasks: Optional[int] = None):
        """Run caption generation process."""
        if not self.check_backend_health():
            raise Exception("Backend is not available")
        
        self.logger.info("Starting caption generation process")
        
        # Discover new assets
        new_assets = self.discover_assets_needing_captions()
        if new_assets:
            self.create_caption_tasks(new_assets)
            self.logger.info(f"Created tasks for {len(new_assets)} new assets")
        
        # Process pending tasks
        batch_size = max_tasks or self.batch_size
        pending_tasks = self.get_pending_tasks(limit=batch_size)
        
        if not pending_tasks:
            self.logger.info("No pending caption tasks")
            return
        
        self.logger.info(f"Processing {len(pending_tasks)} caption tasks")
        
        success_count = 0
        for i, task in enumerate(pending_tasks, 1):
            self.logger.info(f"Processing task {i}/{len(pending_tasks)}")
            
            if self.execute_caption_task(task):
                success_count += 1
            
            # Small delay between tasks to avoid overwhelming the backend
            time.sleep(2)
        
        self.logger.info(f"Caption generation complete: {success_count}/{len(pending_tasks)} successful")
    
    def get_caption_statistics(self) -> Dict:
        """Get comprehensive caption statistics."""
        stats = {
            'total_tasks': len(self.task_state),
            'by_status': {},
            'performance': {
                'avg_processing_time_ms': 0,
                'total_processing_time_ms': 0
            },
            'recent_activity': {}
        }
        
        processing_times = []
        
        # Count by status and collect performance data
        for task in self.task_state.values():
            status = task.status
            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1
            
            if task.processing_time_ms:
                processing_times.append(task.processing_time_ms)
        
        # Calculate performance metrics
        if processing_times:
            stats['performance']['avg_processing_time_ms'] = sum(processing_times) / len(processing_times)
            stats['performance']['total_processing_time_ms'] = sum(processing_times)
        
        # Recent activity (last 24 hours)
        cutoff_time = datetime.now() - timedelta(hours=24)
        recent_tasks = [
            task for task in self.task_state.values()
            if datetime.fromisoformat(task.updated_at) > cutoff_time
        ]
        stats['recent_activity']['total'] = len(recent_tasks)
        stats['recent_activity']['completed'] = len([
            t for t in recent_tasks if t.status == 'completed'
        ])
        
        return stats
    
    def print_status_report(self):
        """Print comprehensive status report."""
        stats = self.get_caption_statistics()
        
        print("\n" + "="*60)
        print("CAPTION GENERATION STATUS REPORT")
        print("="*60)
        
        print(f"\nTASK STATISTICS:")
        print(f"  Total tasks: {stats['total_tasks']}")
        
        print(f"\nBy Status:")
        for status, count in stats['by_status'].items():
            print(f"  {status}: {count}")
        
        print(f"\nPERFORMACE:")
        avg_time = stats['performance']['avg_processing_time_ms']
        total_time = stats['performance']['total_processing_time_ms']
        print(f"  Average processing time: {avg_time:.0f}ms")
        print(f"  Total processing time: {total_time/1000:.1f}s")
        
        print(f"\nRecent Activity (24h):")
        print(f"  Total: {stats['recent_activity']['total']}")
        print(f"  Completed: {stats['recent_activity']['completed']}")
        
        # Sample captions
        completed_tasks = [t for t in self.task_state.values() if t.status == 'completed' and t.caption_text]
        if completed_tasks:
            print(f"\nSample Captions:")
            for i, task in enumerate(completed_tasks[-3:], 1):  # Show last 3
                caption = task.caption_text[:80] + "..." if len(task.caption_text) > 80 else task.caption_text
                print(f"  {i}. {caption}")
        
        print("="*60)


def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='AI Caption Generation Processor')
    parser.add_argument('--backend-url', default='http://localhost:8000', help='Backend URL')
    parser.add_argument('--max-tasks', type=int, help='Maximum tasks to process')
    parser.add_argument('--continuous', action='store_true', help='Run continuously')
    parser.add_argument('--interval', type=int, default=300, help='Interval between cycles (seconds)')
    parser.add_argument('--status', action='store_true', help='Show status report only')
    
    args = parser.parse_args()
    
    processor = CaptionProcessor(args.backend_url)
    
    try:
        if args.status:
            processor.print_status_report()
        elif args.continuous:
            print(f"Starting continuous caption generation (interval: {args.interval}s)")
            while True:
                processor.run_caption_generation(args.max_tasks)
                time.sleep(args.interval)
        else:
            processor.run_caption_generation(args.max_tasks)
            processor.print_status_report()
            
    except KeyboardInterrupt:
        print("\nCaption generation stopped by user")
    except Exception as e:
        print(f"Error: {e}")
        processor.logger.error(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
