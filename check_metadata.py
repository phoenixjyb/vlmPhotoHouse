#!/usr/bin/env python3

import sqlite3

def check_metadata_db():
    conn = sqlite3.connect('metadata.sqlite')
    cursor = conn.cursor()
    
    # Get tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print('📊 Tables in metadata.sqlite:')
    for table in tables:
        print(f'  - {table[0]}')
    print()
    
    # Check if we have photos/assets
    try:
        cursor.execute("SELECT COUNT(*) FROM photos")
        photos = cursor.fetchone()[0]
        print(f"📸 Photos: {photos:,}")
    except:
        try:
            cursor.execute("SELECT COUNT(*) FROM assets")
            assets = cursor.fetchone()[0]
            print(f"📁 Assets: {assets:,}")
        except:
            print("❌ No photos or assets table found")
    
    conn.close()

if __name__ == "__main__":
    check_metadata_db()
