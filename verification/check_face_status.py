import sqlite3

def check_face_processing_status():
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    # First, check what tables we have
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print('📊 Available Tables:')
    for table in tables:
        print(f'  - {table[0]}')
    print()
    
    # Get total asset count (filter by image mime types)
    cursor.execute("SELECT COUNT(*) FROM assets WHERE mime LIKE 'image/%'")
    image_count = cursor.fetchone()[0]
    
    # Get total assets
    cursor.execute("SELECT COUNT(*) FROM assets")
    total_assets = cursor.fetchone()[0]
    
    # Get assets with faces already processed
    cursor.execute("SELECT COUNT(DISTINCT asset_id) FROM face_detections")
    faces_processed = cursor.fetchone()[0]
    
    # Get pending face processing tasks (using correct column names)
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE type = 'face_detection' AND state = 'pending'")
    pending_face_tasks = cursor.fetchone()[0]
    
    # Get task summary (using correct column names)
    cursor.execute("SELECT type, state, COUNT(*) FROM tasks GROUP BY type, state")
    task_summary = cursor.fetchall()
    
    print('🎯 Face Processing Readiness Assessment')
    print('=' * 50)
    print(f'Total Assets: {total_assets:,}')
    print(f'Image Assets: {image_count:,}')
    print(f'Images with Face Data: {faces_processed:,}')
    print(f'Images Needing Face Processing: {image_count - faces_processed:,}')
    print(f'Pending Face Tasks: {pending_face_tasks:,}')
    print()
    
    print('📋 Task Summary:')
    if task_summary:
        for task_type, status, count in task_summary:
            print(f'  {task_type} ({status}): {count:,}')
    else:
        print('  No tasks found in database')
    
    # Check persons table
    cursor.execute("SELECT COUNT(*) FROM persons")
    person_count = cursor.fetchone()[0]
    print(f'\n👥 Persons in Database: {person_count:,}')
    
    # Check face_detections table schema
    cursor.execute("PRAGMA table_info(face_detections)")
    face_columns = cursor.fetchall()
    print(f'\n🔍 Face Detections Table Columns:')
    for col in face_columns:
        print(f'  - {col[1]} ({col[2]})')
    
    conn.close()
    return image_count, faces_processed, pending_face_tasks

if __name__ == '__main__':
    check_face_processing_status()
