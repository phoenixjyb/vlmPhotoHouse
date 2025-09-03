#!/usr/bin/env python3
"""
Check if coordinates are fixed after the update
"""

import sqlite3

def main():
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()

    print('Recent SCRFD detections with corrected coordinates:')
    cursor.execute('''
        SELECT fd.asset_id, a.path, fd.bbox_x, fd.bbox_y, fd.bbox_w, fd.bbox_h
        FROM face_detections fd
        JOIN assets a ON fd.asset_id = a.id
        WHERE fd.asset_id > 5
        ORDER BY fd.asset_id DESC
        LIMIT 10
    ''')

    for row in cursor.fetchall():
        asset_id, path, x, y, w, h = row
        filename = path.split('\\')[-1] if '\\' in path else path.split('/')[-1]
        valid = "✅" if w > 0 and h > 0 else "❌"
        
        print(f'ID: {asset_id}, File: {filename}')
        print(f'  Position: ({x:.0f}, {y:.0f})')
        print(f'  Size: {w:.0f} x {h:.0f} pixels')
        print(f'  Valid: {valid}')
        print()

    conn.close()

if __name__ == "__main__":
    main()
