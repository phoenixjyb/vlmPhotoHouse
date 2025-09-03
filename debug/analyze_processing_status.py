#!/usr/bin/env python3
"""
Analyze the difference between processed images with no faces vs unprocessed images
"""

import sqlite3

def analyze_processing_status():
    """Analyze which images are processed vs have faces vs unprocessed"""
    
    print("🔍 PROCESSING STATUS ANALYSIS")
    print("=" * 60)
    
    try:
        conn = sqlite3.connect('app.db')
        cursor = conn.cursor()
        
        # 1. Total images in database
        cursor.execute("SELECT COUNT(*) FROM assets WHERE mime LIKE 'image/%' AND id > 5")
        total_images = cursor.fetchone()[0]
        
        # 2. Images that have been processed (have face_detections entries, even if 0 faces)
        # Note: Our current system only saves entries when faces are found
        cursor.execute("SELECT COUNT(DISTINCT asset_id) FROM face_detections")
        images_with_face_records = cursor.fetchone()[0]
        
        # 3. Let's check if there are images that were processed but had no faces
        # This would require checking our orchestrator's logic
        
        # 4. Images that definitely have faces detected
        cursor.execute("""
            SELECT COUNT(DISTINCT asset_id) 
            FROM face_detections 
            WHERE bbox_w > 0 AND bbox_h > 0
        """)
        images_with_valid_faces = cursor.fetchone()[0]
        
        # 5. Check some sample unprocessed images
        cursor.execute("""
            SELECT a.id, a.path 
            FROM assets a 
            WHERE a.mime LIKE 'image/%' 
            AND a.id > 5 
            AND a.id NOT IN (SELECT DISTINCT asset_id FROM face_detections)
            ORDER BY a.id 
            LIMIT 10
        """)
        unprocessed_samples = cursor.fetchall()
        
        print(f"📊 BREAKDOWN:")
        print(f"   Total images: {total_images}")
        print(f"   Images with face detection records: {images_with_face_records}")
        print(f"   Images with valid faces: {images_with_valid_faces}")
        print(f"   Unprocessed images: {total_images - images_with_face_records}")
        
        print(f"\n🤔 IMPORTANT DISTINCTION:")
        print(f"Our current orchestrator logic:")
        print(f"   ✅ Processes image → finds faces → saves to database")
        print(f"   ❌ Processes image → no faces found → NO database entry")
        print(f"   ❓ Never processed → no database entry")
        
        print(f"\nThis means images without database entries could be:")
        print(f"   1. Not yet processed")
        print(f"   2. Processed but no faces detected")
        
        if unprocessed_samples:
            print(f"\n📋 Sample 'unprocessed' images:")
            for asset_id, path in unprocessed_samples:
                filename = path.split('/')[-1] if '/' in path else path.split('\\')[-1]
                print(f"   Asset {asset_id}: {filename}")
        
        # Check our orchestrator's actual behavior
        print(f"\n🔍 CHECKING ORCHESTRATOR BEHAVIOR:")
        print(f"Let me check if the orchestrator saves 'no faces found' records...")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

def check_orchestrator_logic():
    """Check how the orchestrator handles images with no faces"""
    
    print(f"\n🔧 ORCHESTRATOR LOGIC ANALYSIS:")
    print("=" * 40)
    
    # Read the orchestrator code to see how it handles no faces
    try:
        with open('enhanced_face_orchestrator_unified.py', 'r') as f:
            content = f.read()
            
        # Look for the logic that handles saving results
        if 'if scrfd_result.get(\'faces\', 0) > 0:' in content:
            print("✅ Found the issue!")
            print("The orchestrator only saves to database when faces > 0")
            print("This means:")
            print("   - Images with faces → saved to database")
            print("   - Images with no faces → NOT saved to database")
            print("   - Unprocessed images → NOT in database")
            print()
            print("Result: We cannot distinguish between:")
            print("   1. Images processed but no faces found")
            print("   2. Images not yet processed")
            
        else:
            print("Need to check the save logic manually")
            
    except Exception as e:
        print(f"Error reading orchestrator: {e}")

def recommend_solution():
    """Recommend how to fix this"""
    
    print(f"\n💡 RECOMMENDED SOLUTION:")
    print("=" * 30)
    print("To distinguish processed vs unprocessed images:")
    print("1. Modify orchestrator to save entries even for 0 faces")
    print("2. Add a 'processed' flag or timestamp to assets table")
    print("3. Or create a separate 'processed_images' tracking table")
    print()
    print("For now, assume remaining images need processing")
    print("The 1,099 'remaining' images are likely unprocessed")

if __name__ == "__main__":
    analyze_processing_status()
    check_orchestrator_logic()
    recommend_solution()
