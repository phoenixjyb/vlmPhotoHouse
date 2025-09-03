#!/usr/bin/env python3
"""Quick asset importer to populate the database with image files"""

import os
import sqlite3
import hashlib
from datetime import datetime
import mimetypes

def import_assets():
    """Import image assets from the directory structure"""
    
    # Base directories to scan
    base_dirs = [
        "E:/01_INCOMING",
        "E:/02_PROCESSED", 
        "E:/03_CURATED"
    ]
    
    db_path = "app.db"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔍 Scanning for image files...")
        
        image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp'}
        imported_count = 0
        
        for base_dir in base_dirs:
            if not os.path.exists(base_dir):
                print(f"⚠️ Directory not found: {base_dir}")
                continue
                
            print(f"📂 Scanning: {base_dir}")
            
            for root, dirs, files in os.walk(base_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    _, ext = os.path.splitext(file.lower())
                    
                    if ext in image_extensions:
                        try:
                            # Check if already exists
                            cursor.execute("SELECT id FROM assets WHERE path = ?", (file_path,))
                            if cursor.fetchone():
                                continue  # Already imported
                            
                            # Get file stats
                            stat = os.stat(file_path)
                            file_size = stat.st_size
                            
                            # Get MIME type
                            mime_type, _ = mimetypes.guess_type(file_path)
                            if not mime_type:
                                mime_type = 'image/jpeg'  # Default
                            
                            # Generate hash (simple for now)
                            hash_sha256 = hashlib.sha256(file_path.encode()).hexdigest()[:64]
                            
                            # Insert into database
                            cursor.execute("""
                                INSERT INTO assets 
                                (path, hash_sha256, mime, file_size, created_at, imported_at, status)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                file_path,
                                hash_sha256,
                                mime_type,
                                file_size,
                                datetime.now(),
                                datetime.now(),
                                'new'
                            ))
                            
                            imported_count += 1
                            
                            if imported_count % 100 == 0:
                                print(f"   📸 Imported {imported_count} images...")
                                conn.commit()
                                
                        except Exception as e:
                            print(f"❌ Error importing {file_path}: {e}")
                            continue
        
        conn.commit()
        conn.close()
        
        print(f"✅ Successfully imported {imported_count} image assets!")
        print(f"📊 Ready for face processing")
        
    except Exception as e:
        print(f"❌ Database error: {e}")

if __name__ == "__main__":
    import_assets()
