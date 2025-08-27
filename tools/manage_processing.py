#!/usr/bin/env python3
"""
Drive E Processing Management Tool

View processing status, manage checkpoints, and analyze processing history.
"""

import sqlite3
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sys

class ProcessingManager:
    """Manager for Drive E processing data."""
    
    def __init__(self, db_path: str = "drive_e_processing.db"):
        self.db_path = Path(db_path)
        
    def get_processing_stats(self) -> Dict:
        """Get overall processing statistics."""
        if not self.db_path.exists():
            return {"error": "No processing database found"}
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Overall stats
        cursor.execute("SELECT COUNT(*) FROM processing_history")
        total_files = cursor.fetchone()[0]
        
        cursor.execute("SELECT processing_status, COUNT(*) FROM processing_history GROUP BY processing_status")
        status_counts = dict(cursor.fetchall())
        
        # Session stats
        cursor.execute("""
            SELECT session_id, start_time, end_time, total_files, completed_files, failed_files, status
            FROM processing_sessions 
            ORDER BY start_time DESC
        """)
        sessions = cursor.fetchall()
        
        conn.close()
        
        return {
            "total_files": total_files,
            "status_counts": status_counts,
            "sessions": sessions
        }
    
    def get_failed_files(self, limit: int = 50) -> List[Dict]:
        """Get list of failed files with error messages."""
        if not self.db_path.exists():
            return []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT file_path, error_message, last_processed, session_id
            FROM processing_history 
            WHERE processing_status = 'failed'
            ORDER BY last_processed DESC
            LIMIT ?
        """, (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "file_path": row[0],
                "error_message": row[1],
                "last_processed": row[2],
                "session_id": row[3]
            })
        
        conn.close()
        return results
    
    def get_processing_history(self, file_path: str) -> Optional[Dict]:
        """Get processing history for a specific file."""
        if not self.db_path.exists():
            return None
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM processing_history 
            WHERE file_path = ?
            ORDER BY last_processed DESC
        """, (file_path,))
        
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, row))
        else:
            result = None
        
        conn.close()
        return result
    
    def reset_failed_files(self) -> int:
        """Reset failed files to allow reprocessing."""
        if not self.db_path.exists():
            return 0
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("UPDATE processing_history SET processing_status = 'pending' WHERE processing_status = 'failed'")
        updated = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return updated
    
    def cleanup_old_sessions(self, keep_days: int = 30) -> int:
        """Clean up old processing sessions."""
        if not self.db_path.exists():
            return 0
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=keep_days)).isoformat()
        
        cursor.execute("""
            DELETE FROM processing_history 
            WHERE last_processed < ? AND processing_status IN ('completed', 'failed')
        """, (cutoff_date,))
        
        deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def list_checkpoints(self) -> List[Dict]:
        """List available checkpoint files."""
        checkpoints = []
        
        for checkpoint_file in Path('.').glob('drive_e_checkpoint_*.json'):
            try:
                with open(checkpoint_file, 'r') as f:
                    data = json.load(f)
                
                checkpoints.append({
                    "file": str(checkpoint_file),
                    "session_id": data.get('session_id'),
                    "timestamp": data.get('timestamp'),
                    "total_files": data.get('total_files'),
                    "processed_files": data.get('processed_files'),
                    "success_rate": (data.get('successful_files', 0) / max(data.get('processed_files', 1), 1)) * 100
                })
            except Exception as e:
                checkpoints.append({
                    "file": str(checkpoint_file),
                    "error": str(e)
                })
        
        return sorted(checkpoints, key=lambda x: x.get('timestamp', ''), reverse=True)

def main():
    parser = argparse.ArgumentParser(description="Manage Drive E processing")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show processing status')
    status_parser.add_argument('--detailed', action='store_true', help='Show detailed status')
    
    # Failed command
    failed_parser = subparsers.add_parser('failed', help='Show failed files')
    failed_parser.add_argument('--limit', type=int, default=50, help='Limit number of files shown')
    
    # History command
    history_parser = subparsers.add_parser('history', help='Show file processing history')
    history_parser.add_argument('file_path', help='Path to file to check')
    
    # Reset command
    reset_parser = subparsers.add_parser('reset-failed', help='Reset failed files for reprocessing')
    
    # Checkpoints command
    checkpoints_parser = subparsers.add_parser('checkpoints', help='List checkpoint files')
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up old processing records')
    cleanup_parser.add_argument('--days', type=int, default=30, help='Keep records newer than N days')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = ProcessingManager()
    
    if args.command == 'status':
        stats = manager.get_processing_stats()
        
        if "error" in stats:
            print(f"❌ {stats['error']}")
            return
        
        print("📊 Drive E Processing Status")
        print("=" * 40)
        print(f"Total files tracked: {stats['total_files']}")
        print()
        
        status_counts = stats.get('status_counts', {})
        for status, count in status_counts.items():
            emoji = {
                'completed': '✅',
                'failed': '❌',
                'processing': '🔄',
                'pending': '⏳'
            }.get(status, '📄')
            print(f"{emoji} {status.capitalize()}: {count}")
        
        print()
        print("📅 Recent Sessions:")
        for session in stats.get('sessions', [])[:5]:
            session_id, start_time, end_time, total, completed, failed, status = session
            print(f"   {session_id}: {completed}/{total} files, {failed} failed ({status})")
    
    elif args.command == 'failed':
        failed_files = manager.get_failed_files(args.limit)
        
        if not failed_files:
            print("✅ No failed files found!")
            return
        
        print(f"❌ Failed Files (showing {len(failed_files)}):")
        print("=" * 60)
        
        for i, file_info in enumerate(failed_files, 1):
            print(f"{i}. {file_info['file_path']}")
            print(f"   Error: {file_info['error_message']}")
            print(f"   Last attempt: {file_info['last_processed']}")
            print()
    
    elif args.command == 'history':
        history = manager.get_processing_history(args.file_path)
        
        if not history:
            print(f"❌ No processing history found for: {args.file_path}")
            return
        
        print(f"📋 Processing History: {args.file_path}")
        print("=" * 60)
        
        for key, value in history.items():
            if value is not None:
                print(f"{key}: {value}")
    
    elif args.command == 'reset-failed':
        count = manager.reset_failed_files()
        print(f"🔄 Reset {count} failed files for reprocessing")
    
    elif args.command == 'checkpoints':
        checkpoints = manager.list_checkpoints()
        
        if not checkpoints:
            print("📄 No checkpoint files found")
            return
        
        print("📋 Available Checkpoints:")
        print("=" * 60)
        
        for i, checkpoint in enumerate(checkpoints, 1):
            if "error" in checkpoint:
                print(f"{i}. {checkpoint['file']} - ERROR: {checkpoint['error']}")
            else:
                print(f"{i}. {checkpoint['file']}")
                print(f"   Session: {checkpoint['session_id']}")
                print(f"   Time: {checkpoint['timestamp']}")
                print(f"   Progress: {checkpoint['processed_files']}/{checkpoint['total_files']} " +
                      f"({checkpoint['success_rate']:.1f}% success)")
                print()
    
    elif args.command == 'cleanup':
        count = manager.cleanup_old_sessions(args.days)
        print(f"🧹 Cleaned up {count} old processing records")

if __name__ == "__main__":
    main()
