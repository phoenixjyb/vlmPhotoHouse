#!/usr/bin/env python3
"""
Database Schema Inspector
Check the actual database structure and face detection data
"""

import sqlite3

def inspect_database():
    """Inspect the database schema and data"""
    try:
        conn = sqlite3.connect("metadata.sqlite")
        cursor = conn.cursor()
        
        print("🔍 DATABASE SCHEMA INSPECTION")
        print("=" * 50)
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        print("📋 Available tables:")
        for table in tables:
            print(f"   • {table[0]}")
        
        # Check face_detections table structure
        print(f"\n📊 FACE_DETECTIONS TABLE STRUCTURE:")
        cursor.execute("PRAGMA table_info(face_detections)")
        columns = cursor.fetchall()
        
        for column in columns:
            col_id, name, col_type, not_null, default, primary_key = column
            print(f"   • {name}: {col_type} {'(PRIMARY KEY)' if primary_key else ''}")
        
        # Sample data from face_detections
        print(f"\n📄 SAMPLE FACE_DETECTIONS DATA:")
        cursor.execute("SELECT * FROM face_detections LIMIT 3")
        sample_data = cursor.fetchall()
        
        if sample_data:
            # Get column names
            column_names = [description[0] for description in cursor.description]
            print(f"   Columns: {', '.join(column_names)}")
            
            for i, row in enumerate(sample_data):
                print(f"   Row {i+1}: {row}")
        else:
            print("   No data found in face_detections table")
        
        # Check if there are any face detection records at all
        cursor.execute("SELECT COUNT(*) FROM face_detections")
        face_count = cursor.fetchone()[0]
        print(f"\n📈 Total face_detections records: {face_count}")
        
        # Check recent assets
        print(f"\n📄 SAMPLE ASSETS DATA:")
        cursor.execute("SELECT id, filename, path FROM assets LIMIT 5")
        asset_samples = cursor.fetchall()
        
        for asset in asset_samples:
            print(f"   ID {asset[0]}: {asset[1]} -> {asset[2]}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Database inspection error: {e}")

def check_processing_logs():
    """Check if there are any processing logs or indicators"""
    import os
    import glob
    
    print(f"\n🔍 PROCESSING LOGS CHECK")
    print("=" * 50)
    
    # Check for any log files
    log_files = glob.glob("*.log")
    if log_files:
        print("📄 Found log files:")
        for log_file in log_files:
            size = os.path.getsize(log_file)
            print(f"   • {log_file}: {size} bytes")
    else:
        print("📄 No log files found")
    
    # Check for embedding files
    if os.path.exists("embeddings"):
        embedding_files = os.listdir("embeddings")
        print(f"📁 Embedding files: {len(embedding_files)}")
        if embedding_files:
            print(f"   Sample: {embedding_files[:3]}")
    else:
        print("📁 No embeddings directory found")

if __name__ == "__main__":
    inspect_database()
    check_processing_logs()
    
    print(f"\n💡 DIAGNOSIS:")
    print("=" * 50)
    print("The database schema seems to be different than expected.")
    print("The 'confidence' column is missing from face_detections table.")
    print("This suggests the previous batch processing may not have")
    print("properly called the SCRFD service or used a different schema.")
    print(f"\n🔧 RECOMMENDED ACTION:")
    print("1. Check if SCRFD service is running")
    print("2. Test the service with a known face image")
    print("3. Run fresh face detection with proper schema")
