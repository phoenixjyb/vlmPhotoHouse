#!/usr/bin/env python3
"""
Add face processing status tracking to database
"""

import sqlite3
from datetime import datetime

def add_face_processing_status():
    """Add face processing status columns to assets table"""
    
    print("🗄️ ADDING FACE PROCESSING STATUS TRACKING")
    print("=" * 60)
    
    try:
        conn = sqlite3.connect('app.db')
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(assets)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add face processing columns if they don't exist
        if 'face_processed' not in columns:
            print("📝 Adding 'face_processed' column...")
            cursor.execute("ALTER TABLE assets ADD COLUMN face_processed BOOLEAN DEFAULT FALSE")
            print("✅ Added face_processed column")
        else:
            print("✅ face_processed column already exists")
            
        if 'face_count' not in columns:
            print("📝 Adding 'face_count' column...")
            cursor.execute("ALTER TABLE assets ADD COLUMN face_count INTEGER DEFAULT 0")
            print("✅ Added face_count column")
        else:
            print("✅ face_count column already exists")
            
        if 'face_processed_at' not in columns:
            print("📝 Adding 'face_processed_at' timestamp column...")
            cursor.execute("ALTER TABLE assets ADD COLUMN face_processed_at TIMESTAMP")
            print("✅ Added face_processed_at column")
        else:
            print("✅ face_processed_at column already exists")
        
        conn.commit()
        conn.close()
        print("\n🎉 Database schema updated successfully!")
        
    except Exception as e:
        print(f"❌ Error updating database schema: {e}")
        return False
    
    return True

def populate_face_processing_status():
    """Populate the new columns based on existing face_detections data"""
    
    print(f"\n📊 POPULATING FACE PROCESSING STATUS")
    print("=" * 60)
    
    try:
        conn = sqlite3.connect('app.db')
        cursor = conn.cursor()
        
        # Get current timestamp
        current_time = datetime.now().isoformat()
        
        # 1. Update assets that have face detections
        print("📝 Updating assets with face detections...")
        cursor.execute("""
            UPDATE assets 
            SET 
                face_processed = TRUE,
                face_count = (
                    SELECT COUNT(*) 
                    FROM face_detections 
                    WHERE asset_id = assets.id
                ),
                face_processed_at = ?
            WHERE id IN (
                SELECT DISTINCT asset_id 
                FROM face_detections
            )
        """, (current_time,))
        
        faces_updated = cursor.rowcount
        print(f"✅ Updated {faces_updated} assets with face detections")
        
        # 2. For the remaining images, we need to mark them as processed with 0 faces
        # Since we know from your monitoring that all images have been processed
        print("📝 Marking remaining images as processed with 0 faces...")
        cursor.execute("""
            UPDATE assets 
            SET 
                face_processed = TRUE,
                face_count = 0,
                face_processed_at = ?
            WHERE mime LIKE 'image/%' 
            AND id > 5 
            AND face_processed IS NULL
        """, (current_time,))
        
        no_faces_updated = cursor.rowcount
        print(f"✅ Updated {no_faces_updated} assets with no faces")
        
        # 3. Get summary statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_images,
                SUM(CASE WHEN face_processed = TRUE THEN 1 ELSE 0 END) as processed_images,
                SUM(CASE WHEN face_count > 0 THEN 1 ELSE 0 END) as images_with_faces,
                SUM(CASE WHEN face_count = 0 AND face_processed = TRUE THEN 1 ELSE 0 END) as images_no_faces,
                SUM(face_count) as total_faces
            FROM assets 
            WHERE mime LIKE 'image/%' AND id > 5
        """)
        
        stats = cursor.fetchone()
        
        conn.commit()
        conn.close()
        
        print(f"\n📊 FINAL STATISTICS:")
        print(f"   Total images: {stats[0]}")
        print(f"   Processed images: {stats[1]}")
        print(f"   Images with faces: {stats[2]}")
        print(f"   Images with no faces: {stats[3]}")
        print(f"   Total faces detected: {stats[4]}")
        
    except Exception as e:
        print(f"❌ Error populating status: {e}")
        return False
    
    return True

def update_orchestrator_to_use_status():
    """Show how to update the orchestrator to use the new status columns"""
    
    print(f"\n🔧 UPDATING ORCHESTRATOR FOR STATUS TRACKING")
    print("=" * 60)
    
    orchestrator_update = '''
# In enhanced_face_orchestrator_unified.py, modify save_face_detection_results():

def save_face_detection_results(self, asset_id, image_path, scrfd_result):
    """Save SCRFD detection results AND processing status to database"""
    with self.db_lock:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Clear any existing detections for this image
            cursor.execute("DELETE FROM face_detections WHERE asset_id = ?", (asset_id,))
            
            faces_count = scrfd_result.get('faces', 0)
            current_time = datetime.now().isoformat()
            
            # ALWAYS update the asset processing status
            cursor.execute("""
                UPDATE assets 
                SET face_processed = TRUE, 
                    face_count = ?, 
                    face_processed_at = ?
                WHERE id = ?
            """, (faces_count, current_time, asset_id))
            
            # Only save face detection records if faces were found
            if faces_count > 0:
                detections = scrfd_result.get('detections', [])
                # ... existing face saving logic ...
            
            conn.commit()
            conn.close()
            return True
    '''
    
    print("📝 Recommended orchestrator update:")
    print(orchestrator_update)
    
    print(f"\n💡 Benefits of this approach:")
    print("   ✅ Track processing status for ALL images")
    print("   ✅ Know exact face count per image")
    print("   ✅ Timestamp when processing occurred")
    print("   ✅ Can identify unprocessed images easily")
    print("   ✅ Better analytics and reporting")

def create_status_queries():
    """Create useful queries for the new status tracking"""
    
    print(f"\n📊 USEFUL QUERIES WITH NEW STATUS TRACKING")
    print("=" * 60)
    
    queries = [
        ("Images processed today", """
            SELECT COUNT(*) 
            FROM assets 
            WHERE face_processed_at LIKE '{}%'
        """.format(datetime.now().strftime('%Y-%m-%d'))),
        
        ("Processing completion rate", """
            SELECT 
                ROUND(100.0 * SUM(CASE WHEN face_processed = TRUE THEN 1 ELSE 0 END) / COUNT(*), 2) as completion_percentage
            FROM assets 
            WHERE mime LIKE 'image/%' AND id > 5
        """),
        
        ("Face detection statistics", """
            SELECT 
                'Images with faces' as category, COUNT(*) as count
            FROM assets 
            WHERE face_count > 0
            UNION ALL
            SELECT 
                'Images without faces' as category, COUNT(*) as count
            FROM assets 
            WHERE face_count = 0 AND face_processed = TRUE
            UNION ALL
            SELECT 
                'Unprocessed images' as category, COUNT(*) as count
            FROM assets 
            WHERE face_processed IS NULL OR face_processed = FALSE
        """),
        
        ("Images needing reprocessing", """
            SELECT id, path, face_count 
            FROM assets 
            WHERE (face_processed IS NULL OR face_processed = FALSE)
            AND mime LIKE 'image/%' 
            AND id > 5
            LIMIT 10
        """)
    ]
    
    for name, query in queries:
        print(f"-- {name}")
        print(query)
        print()

if __name__ == "__main__":
    # Step 1: Add new columns
    if add_face_processing_status():
        
        # Step 2: Populate with existing data
        if populate_face_processing_status():
            
            # Step 3: Show how to update orchestrator
            update_orchestrator_to_use_status()
            
            # Step 4: Provide useful queries
            create_status_queries()
            
            print(f"\n🎉 FACE PROCESSING STATUS TRACKING COMPLETE!")
            print("Your database now tracks processing status for all images!")
        else:
            print("❌ Failed to populate status data")
    else:
        print("❌ Failed to update database schema")
