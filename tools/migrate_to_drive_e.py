#!/usr/bin/env python3
"""
Migration Script: Move Data Assets to Drive E:
Separates code from data by moving all assets to E:\VLM_DATA\
"""

import os
import shutil
import sqlite3
from pathlib import Path
import json
from datetime import datetime

class VLMDataMigrator:
    def __init__(self):
        self.workspace_root = Path("C:/Users/yanbo/wSpace/vlm-photo-engine/vlmPhotoHouse")
        self.drive_e_root = Path("E:/VLM_DATA")
        self.migration_log = []
        
    def setup_drive_e_structure(self):
        """Create proper directory structure on Drive E"""
        directories = [
            "databases",
            "embeddings/faces",
            "embeddings/images", 
            "derived/thumbnails",
            "derived/captions",
            "derived/analytics",
            "logs",
            "temp",
            "verification",
            "test_assets",
            "backups"
        ]
        
        for dir_path in directories:
            full_path = self.drive_e_root / dir_path
            full_path.mkdir(parents=True, exist_ok=True)
            self.log(f"Created directory: {full_path}")
    
    def migrate_databases(self):
        """Move all database files to E:\VLM_DATA\databases\"""
        db_files = [
            "app.db",
            "drive_e_processing.db", 
            "metadata.sqlite"
        ]
        
        target_dir = self.drive_e_root / "databases"
        
        for db_file in db_files:
            source = self.workspace_root / db_file
            if source.exists():
                target = target_dir / db_file
                shutil.move(str(source), str(target))
                self.log(f"Moved database: {source} -> {target}")
                
                # Create symlink back to workspace for code compatibility
                try:
                    os.symlink(str(target), str(source))
                    self.log(f"Created symlink: {source} -> {target}")
                except OSError as e:
                    self.log(f"Could not create symlink for {source}: {e}")
    
    def migrate_embeddings(self):
        """Move embeddings folder to E:\VLM_DATA\embeddings\faces\"""
        source_dir = self.workspace_root / "embeddings"
        target_dir = self.drive_e_root / "embeddings" / "faces"
        
        if source_dir.exists():
            # Count files before migration
            file_count = len(list(source_dir.glob("*.json")))
            self.log(f"Migrating {file_count} embedding files...")
            
            # Move the entire directory
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.move(str(source_dir), str(target_dir))
            self.log(f"Moved embeddings: {source_dir} -> {target_dir}")
            
            # Update database paths if needed
            self.update_embedding_paths()
    
    def migrate_derived_data(self):
        """Move derived data folder"""
        source_dir = self.workspace_root / "derived"
        target_dir = self.drive_e_root / "derived"
        
        if source_dir.exists():
            if target_dir.exists():
                # Merge directories
                self.merge_directories(source_dir, target_dir)
            else:
                shutil.move(str(source_dir), str(target_dir))
            self.log(f"Moved derived data: {source_dir} -> {target_dir}")
    
    def migrate_verification_results(self):
        """Move verification results"""
        source_dir = self.workspace_root / "verification_results"
        target_dir = self.drive_e_root / "verification"
        
        if source_dir.exists():
            if target_dir.exists():
                self.merge_directories(source_dir, target_dir)
            else:
                shutil.move(str(source_dir), str(target_dir))
            self.log(f"Moved verification results: {source_dir} -> {target_dir}")
    
    def migrate_test_assets(self):
        """Move test photos and sample videos"""
        test_items = [
            ("test_photos", "test_assets/photos"),
            ("sample_video", "test_assets/videos")
        ]
        
        for source_name, target_path in test_items:
            source_dir = self.workspace_root / source_name
            target_dir = self.drive_e_root / target_path
            
            if source_dir.exists():
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                if target_dir.exists():
                    self.merge_directories(source_dir, target_dir)
                else:
                    shutil.move(str(source_dir), str(target_dir))
                self.log(f"Moved test assets: {source_dir} -> {target_dir}")
    
    def migrate_logs_and_state(self):
        """Move log files and state files to appropriate locations"""
        log_files = list(self.workspace_root.glob("*.log"))
        state_files = list(self.workspace_root.glob("*_state.json"))
        monitoring_files = list(self.workspace_root.glob("gpu_monitoring_*.png"))
        
        logs_dir = self.drive_e_root / "logs"
        
        all_files = log_files + state_files + monitoring_files
        for file_path in all_files:
            target = logs_dir / file_path.name
            shutil.move(str(file_path), str(target))
            self.log(f"Moved log/state file: {file_path} -> {target}")
    
    def update_embedding_paths(self):
        """Update database paths to point to new embedding location"""
        db_path = self.drive_e_root / "databases" / "metadata.sqlite"
        if not db_path.exists():
            return
            
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Update embedding storage paths
            old_path = "embeddings/"
            new_path = "E:/VLM_DATA/embeddings/faces/"
            
            cursor.execute("""
                UPDATE embeddings 
                SET storage_path = REPLACE(storage_path, ?, ?)
                WHERE storage_path LIKE ?
            """, (old_path, new_path, f"{old_path}%"))
            
            rows_updated = cursor.rowcount
            conn.commit()
            conn.close()
            
            self.log(f"Updated {rows_updated} embedding paths in database")
            
        except Exception as e:
            self.log(f"Error updating database paths: {e}")
    
    def merge_directories(self, source, target):
        """Merge source directory into target directory"""
        for item in source.iterdir():
            target_item = target / item.name
            if item.is_dir():
                if target_item.exists():
                    self.merge_directories(item, target_item)
                else:
                    shutil.move(str(item), str(target_item))
            else:
                if target_item.exists():
                    # Create unique name for conflicting files
                    base_name = target_item.stem
                    suffix = target_item.suffix
                    counter = 1
                    while target_item.exists():
                        target_item = target / f"{base_name}_{counter}{suffix}"
                        counter += 1
                shutil.move(str(item), str(target_item))
    
    def create_drive_e_config(self):
        """Create configuration file pointing to Drive E locations"""
        config = {
            "vlm_data_root": "E:/VLM_DATA",
            "databases": {
                "metadata": "E:/VLM_DATA/databases/metadata.sqlite",
                "app": "E:/VLM_DATA/databases/app.db",
                "drive_e_processing": "E:/VLM_DATA/databases/drive_e_processing.db"
            },
            "embeddings": {
                "faces": "E:/VLM_DATA/embeddings/faces",
                "images": "E:/VLM_DATA/embeddings/images"
            },
            "derived": {
                "thumbnails": "E:/VLM_DATA/derived/thumbnails",
                "captions": "E:/VLM_DATA/derived/captions",
                "analytics": "E:/VLM_DATA/derived/analytics"
            },
            "logs": "E:/VLM_DATA/logs",
            "verification": "E:/VLM_DATA/verification",
            "test_assets": "E:/VLM_DATA/test_assets",
            "migration_date": datetime.now().isoformat()
        }
        
        config_path = self.workspace_root / "config" / "drive_e_paths.json"
        config_path.parent.mkdir(exist_ok=True)
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        self.log(f"Created Drive E configuration: {config_path}")
    
    def log(self, message):
        """Log migration steps"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        self.migration_log.append(log_entry)
    
    def save_migration_log(self):
        """Save migration log to Drive E"""
        log_path = self.drive_e_root / "logs" / f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_path, 'w') as f:
            f.write("\n".join(self.migration_log))
        
        print(f"Migration log saved to: {log_path}")
    
    def run_migration(self):
        """Execute complete migration"""
        print("🚀 Starting VLM Data Migration to Drive E...")
        print("=" * 60)
        
        # Check if Drive E is accessible
        if not self.drive_e_root.exists():
            raise Exception("Drive E is not accessible!")
        
        try:
            # Step 1: Setup directory structure
            self.log("Setting up Drive E directory structure...")
            self.setup_drive_e_structure()
            
            # Step 2: Migrate databases
            self.log("Migrating databases...")
            self.migrate_databases()
            
            # Step 3: Migrate embeddings (largest operation)
            self.log("Migrating embeddings...")
            self.migrate_embeddings()
            
            # Step 4: Migrate derived data
            self.log("Migrating derived data...")
            self.migrate_derived_data()
            
            # Step 5: Migrate verification results
            self.log("Migrating verification results...")
            self.migrate_verification_results()
            
            # Step 6: Migrate test assets
            self.log("Migrating test assets...")
            self.migrate_test_assets()
            
            # Step 7: Migrate logs and state files
            self.log("Migrating logs and state files...")
            self.migrate_logs_and_state()
            
            # Step 8: Create configuration
            self.log("Creating Drive E configuration...")
            self.create_drive_e_config()
            
            # Step 9: Save migration log
            self.save_migration_log()
            
            print("\n✅ Migration completed successfully!")
            print(f"📁 Data location: {self.drive_e_root}")
            print(f"💾 Configuration: {self.workspace_root}/config/drive_e_paths.json")
            
        except Exception as e:
            self.log(f"❌ Migration failed: {e}")
            raise

if __name__ == "__main__":
    migrator = VLMDataMigrator()
    migrator.run_migration()
