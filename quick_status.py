#!/usr/bin/env python3

import sqlite3

def main():
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    # Get image count
    cursor.execute("SELECT COUNT(*) FROM assets WHERE mime LIKE 'image/%'")
    images = cursor.fetchone()[0]
    
    # Get face detection count
    cursor.execute("SELECT COUNT(DISTINCT asset_id) FROM face_detections") 
    faces = cursor.fetchone()[0]
    
    # Get task counts
    cursor.execute("SELECT type, state, COUNT(*) FROM tasks GROUP BY type, state")
    tasks = cursor.fetchall()
    
    print("🎯 FACE PROCESSING READINESS")
    print("=" * 40)
    print(f"📸 Images in database: {images:,}")
    print(f"👤 Images with faces: {faces:,}")
    print(f"⚡ Images to process: {images - faces:,}")
    print()
    print("📋 Current Tasks:")
    for task_type, state, count in tasks:
        print(f"  {task_type} ({state}): {count}")
    
    conn.close()

if __name__ == "__main__":
    main()
