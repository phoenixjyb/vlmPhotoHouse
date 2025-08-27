#!/usr/bin/env python3
"""
VLM Photo Engine - Master AI Orchestrator

This script orchestrates the complete AI processing pipeline for Drive E files:
1. Backend Integration (ingestion)
2. AI Task Management (caption, face, embedding, etc.)
3. Progress monitoring and reporting
4. Incremental processing with state management

Features:
- Orchestrates all AI processing components
- Handles dependencies between tasks
- Provides comprehensive monitoring
- Supports both single-run and continuous modes
- Automatic recovery and retry logic
"""

import json
import time
import logging
import subprocess
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import requests

class AIOrchestrator:
    """Master orchestrator for AI processing pipeline."""
    
    def __init__(self, backend_url: str = "http://localhost:8000"):
        self.backend_url = backend_url
        self.state_file = "ai_orchestrator_state.json"
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('ai_orchestrator.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('AIOrchestrator')
        
        # Component scripts
        self.scripts = {
            'ingestion': 'drive_e_backend_integrator.py',
            'captions': 'caption_processor.py',
            'ai_tasks': 'ai_task_manager.py'
        }
        
        # Load orchestrator state
        self.orchestrator_state = self.load_orchestrator_state()
        
    def load_orchestrator_state(self) -> Dict:
        """Load orchestrator state."""
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                'last_full_run': None,
                'last_ingestion': None,
                'last_caption_run': None,
                'last_ai_task_run': None,
                'total_runs': 0,
                'pipeline_stats': {}
            }
        except Exception as e:
            self.logger.error(f"Error loading orchestrator state: {e}")
            return {}
    
    def save_orchestrator_state(self):
        """Save orchestrator state."""
        try:
            temp_file = f"{self.state_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(self.orchestrator_state, f, indent=2)
            Path(temp_file).replace(self.state_file)
        except Exception as e:
            self.logger.error(f"Error saving orchestrator state: {e}")
    
    def check_backend_health(self) -> bool:
        """Check if backend is healthy."""
        try:
            response = requests.get(f"{self.backend_url}/health", timeout=10)
            return response.status_code == 200
        except Exception:
            return False
    
    def get_backend_metrics(self) -> Dict:
        """Get backend metrics."""
        try:
            response = requests.get(f"{self.backend_url}/metrics", timeout=10)
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception:
            return {}
    
    def run_script(self, script_name: str, args: List[str] = None) -> Dict:
        """Run a component script and return results."""
        script_path = self.scripts.get(script_name)
        if not script_path:
            raise ValueError(f"Unknown script: {script_name}")
        
        if not Path(script_path).exists():
            raise FileNotFoundError(f"Script not found: {script_path}")
        
        # Build command
        cmd = [sys.executable, script_path]
        if args:
            cmd.extend(args)
        
        self.logger.info(f"Running {script_name}: {' '.join(cmd)}")
        
        try:
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            execution_time = time.time() - start_time
            
            return {
                'success': result.returncode == 0,
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'execution_time': execution_time
            }
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Script {script_name} timed out")
            return {
                'success': False,
                'returncode': -1,
                'stdout': '',
                'stderr': 'Script execution timed out',
                'execution_time': 3600
            }
        except Exception as e:
            self.logger.error(f"Error running script {script_name}: {e}")
            return {
                'success': False,
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
                'execution_time': 0
            }
    
    def run_ingestion_phase(self, max_dirs: Optional[int] = None) -> bool:
        """Run the ingestion phase."""
        self.logger.info("Starting ingestion phase")
        
        args = ['--batch-size', '5']  # Conservative batch size
        if max_dirs:
            args.extend(['--max-dirs', str(max_dirs)])
        
        result = self.run_script('ingestion', args)
        
        if result['success']:
            self.logger.info("Ingestion phase completed successfully")
            self.orchestrator_state['last_ingestion'] = datetime.now().isoformat()
        else:
            self.logger.error(f"Ingestion phase failed: {result['stderr']}")
        
        return result['success']
    
    def run_caption_phase(self, max_tasks: Optional[int] = None) -> bool:
        """Run the caption generation phase."""
        self.logger.info("Starting caption generation phase")
        
        args = []
        if max_tasks:
            args.extend(['--max-tasks', str(max_tasks)])
        
        result = self.run_script('captions', args)
        
        if result['success']:
            self.logger.info("Caption generation phase completed successfully")
            self.orchestrator_state['last_caption_run'] = datetime.now().isoformat()
        else:
            self.logger.error(f"Caption generation phase failed: {result['stderr']}")
        
        return result['success']
    
    def run_ai_tasks_phase(self, max_tasks: Optional[int] = None) -> bool:
        """Run the general AI tasks phase."""
        self.logger.info("Starting AI tasks phase")
        
        args = []
        if max_tasks:
            args.extend(['--max-tasks', str(max_tasks)])
        
        result = self.run_script('ai_tasks', args)
        
        if result['success']:
            self.logger.info("AI tasks phase completed successfully")
            self.orchestrator_state['last_ai_task_run'] = datetime.now().isoformat()
        else:
            self.logger.error(f"AI tasks phase failed: {result['stderr']}")
        
        return result['success']
    
    def run_full_pipeline(self, 
                         max_dirs: Optional[int] = None,
                         max_caption_tasks: Optional[int] = None,
                         max_ai_tasks: Optional[int] = None) -> Dict:
        """Run the complete AI processing pipeline."""
        
        if not self.check_backend_health():
            raise Exception("Backend is not available - please start the backend server first")
        
        self.logger.info("Starting full AI processing pipeline")
        pipeline_start = time.time()
        
        results = {
            'start_time': datetime.now().isoformat(),
            'phases': {},
            'success': False,
            'total_time': 0
        }
        
        try:
            # Phase 1: Ingestion
            self.logger.info("=" * 50)
            self.logger.info("PHASE 1: BACKEND INGESTION")
            self.logger.info("=" * 50)
            
            ingestion_success = self.run_ingestion_phase(max_dirs)
            results['phases']['ingestion'] = ingestion_success
            
            if not ingestion_success:
                self.logger.error("Ingestion phase failed, stopping pipeline")
                return results
            
            # Small pause between phases
            time.sleep(5)
            
            # Phase 2: Caption Generation
            self.logger.info("=" * 50)
            self.logger.info("PHASE 2: CAPTION GENERATION")
            self.logger.info("=" * 50)
            
            caption_success = self.run_caption_phase(max_caption_tasks)
            results['phases']['captions'] = caption_success
            
            # Continue even if captions fail
            if not caption_success:
                self.logger.warning("Caption generation had issues, but continuing with other AI tasks")
            
            # Small pause between phases
            time.sleep(5)
            
            # Phase 3: Other AI Tasks
            self.logger.info("=" * 50)
            self.logger.info("PHASE 3: AI TASKS (EMBEDDING, FACE, ETC.)")
            self.logger.info("=" * 50)
            
            ai_tasks_success = self.run_ai_tasks_phase(max_ai_tasks)
            results['phases']['ai_tasks'] = ai_tasks_success
            
            # Overall success if at least ingestion succeeded
            results['success'] = ingestion_success
            
            # Update orchestrator state
            self.orchestrator_state['last_full_run'] = datetime.now().isoformat()
            self.orchestrator_state['total_runs'] += 1
            
            # Store pipeline stats
            self.orchestrator_state['pipeline_stats'] = {
                'ingestion_success': ingestion_success,
                'caption_success': caption_success,
                'ai_tasks_success': ai_tasks_success,
                'total_time': time.time() - pipeline_start
            }
            
            self.save_orchestrator_state()
            
        except Exception as e:
            self.logger.error(f"Pipeline execution failed: {e}")
            results['error'] = str(e)
        
        results['total_time'] = time.time() - pipeline_start
        results['end_time'] = datetime.now().isoformat()
        
        self.logger.info("=" * 50)
        self.logger.info("PIPELINE EXECUTION COMPLETE")
        self.logger.info("=" * 50)
        
        return results
    
    def get_comprehensive_status(self) -> Dict:
        """Get comprehensive status across all components."""
        status = {
            'orchestrator': {
                'last_full_run': self.orchestrator_state.get('last_full_run'),
                'total_runs': self.orchestrator_state.get('total_runs', 0),
                'backend_healthy': self.check_backend_health()
            },
            'backend_metrics': self.get_backend_metrics(),
            'component_status': {}
        }
        
        # Get status from each component
        for component, script in self.scripts.items():
            try:
                result = self.run_script(component, ['--status'])
                status['component_status'][component] = {
                    'available': True,
                    'last_check': datetime.now().isoformat(),
                    'stdout': result['stdout']
                }
            except Exception as e:
                status['component_status'][component] = {
                    'available': False,
                    'error': str(e),
                    'last_check': datetime.now().isoformat()
                }
        
        return status
    
    def print_comprehensive_report(self):
        """Print a comprehensive status report."""
        status = self.get_comprehensive_status()
        
        print("\n" + "="*80)
        print("VLM PHOTO ENGINE - AI PROCESSING STATUS REPORT")
        print("="*80)
        
        # Orchestrator status
        print(f"\nORCHESTRATOR STATUS:")
        print(f"  Backend healthy: {status['orchestrator']['backend_healthy']}")
        print(f"  Total pipeline runs: {status['orchestrator']['total_runs']}")
        print(f"  Last full run: {status['orchestrator']['last_full_run']}")
        
        # Backend metrics
        backend_metrics = status['backend_metrics']
        if backend_metrics:
            print(f"\nBACKEND METRICS:")
            for key, value in backend_metrics.items():
                print(f"  {key}: {value}")
        
        # Component status
        print(f"\nCOMPONENT STATUS:")
        for component, comp_status in status['component_status'].items():
            print(f"  {component}: {'✓' if comp_status['available'] else '✗'}")
            if not comp_status['available']:
                print(f"    Error: {comp_status.get('error', 'Unknown')}")
        
        # Pipeline stats
        pipeline_stats = self.orchestrator_state.get('pipeline_stats', {})
        if pipeline_stats:
            print(f"\nLAST PIPELINE EXECUTION:")
            print(f"  Ingestion: {'✓' if pipeline_stats.get('ingestion_success') else '✗'}")
            print(f"  Captions: {'✓' if pipeline_stats.get('caption_success') else '✗'}")
            print(f"  AI Tasks: {'✓' if pipeline_stats.get('ai_tasks_success') else '✗'}")
            print(f"  Total time: {pipeline_stats.get('total_time', 0):.1f}s")
        
        print("="*80)


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='VLM Photo Engine AI Orchestrator')
    parser.add_argument('--backend-url', default='http://localhost:8000', help='Backend URL')
    parser.add_argument('--max-dirs', type=int, help='Maximum directories for ingestion')
    parser.add_argument('--max-caption-tasks', type=int, help='Maximum caption tasks')
    parser.add_argument('--max-ai-tasks', type=int, help='Maximum AI tasks')
    parser.add_argument('--continuous', action='store_true', help='Run continuously')
    parser.add_argument('--interval', type=int, default=1800, help='Interval between runs (seconds)')
    parser.add_argument('--status', action='store_true', help='Show comprehensive status')
    parser.add_argument('--ingestion-only', action='store_true', help='Run ingestion phase only')
    parser.add_argument('--captions-only', action='store_true', help='Run caption phase only')
    parser.add_argument('--ai-tasks-only', action='store_true', help='Run AI tasks phase only')
    
    args = parser.parse_args()
    
    orchestrator = AIOrchestrator(args.backend_url)
    
    try:
        if args.status:
            orchestrator.print_comprehensive_report()
            
        elif args.ingestion_only:
            success = orchestrator.run_ingestion_phase(args.max_dirs)
            print(f"Ingestion phase: {'SUCCESS' if success else 'FAILED'}")
            
        elif args.captions_only:
            success = orchestrator.run_caption_phase(args.max_caption_tasks)
            print(f"Caption phase: {'SUCCESS' if success else 'FAILED'}")
            
        elif args.ai_tasks_only:
            success = orchestrator.run_ai_tasks_phase(args.max_ai_tasks)
            print(f"AI tasks phase: {'SUCCESS' if success else 'FAILED'}")
            
        elif args.continuous:
            print(f"Starting continuous AI processing (interval: {args.interval}s)")
            while True:
                results = orchestrator.run_full_pipeline(
                    max_dirs=args.max_dirs,
                    max_caption_tasks=args.max_caption_tasks,
                    max_ai_tasks=args.max_ai_tasks
                )
                
                print(f"\nPipeline run completed: {'SUCCESS' if results['success'] else 'FAILED'}")
                print(f"Total time: {results['total_time']:.1f}s")
                
                time.sleep(args.interval)
        else:
            # Single run
            results = orchestrator.run_full_pipeline(
                max_dirs=args.max_dirs,
                max_caption_tasks=args.max_caption_tasks,
                max_ai_tasks=args.max_ai_tasks
            )
            
            print(f"\nPipeline execution: {'SUCCESS' if results['success'] else 'FAILED'}")
            print(f"Total time: {results['total_time']:.1f}s")
            
            # Show final status
            orchestrator.print_comprehensive_report()
            
    except KeyboardInterrupt:
        print("\nAI processing stopped by user")
    except Exception as e:
        print(f"Error: {e}")
        orchestrator.logger.error(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
