#!/usr/bin/env python3
"""
Check database schema and recent entries
"""

import sqlite3

def main():
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    # Check all tables
    cursor.execute('SELECT name FROM sqlite_master WHERE type="table"')
    tables = cursor.fetchall()
    print('All tables:')
    for table in tables:
        print(f'  {table[0]}')
    
    # Check recent face_detections entries
    cursor.execute('SELECT COUNT(*) FROM face_detections')
    count = cursor.fetchone()[0]
    print(f'\nTotal face_detections entries: {count}')
    
    # Check last few entries
    cursor.execute('SELECT * FROM face_detections ORDER BY id DESC LIMIT 5')
    recent = cursor.fetchall()
    print('\nLast 5 face_detections entries:')
    for row in recent:
        print(f'  ID: {row[0]}, Asset: {row[1]}, BBox: ({row[2]:.1f},{row[3]:.1f},{row[4]:.1f},{row[5]:.1f}), Person: {row[6]}, Embedding: {row[7]}')
    
    # Check for other detection-related tables
    cursor.execute('SELECT name FROM sqlite_master WHERE type="table" AND name LIKE "%detection%"')
    detection_tables = cursor.fetchall()
    if detection_tables:
        print('\nDetection-related tables:')
        for table in detection_tables:
            print(f'  {table[0]}')
            
    # Also check what images ID 6-10 are
    print("\nImages ID 6-10:")
    cursor.execute('SELECT id, path FROM assets WHERE id BETWEEN 6 AND 10 ORDER BY id')
    for asset_id, path in cursor.fetchall():
        import os
        exists = "✅" if os.path.exists(path) else "❌"
        basename = os.path.basename(path)
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"ID: {asset_id}, File: {basename}, Size: {size:,} bytes {exists}")
        else:
            print(f"ID: {asset_id}, File: {basename} {exists}")
    
    conn.close()

if __name__ == "__main__":
    main()
