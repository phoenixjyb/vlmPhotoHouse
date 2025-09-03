#!/usr/bin/env python3
"""Check database schema to understand table structure"""

import sqlite3
import os

def check_database_schema():
    """Check the current database schema"""
    
    db_path = "app.db"
    
    if not os.path.exists(db_path):
        print("❌ Database not found: app.db")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🗄️ Database Schema Analysis")
        print("=" * 50)
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print(f"📋 Found {len(tables)} tables:")
        for table in tables:
            print(f"   • {table[0]}")
        
        # Check assets table structure
        print("\n📊 Assets Table Structure:")
        print("-" * 30)
        
        cursor.execute("PRAGMA table_info(assets);")
        columns = cursor.fetchall()
        
        if columns:
            print("Columns:")
            for col in columns:
                print(f"   {col[1]} ({col[2]}) - NOT NULL: {bool(col[3])}")
        else:
            print("❌ Assets table not found or empty")
        
        # Check face_detections table structure
        print("\n👤 Face_Detections Table Structure:")
        print("-" * 40)
        
        cursor.execute("PRAGMA table_info(face_detections);")
        fd_columns = cursor.fetchall()
        
        if fd_columns:
            print("Columns:")
            for col in fd_columns:
                print(f"   {col[1]} ({col[2]}) - NOT NULL: {bool(col[3])}")
        else:
            print("❌ Face_detections table not found")
        
        # Sample data from assets
        print("\n📸 Sample Assets Data:")
        print("-" * 25)
        
        cursor.execute("SELECT * FROM assets LIMIT 5;")
        sample_assets = cursor.fetchall()
        
        if sample_assets:
            # Get column names
            cursor.execute("PRAGMA table_info(assets);")
            asset_columns = [col[1] for col in cursor.fetchall()]
            
            for i, row in enumerate(sample_assets):
                print(f"Row {i+1}:")
                for col_name, value in zip(asset_columns, row):
                    print(f"   {col_name}: {value}")
                print()
        else:
            print("❌ No sample data found in assets table")
        
        # Count total assets
        cursor.execute("SELECT COUNT(*) FROM assets;")
        total_assets = cursor.fetchone()[0]
        print(f"📊 Total assets in database: {total_assets}")
        
        # Count processed faces
        cursor.execute("SELECT COUNT(*) FROM face_detections;")
        total_faces = cursor.fetchone()[0]
        print(f"👤 Total face detections: {total_faces}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Database error: {e}")

if __name__ == "__main__":
    check_database_schema()
