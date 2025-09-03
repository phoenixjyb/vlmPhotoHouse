#!/usr/bin/env python3
"""
Check processing progress and remaining images
"""

import sqlite3

def check_processing_progress():
    """Check how many images have been processed and how many remain"""
    
    print("📊 FACE DETECTION PROCESSING PROGRESS")
    print("=" * 50)
    
    try:
        conn = sqlite3.connect('app.db')
        cursor = conn.cursor()
        
        # Total images in database
        cursor.execute("SELECT COUNT(*) FROM assets WHERE mime LIKE 'image/%' AND id > 5")
        total_images = cursor.fetchone()[0]
        
        # Images with face detections
        cursor.execute("SELECT COUNT(DISTINCT asset_id) FROM face_detections")
        processed_images = cursor.fetchone()[0]
        
        # Total face detections
        cursor.execute("SELECT COUNT(*) FROM face_detections")
        total_faces = cursor.fetchone()[0]
        
        # Images with embeddings
        cursor.execute("SELECT COUNT(DISTINCT asset_id) FROM face_detections WHERE embedding_path IS NOT NULL")
        images_with_embeddings = cursor.fetchone()[0]
        
        # Total embeddings
        cursor.execute("SELECT COUNT(*) FROM face_detections WHERE embedding_path IS NOT NULL")
        total_embeddings = cursor.fetchone()[0]
        
        remaining = total_images - processed_images
        progress_percent = (processed_images / total_images) * 100
        
        print(f"Total images in database: {total_images}")
        print(f"Images processed: {processed_images}")
        print(f"Images remaining: {remaining}")
        print(f"Progress: {progress_percent:.1f}%")
        print()
        print(f"Total faces detected: {total_faces}")
        print(f"Images with embeddings: {images_with_embeddings}")
        print(f"Total embeddings: {total_embeddings}")
        print()
        
        if remaining > 0:
            print(f"🚀 Ready to continue processing {remaining} remaining images")
            
            # Estimate remaining time based on current rate
            estimated_time = remaining / 0.57  # images per second
            hours = estimated_time // 3600
            minutes = (estimated_time % 3600) // 60
            
            print(f"⏱️ Estimated time for remaining: {hours:.0f}h {minutes:.0f}m")
        else:
            print(f"🎉 All images processed!")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error checking progress: {e}")

if __name__ == "__main__":
    check_processing_progress()
