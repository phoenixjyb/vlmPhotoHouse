#!/usr/bin/env python3
"""
Verify face processing status was added to database
"""

import sqlite3
import json
import os

def verify_database_changes():
    """Verify the face processing status columns were added and populated"""
    
    print("🔍 VERIFYING DATABASE FACE PROCESSING STATUS")
    print("=" * 60)
    
    try:
        # Load Drive E configuration
        config_path = "config/drive_e_paths.json"
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
            db_path = config["databases"]["app"]
        else:
            # Fallback to local database
            db_path = "app.db"
            
        print(f"📁 Using database: {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. Check if new columns exist
        print("📋 Checking database schema...")
        cursor.execute("PRAGMA table_info(assets)")
        columns = cursor.fetchall()
        
        column_names = [col[1] for col in columns]
        new_columns = ['face_processed', 'face_count', 'face_processed_at']
        
        print(f"Assets table columns:")
        for col in columns:
            col_name = col[1]
            col_type = col[2]
            is_new = "🆕" if col_name in new_columns else "  "
            print(f"   {is_new} {col_name} ({col_type})")
        
        # Check if our new columns exist
        missing_columns = [col for col in new_columns if col not in column_names]
        if missing_columns:
            print(f"\n❌ Missing columns: {missing_columns}")
            return False
        else:
            print(f"\n✅ All face processing columns exist!")
        
        # 2. Check data population
        print(f"\n📊 Checking data population...")
        
        # Count processed images
        cursor.execute("""
            SELECT 
                COUNT(*) as total_images,
                SUM(CASE WHEN face_processed = 1 THEN 1 ELSE 0 END) as processed_count,
                SUM(CASE WHEN face_processed IS NULL THEN 1 ELSE 0 END) as null_count,
                SUM(CASE WHEN face_count > 0 THEN 1 ELSE 0 END) as with_faces,
                SUM(CASE WHEN face_count = 0 THEN 1 ELSE 0 END) as no_faces,
                MAX(face_count) as max_faces
            FROM assets 
            WHERE mime LIKE 'image/%' AND id > 5
        """)
        
        stats = cursor.fetchone()
        total, processed, null_count, with_faces, no_faces, max_faces = stats
        
        print(f"Statistics:")
        print(f"   Total images: {total}")
        print(f"   Processed (face_processed=TRUE): {processed}")
        print(f"   Not processed (face_processed=NULL): {null_count}")
        print(f"   Images with faces (face_count>0): {with_faces}")
        print(f"   Images with no faces (face_count=0): {no_faces}")
        print(f"   Maximum faces in single image: {max_faces}")
        
        # 3. Sample some records
        print(f"\n📋 Sample records with face processing data:")
        cursor.execute("""
            SELECT id, face_processed, face_count, face_processed_at, 
                   substr(path, -30) as filename
            FROM assets 
            WHERE mime LIKE 'image/%' AND id > 5
            ORDER BY id 
            LIMIT 10
        """)
        
        samples = cursor.fetchall()
        print(f"ID   | Processed | Count | Processed At        | Filename")
        print(f"-" * 70)
        for record in samples:
            asset_id, processed, count, processed_at, filename = record
            processed_str = "✅" if processed else "❌"
            processed_at_str = processed_at[:19] if processed_at else "None"
            count_str = str(count) if count is not None else "None"
            print(f"{asset_id:4d} | {processed_str:9s} | {count_str:5s} | {processed_at_str:19s} | {filename}")
        
        # 4. Check consistency with face_detections table
        print(f"\n🔍 Checking consistency with face_detections table...")
        cursor.execute("""
            WITH face_counts AS (
                SELECT 
                    a.id,
                    a.face_count,
                    COUNT(f.id) as actual_face_count
                FROM assets a
                LEFT JOIN face_detections f ON a.id = f.asset_id
                WHERE a.mime LIKE 'image/%' AND a.id > 5
                GROUP BY a.id, a.face_count
            )
            SELECT id, face_count, actual_face_count
            FROM face_counts
            WHERE face_count != actual_face_count
            LIMIT 5
        """)
        
        inconsistencies = cursor.fetchall()
        
        if inconsistencies:
            print(f"⚠️ Found {len(inconsistencies)} inconsistencies:")
            for asset_id, recorded_count, actual_count in inconsistencies:
                print(f"   Asset {asset_id}: recorded={recorded_count}, actual={actual_count}")
        else:
            print(f"✅ Face counts are consistent with face_detections table")
        
        # 5. Check recent processing timestamps
        print(f"\n⏰ Recent processing timestamps:")
        cursor.execute("""
            SELECT 
                DATE(face_processed_at) as process_date,
                COUNT(*) as images_processed
            FROM assets 
            WHERE face_processed_at IS NOT NULL
            GROUP BY DATE(face_processed_at)
            ORDER BY process_date DESC
            LIMIT 5
        """)
        
        dates = cursor.fetchall()
        for date, count in dates:
            print(f"   {date}: {count} images processed")
        
        conn.close()
        
        # Summary
        if processed == total and null_count == 0:
            print(f"\n🎉 PERFECT! All {total} images are marked as processed")
            print(f"   ✅ {with_faces} images with faces")
            print(f"   ✅ {no_faces} images with no faces")
            print(f"   ✅ Status tracking is complete and accurate")
            return True
        else:
            print(f"\n⚠️ Some images may not be properly marked as processed")
            return False
            
    except Exception as e:
        print(f"❌ Error verifying database: {e}")
        return False

if __name__ == "__main__":
    verify_database_changes()
