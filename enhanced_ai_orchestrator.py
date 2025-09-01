#!/usr/bin/env python3
"""
Enhanced AI Orchestrator with Real-time Progress Monitoring

Features:
- Real-time progress bars using tqdm
- Live status dashboard
- Task completion counters
- GPU utilization monitoring
- Processing rate metrics
- Current file being processed indicator
"""

import json
import time
import logging
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import requests
from tqdm import tqdm
import os

class EnhancedAIOrchestrator:
    """Enhanced orchestrator with real-time progress monitoring."""
    
    def __init__(self, backend_url: str = "http://localhost:8000"):
        self.backend_url = backend_url
        self.state_file = "ai_orchestrator_state.json"
        self.running = False
        self.progress_thread = None
        
        # Progress tracking
        self.progress_data = {
            'total_files': 0,
            'processed_files': 0,
            'current_file': '',
            'processing_rate': 0,
            'gpu_memory_used': 0,
            'start_time': None,
            'tasks_completed': 0,
            'tasks_pending': 0,
            'tasks_failed': 0
        }
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('enhanced_ai_orchestrator.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('EnhancedAIOrchestrator')
    
    def get_backend_stats(self) -> Dict:
        """Get current backend statistics."""
        try:
            response = requests.get(f"{self.backend_url}/stats", timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.logger.debug(f"Could not get backend stats: {e}")
        return {}
    
    def get_task_stats(self) -> Dict:
        """Get current task statistics."""
        try:
            response = requests.get(f"{self.backend_url}/tasks/stats", timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.logger.debug(f"Could not get task stats: {e}")
        return {}
    
    def get_gpu_stats(self) -> Dict:
        """Get GPU utilization statistics."""
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total,utilization.gpu', 
                                   '--format=csv,noheader,nounits'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                gpu_stats = []
                for line in lines:
                    memory_used, memory_total, gpu_util = map(int, line.split(', '))
                    gpu_stats.append({
                        'memory_used': memory_used,
                        'memory_total': memory_total,
                        'gpu_utilization': gpu_util
                    })
                return {'gpus': gpu_stats}
        except Exception as e:
            self.logger.debug(f"Could not get GPU stats: {e}")
        return {}
    
    def update_progress_data(self):
        """Update progress tracking data."""
        # Get backend stats
        backend_stats = self.get_backend_stats()
        task_stats = self.get_task_stats()
        gpu_stats = self.get_gpu_stats()
        
        # Update progress data
        if backend_stats:
            self.progress_data['total_files'] = backend_stats.get('total_assets', 0)
            self.progress_data['processed_files'] = backend_stats.get('processed_assets', 0)
        
        if task_stats:
            self.progress_data['tasks_completed'] = task_stats.get('completed', 0)
            self.progress_data['tasks_pending'] = task_stats.get('pending', 0)
            self.progress_data['tasks_failed'] = task_stats.get('failed', 0)
            self.progress_data['current_file'] = task_stats.get('current_task', '')
        
        if gpu_stats and gpu_stats.get('gpus'):
            # Focus on RTX 3090 (GPU 1)
            if len(gpu_stats['gpus']) > 1:
                rtx_3090 = gpu_stats['gpus'][1]
                self.progress_data['gpu_memory_used'] = rtx_3090['memory_used']
                self.progress_data['gpu_utilization'] = rtx_3090['gpu_utilization']
    
    def print_live_dashboard(self):
        """Print live status dashboard."""
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print("🚀 VLM PHOTO ENGINE - LIVE AI PROCESSING DASHBOARD")
        print("=" * 80)
        
        # Time info
        if self.progress_data['start_time']:
            elapsed = datetime.now() - self.progress_data['start_time']
            print(f"⏱️  Running Time: {str(elapsed).split('.')[0]}")
        
        # File progress
        total = self.progress_data['total_files']
        processed = self.progress_data['processed_files']
        if total > 0:
            percentage = (processed / total) * 100
            print(f"📁 Files: {processed:,}/{total:,} ({percentage:.1f}%)")
            
            # Progress bar for files
            bar_width = 50
            filled = int(bar_width * processed / total)
            bar = "█" * filled + "░" * (bar_width - filled)
            print(f"   [{bar}]")
        
        # Task progress
        completed = self.progress_data['tasks_completed']
        pending = self.progress_data['tasks_pending']
        failed = self.progress_data['tasks_failed']
        total_tasks = completed + pending + failed
        
        if total_tasks > 0:
            print(f"\n🔧 Tasks: {completed:,} completed, {pending:,} pending, {failed:,} failed")
            
            # Progress bar for tasks
            if total_tasks > 0:
                task_percentage = (completed / total_tasks) * 100
                bar_width = 50
                filled = int(bar_width * completed / total_tasks)
                bar = "█" * filled + "░" * (bar_width - filled)
                print(f"   [{bar}] {task_percentage:.1f}%")
        
        # Current processing
        current = self.progress_data['current_file']
        if current:
            # Truncate long filenames
            if len(current) > 60:
                current = "..." + current[-57:]
            print(f"\n🔄 Processing: {current}")
        
        # GPU utilization
        gpu_mem = self.progress_data.get('gpu_memory_used', 0)
        gpu_util = self.progress_data.get('gpu_utilization', 0)
        if gpu_mem > 0:
            print(f"\n🎮 RTX 3090: {gpu_mem:,}MB VRAM, {gpu_util}% GPU Utilization")
            
            # GPU memory bar (out of 24GB)
            gpu_percentage = (gpu_mem / 24576) * 100
            bar_width = 30
            filled = int(bar_width * gpu_mem / 24576)
            bar = "█" * filled + "░" * (bar_width - filled)
            print(f"   VRAM: [{bar}] {gpu_percentage:.1f}%")
        
        # Processing rate
        if self.progress_data['start_time'] and processed > 0:
            elapsed_seconds = (datetime.now() - self.progress_data['start_time']).total_seconds()
            rate = processed / elapsed_seconds if elapsed_seconds > 0 else 0
            if rate > 0:
                remaining = (total - processed) / rate if rate > 0 else 0
                eta = datetime.now() + timedelta(seconds=remaining)
                print(f"\n📊 Rate: {rate:.2f} files/sec")
                print(f"⏰ ETA: {eta.strftime('%H:%M:%S')}")
        
        print("=" * 80)
        print("Press Ctrl+C to stop monitoring")
    
    def progress_monitor_loop(self):
        """Background thread for progress monitoring."""
        while self.running:
            try:
                self.update_progress_data()
                self.print_live_dashboard()
                time.sleep(2)  # Update every 2 seconds
            except Exception as e:
                self.logger.error(f"Error in progress monitor: {e}")
                time.sleep(5)
    
    def start_progress_monitoring(self):
        """Start the progress monitoring thread."""
        self.running = True
        self.progress_data['start_time'] = datetime.now()
        self.progress_thread = threading.Thread(target=self.progress_monitor_loop)
        self.progress_thread.daemon = True
        self.progress_thread.start()
        self.logger.info("Progress monitoring started")
    
    def stop_progress_monitoring(self):
        """Stop the progress monitoring thread."""
        self.running = False
        if self.progress_thread:
            self.progress_thread.join(timeout=5)
        self.logger.info("Progress monitoring stopped")
    
    def run_with_monitoring(self):
        """Run AI processing with live progress monitoring."""
        try:
            self.logger.info("Starting AI processing with live monitoring...")
            
            # Start progress monitoring
            self.start_progress_monitoring()
            
            # Run the original AI orchestrator
            result = subprocess.run([
                sys.executable, 'ai_orchestrator.py', '--continuous'
            ], cwd=Path.cwd())
            
            return result.returncode == 0
            
        except KeyboardInterrupt:
            self.logger.info("Processing interrupted by user")
            return False
        except Exception as e:
            self.logger.error(f"Error during processing: {e}")
            return False
        finally:
            self.stop_progress_monitoring()

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced AI Orchestrator with Progress Monitoring')
    parser.add_argument('--backend-url', default='http://localhost:8000',
                       help='Backend URL (default: http://localhost:8000)')
    parser.add_argument('--monitor-only', action='store_true',
                       help='Only show progress monitoring, do not start processing')
    
    args = parser.parse_args()
    
    orchestrator = EnhancedAIOrchestrator(backend_url=args.backend_url)
    
    if args.monitor_only:
        # Just monitor existing processing
        try:
            orchestrator.start_progress_monitoring()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            orchestrator.stop_progress_monitoring()
    else:
        # Run processing with monitoring
        success = orchestrator.run_with_monitoring()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
