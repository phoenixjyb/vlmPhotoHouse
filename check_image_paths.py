#!/usr/bin/env python3
"""
Quick script to check the actual image paths being processed
"""

import sqlite3
import os

def main():
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    
    # Get first 5 images
    cursor.execute('SELECT id, path FROM assets WHERE mime LIKE "image/%" ORDER BY id LIMIT 5')
    images = cursor.fetchall()
    
    print("First 5 images in database:")
    for asset_id, path in images:
        exists = "✅" if os.path.exists(path) else "❌"
        print(f"ID: {asset_id}, Path: {path} {exists}")
        
        # Check file size if it exists
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"    Size: {size:,} bytes ({size/1024/1024:.1f} MB)")
    
    conn.close()

if __name__ == "__main__":
    main()
