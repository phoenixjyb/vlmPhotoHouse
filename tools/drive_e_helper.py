#!/usr/bin/env python3
"""
Drive E Data Access Helper
Provides easy access to data stored on Drive E after migration
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional

class DriveEConfig:
    """Helper class to access Drive E data locations"""
    
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            # Default config location
            config_path = Path(__file__).parent.parent / "config" / "drive_e_paths.json"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load the Drive E configuration"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Drive E config not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    @property
    def root(self) -> Path:
        """Root directory on Drive E"""
        return Path(self.config['vlm_data_root'])
    
    @property
    def databases(self) -> Dict[str, Path]:
        """Database file paths"""
        return {name: Path(path) for name, path in self.config['databases'].items()}
    
    @property
    def metadata_db(self) -> Path:
        """Main metadata database"""
        return Path(self.config['databases']['metadata'])
    
    @property
    def app_db(self) -> Path:
        """Application database"""
        return Path(self.config['databases']['app'])
    
    @property
    def embeddings_dir(self) -> Path:
        """Face embeddings directory"""
        return Path(self.config['embeddings']['faces'])
    
    @property
    def derived_dir(self) -> Path:
        """Derived data directory"""
        return Path(self.config['derived']['thumbnails']).parent
    
    @property
    def logs_dir(self) -> Path:
        """Logs directory"""
        return Path(self.config['logs'])
    
    @property
    def verification_dir(self) -> Path:
        """Verification results directory"""
        return Path(self.config['verification'])
    
    @property
    def test_assets_dir(self) -> Path:
        """Test assets directory"""
        return Path(self.config['test_assets'])
    
    def get_embedding_path(self, filename: str) -> Path:
        """Get full path for an embedding file"""
        return self.embeddings_dir / filename
    
    def list_embeddings(self, pattern: str = "*.json") -> list:
        """List all embedding files"""
        if not self.embeddings_dir.exists():
            return []
        return list(self.embeddings_dir.glob(pattern))
    
    def verify_access(self) -> Dict[str, bool]:
        """Verify access to all configured directories"""
        results = {}
        
        # Check root
        results['root'] = self.root.exists()
        
        # Check databases
        for name, path in self.databases.items():
            results[f'db_{name}'] = path.exists()
        
        # Check directories
        directories = {
            'embeddings': self.embeddings_dir,
            'derived': self.derived_dir,
            'logs': self.logs_dir,
            'verification': self.verification_dir,
            'test_assets': self.test_assets_dir
        }
        
        for name, path in directories.items():
            results[name] = path.exists() and path.is_dir()
        
        return results
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about data on Drive E"""
        stats = {}
        
        # Embedding files count
        if self.embeddings_dir.exists():
            stats['embedding_files'] = len(list(self.embeddings_dir.glob("*.json")))
        else:
            stats['embedding_files'] = 0
        
        # Database sizes
        for name, path in self.databases.items():
            if path.exists():
                stats[f'{name}_db_size_mb'] = round(path.stat().st_size / (1024 * 1024), 2)
            else:
                stats[f'{name}_db_size_mb'] = 0
        
        # Directory file counts
        directories = {
            'derived_files': self.derived_dir,
            'log_files': self.logs_dir,
            'verification_files': self.verification_dir,
            'test_files': self.test_assets_dir
        }
        
        for stat_name, path in directories.items():
            if path.exists():
                stats[stat_name] = len(list(path.rglob("*")))
            else:
                stats[stat_name] = 0
        
        return stats

# Global instance for easy import
drive_e = DriveEConfig()

# Convenience functions
def get_metadata_db() -> Path:
    """Get metadata database path"""
    return drive_e.metadata_db

def get_embeddings_dir() -> Path:
    """Get embeddings directory path"""
    return drive_e.embeddings_dir

def get_embedding_file(filename: str) -> Path:
    """Get full path for an embedding file"""
    return drive_e.get_embedding_path(filename)

def verify_drive_e_access() -> bool:
    """Quick verification that Drive E is accessible"""
    results = drive_e.verify_access()
    return all(results.values())

if __name__ == "__main__":
    # Test the configuration
    print("🔧 Drive E Configuration Test")
    print("=" * 40)
    
    # Show configuration
    print(f"📁 Root: {drive_e.root}")
    print(f"💾 Metadata DB: {drive_e.metadata_db}")
    print(f"🧠 Embeddings: {drive_e.embeddings_dir}")
    print(f"📊 Derived: {drive_e.derived_dir}")
    
    # Verify access
    print("\n🔍 Access Verification:")
    access_results = drive_e.verify_access()
    for component, accessible in access_results.items():
        status = "✅" if accessible else "❌"
        print(f"  {status} {component}")
    
    # Show statistics
    print(f"\n📈 Statistics:")
    stats = drive_e.get_stats()
    for stat_name, value in stats.items():
        print(f"  📊 {stat_name}: {value}")
    
    # Overall status
    all_accessible = all(access_results.values())
    print(f"\n🎯 Overall Status: {'✅ READY' if all_accessible else '❌ ISSUES DETECTED'}")
