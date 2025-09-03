#!/usr/bin/env python3

import sqlite3

def face_processing_readiness():
    conn = sqlite3.connect('metadata.sqlite')
    cursor = conn.cursor()
    
    # Get total assets
    cursor.execute("SELECT COUNT(*) FROM assets")
    total_assets = cursor.fetchone()[0]
    
    # Get image assets (filter by mime type)
    cursor.execute("SELECT COUNT(*) FROM assets WHERE mime LIKE 'image/%'")
    image_assets = cursor.fetchone()[0]
    
    # Get assets with face detections
    cursor.execute("SELECT COUNT(DISTINCT asset_id) FROM face_detections")
    assets_with_faces = cursor.fetchone()[0]
    
    # Get total face detections
    cursor.execute("SELECT COUNT(*) FROM face_detections")
    total_faces = cursor.fetchone()[0]
    
    # Get persons count
    cursor.execute("SELECT COUNT(*) FROM persons")
    persons_count = cursor.fetchone()[0]
    
    # Get tasks related to face processing
    cursor.execute("SELECT type, state, COUNT(*) FROM tasks WHERE type LIKE '%face%' GROUP BY type, state")
    face_tasks = cursor.fetchall()
    
    print("🎯 FACE PROCESSING READINESS ASSESSMENT")
    print("=" * 50)
    print(f"📁 Total Assets: {total_assets:,}")
    print(f"📸 Image Assets: {image_assets:,}")
    print(f"👤 Images with Faces Detected: {assets_with_faces:,}")
    print(f"🔍 Total Face Detections: {total_faces:,}")
    print(f"👥 Persons in Database: {persons_count:,}")
    print(f"⚡ Images Pending Face Processing: {image_assets - assets_with_faces:,}")
    print()
    
    if face_tasks:
        print("📋 Face Processing Tasks:")
        for task_type, state, count in face_tasks:
            print(f"  {task_type} ({state}): {count:,}")
    else:
        print("📋 No face processing tasks found")
    
    print()
    print("🚀 RECOMMENDATIONS:")
    
    if assets_with_faces == 0:
        print("  ✨ Ready to start face processing from scratch!")
        print(f"  📊 Need to process {image_assets:,} images")
        print("  🎯 Estimated time: ~{:.1f} hours at 0.78s per image".format(image_assets * 0.78 / 3600))
    else:
        remaining = image_assets - assets_with_faces
        print(f"  🔄 Continue processing {remaining:,} remaining images")
        print("  📊 Some faces already detected")
    
    conn.close()
    return image_assets, assets_with_faces, total_faces, persons_count

if __name__ == "__main__":
    face_processing_readiness()
