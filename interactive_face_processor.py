#!/usr/bin/env python3
"""
Interactive Face Processing System
Integrates with main service panel for on-demand face detection and recognition
"""

import sqlite3
import os
import time
import json
from datetime import datetime
import subprocess
import argparse

class InteractiveFaceProcessor:
    def __init__(self):
        # Load Drive E configuration
        config_path = "config/drive_e_paths.json"
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
            self.db_path = config["databases"]["app"]
        else:
            # Fallback to local database
            self.db_path = "app.db"
        
    def get_unprocessed_count(self):
        """Get count of images without face detection"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(DISTINCT a.id) 
                FROM assets a 
                LEFT JOIN face_detections f ON a.id = f.asset_id
                WHERE a.mime LIKE 'image/%' AND a.id > 5 AND f.asset_id IS NULL
            """)
            
            unprocessed = cursor.fetchone()[0]
            conn.close()
            return unprocessed
            
        except Exception as e:
            print(f"❌ Database error: {e}")
            return 0
    
    def get_processing_stats(self):
        """Get current processing statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Total images
            cursor.execute("SELECT COUNT(*) FROM assets WHERE mime LIKE 'image/%' AND id > 5")
            total_images = cursor.fetchone()[0]
            
            # Processed images (with face detections)
            cursor.execute("SELECT COUNT(DISTINCT asset_id) FROM face_detections")
            processed_images = cursor.fetchone()[0]
            
            # Total faces detected
            cursor.execute("SELECT COUNT(*) FROM face_detections")
            total_faces = cursor.fetchone()[0]
            
            # Images with embeddings
            cursor.execute("SELECT COUNT(DISTINCT asset_id) FROM face_detections WHERE embedding_path IS NOT NULL")
            images_with_embeddings = cursor.fetchone()[0]
            
            # Total embeddings
            cursor.execute("SELECT COUNT(*) FROM face_detections WHERE embedding_path IS NOT NULL")
            total_embeddings = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_images': total_images,
                'processed_images': processed_images,
                'unprocessed_images': total_images - processed_images,
                'total_faces': total_faces,
                'images_with_embeddings': images_with_embeddings,
                'total_embeddings': total_embeddings,
                'completion_rate': (processed_images / total_images * 100) if total_images > 0 else 0
            }
            
        except Exception as e:
            print(f"❌ Database error: {e}")
            return None
    
    def check_service_status(self):
        """Check if the unified face service is running"""
        import requests
        
        try:
            session = requests.Session()
            session.proxies = {'http': None, 'https': None}
            response = session.get("http://172.22.61.27:8003/status", timeout=5)
            
            if response.status_code == 200:
                status = response.json()
                return True, status
            else:
                return False, {"error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return False, {"error": str(e)}
    
    def delegate_to_enhanced_orchestrator(self, batch_size=0, max_workers=3, incremental=False):
        """Delegate heavy processing to enhanced orchestrator"""
        
        print("🎯 Delegating to Enhanced Face Orchestrator...")
        
        # Show pre-processing status
        stats = self.get_processing_stats()
        if stats:
            print(f"📊 Current Status:")
            print(f"   Total images: {stats['total_images']:,}")
            print(f"   Processed: {stats['processed_images']:,} ({stats['completion_rate']:.1f}%)")
            print(f"   Unprocessed: {stats['unprocessed_images']:,}")
        
        # Build command for enhanced orchestrator
        cmd = [".venv/Scripts/python.exe", "enhanced_face_orchestrator_unified.py"]
        
        if batch_size > 0:
            cmd.extend(["--batch-size", str(batch_size)])
        if max_workers != 3:
            cmd.extend(["--max-workers", str(max_workers)])
        
        try:
            # Run the enhanced orchestrator
            result = subprocess.run(cmd, capture_output=False, text=True)
            
            if result.returncode == 0:
                print("✅ Enhanced processing completed successfully!")
                
                # Show post-processing status
                stats = self.get_processing_stats()
                if stats:
                    print(f"📊 Updated Status:")
                    print(f"   Processed: {stats['processed_images']:,} ({stats['completion_rate']:.1f}%)")
                    print(f"   Unprocessed: {stats['unprocessed_images']:,}")
                    
            else:
                print(f"❌ Enhanced processing failed with exit code: {result.returncode}")
                
        except Exception as e:
            print(f"❌ Error running enhanced orchestrator: {e}")
            return False
            
        return True
    
    def process_new_assets(self, batch_size=0, max_workers=3):
        """Process newly added assets"""
        
        print("🔍 INTERACTIVE FACE PROCESSING")
        print("=" * 50)
        
        # Check service status first
        service_running, service_info = self.check_service_status()
        
        if not service_running:
            print(f"❌ Face service not running: {service_info.get('error', 'Unknown error')}")
            print("Please start the service first:")
            print("   wsl -d Ubuntu-22.04 -- bash -c \"cd /mnt/c/Users/yanbo/wSpace/vlm-photo-engine/LVFace && source .venv-cuda124-wsl/bin/activate && python unified_scrfd_service.py\"")
            return False
        
        print(f"✅ Face service running: {service_info.get('service', 'Unknown')}")
        
        # Get processing stats
        stats = self.get_processing_stats()
        if not stats:
            return False
        
        print(f"\n📊 Current Status:")
        print(f"   Total images: {stats['total_images']:,}")
        print(f"   Processed: {stats['processed_images']:,} ({stats['completion_rate']:.1f}%)")
        print(f"   Unprocessed: {stats['unprocessed_images']:,}")
        print(f"   Total faces detected: {stats['total_faces']:,}")
        print(f"   Images with embeddings: {stats['images_with_embeddings']:,}")
        print(f"   Total embeddings: {stats['total_embeddings']:,}")
        
        if stats['unprocessed_images'] == 0:
            print(f"\n✅ All images already processed!")
            return True
        
        # Ask for confirmation if processing many images
        if stats['unprocessed_images'] > 100:
            print(f"\n⚠️  About to process {stats['unprocessed_images']:,} images")
            print(f"   Estimated time: {stats['unprocessed_images'] / 8:.1f} minutes")
            
            response = input("Continue? (y/N): ").strip().lower()
            if response != 'y':
                print("Processing cancelled.")
                return False
        
        # Run the orchestrator
        print(f"\n🚀 Starting face processing...")
        
        cmd = [
            ".venv\\Scripts\\python.exe",
            "enhanced_face_orchestrator_unified.py"
        ]
        
        if batch_size > 0:
            cmd.extend(["--batch-size", str(batch_size)])
        
        cmd.extend(["--max-workers", str(max_workers)])
        
        try:
            # Run the orchestrator
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
            
            if result.returncode == 0:
                print(f"✅ Processing completed successfully!")
                
                # Show updated stats
                new_stats = self.get_processing_stats()
                if new_stats:
                    print(f"\n📊 Updated Status:")
                    print(f"   Processed: {new_stats['processed_images']:,} ({new_stats['completion_rate']:.1f}%)")
                    print(f"   Remaining: {new_stats['unprocessed_images']:,}")
                
                return True
            else:
                print(f"❌ Processing failed with return code: {result.returncode}")
                print(f"Error: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Failed to run processing: {e}")
            return False
    
    def show_recent_results(self, limit=10):
        """Show recent face detection results"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT a.path, COUNT(f.id) as face_count,
                       SUM(CASE WHEN f.embedding_path IS NOT NULL THEN 1 ELSE 0 END) as embedding_count
                FROM assets a
                JOIN face_detections f ON a.id = f.asset_id
                WHERE a.mime LIKE 'image/%'
                GROUP BY a.id, a.path
                ORDER BY a.id DESC
                LIMIT ?
            """, (limit,))
            
            results = cursor.fetchall()
            conn.close()
            
            if results:
                print(f"\n📸 Recent Face Detection Results:")
                for path, face_count, embedding_count in results:
                    filename = os.path.basename(path)
                    emb_status = f"{embedding_count}/{face_count} embeddings" if face_count > 0 else "no embeddings"
                    print(f"   {filename}: {face_count} faces, {emb_status}")
            else:
                print(f"\n📸 No recent results found")
                
        except Exception as e:
            print(f"❌ Error showing results: {e}")

def main():
    parser = argparse.ArgumentParser(description='Interactive Face Processing System')
    parser.add_argument('--status', action='store_true', help='Show current processing status')
    parser.add_argument('--process', action='store_true', help='Process new/unprocessed assets')
    parser.add_argument('--batch-size', type=int, default=0, help='Batch size for processing (0=unlimited)')
    parser.add_argument('--max-workers', type=int, default=3, help='Number of worker threads')
    parser.add_argument('--recent', type=int, default=10, help='Show recent results (number of images)')
    parser.add_argument('--incremental', action='store_true', help='Process only unprocessed images')
    
    args = parser.parse_args()
    
    processor = InteractiveFaceProcessor()
    
    if args.status:
        stats = processor.get_processing_stats()
        if stats:
            print(f"📊 Face Processing Status:")
            print(f"   Total images: {stats['total_images']:,}")
            print(f"   Processed: {stats['processed_images']:,} ({stats['completion_rate']:.1f}%)")
            print(f"   Unprocessed: {stats['unprocessed_images']:,}")
            print(f"   Total faces: {stats['total_faces']:,}")
            print(f"   Total embeddings: {stats['total_embeddings']:,}")
    
    elif args.process:
        # Delegate heavy processing to enhanced orchestrator
        processor.delegate_to_enhanced_orchestrator(
            batch_size=args.batch_size, 
            max_workers=args.max_workers, 
            incremental=args.incremental
        )
    
    else:
        # Interactive mode
        print("🎮 Interactive Face Processing System")
        print("Commands:")
        print("  --status: Show processing status")
        print("  --process: Process new assets")
        print("  --recent N: Show recent N results")
        
        processor.show_recent_results(args.recent)

if __name__ == "__main__":
    main()
