#!/usr/bin/env python3
"""
Enhanced Face Detection Database Schema Update
Adds support for unified YOLOv8 face detection + LVFace recognition pipeline
"""

import sqlite3
import os
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def update_face_schema():
    """Update face_detections table with enhanced schema for unified pipeline"""
    
    db_path = 'metadata.sqlite'
    if not os.path.exists(db_path):
        logger.error(f"Database {db_path} not found!")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        logger.info("📊 Current face_detections schema:")
        cursor.execute('PRAGMA table_info(face_detections)')
        current_columns = {row[1]: row for row in cursor.fetchall()}
        for col_name, col_info in current_columns.items():
            logger.info(f"  {col_name}: {col_info[2]} (nullable: {not col_info[3]})")
        
        # Define new columns for enhanced face detection
        new_columns = [
            # Face detection metadata
            ('detection_method', 'VARCHAR(50)', 'DEFAULT "yolov8"', 'Detection method used (yolov8, opencv, etc.)'),
            ('confidence_score', 'FLOAT', 'DEFAULT 0.0', 'Detection confidence score (0.0-1.0)'),
            ('detection_model', 'VARCHAR(100)', 'DEFAULT "yolov8n"', 'Specific model version used'),
            
            # Face quality metrics
            ('face_quality', 'FLOAT', 'DEFAULT 0.0', 'Face quality score (0.0-1.0)'),
            ('blur_score', 'FLOAT', 'DEFAULT 0.0', 'Face blur assessment'),
            ('brightness_score', 'FLOAT', 'DEFAULT 0.0', 'Face brightness assessment'),
            
            # Face landmarks (optional, for future alignment)
            ('landmarks_x', 'TEXT', '', 'JSON array of landmark x coordinates'),
            ('landmarks_y', 'TEXT', '', 'JSON array of landmark y coordinates'),
            
            # Recognition metadata
            ('embedding_model', 'VARCHAR(100)', 'DEFAULT "lvface"', 'Embedding model used'),
            ('embedding_dim', 'INTEGER', 'DEFAULT 512', 'Embedding vector dimension'),
            ('recognition_confidence', 'FLOAT', 'DEFAULT 0.0', 'Recognition confidence if matched'),
            
            # Processing metadata
            ('processing_time_ms', 'FLOAT', 'DEFAULT 0.0', 'Total processing time in milliseconds'),
            ('gpu_used', 'BOOLEAN', 'DEFAULT 1', 'Whether GPU was used for processing'),
            ('last_updated', 'DATETIME', 'DEFAULT CURRENT_TIMESTAMP', 'Last update timestamp')
        ]
        
        # Add new columns if they don't exist
        columns_added = 0
        for col_name, col_type, col_default, description in new_columns:
            if col_name not in current_columns:
                try:
                    alter_sql = f'ALTER TABLE face_detections ADD COLUMN {col_name} {col_type}'
                    if col_default:
                        alter_sql += f' {col_default}'
                    
                    cursor.execute(alter_sql)
                    logger.info(f"✅ Added column: {col_name} ({description})")
                    columns_added += 1
                except sqlite3.Error as e:
                    logger.error(f"❌ Failed to add column {col_name}: {e}")
        
        # Create indices for better performance
        indices = [
            ('idx_face_detection_method', 'detection_method'),
            ('idx_face_confidence', 'confidence_score'),
            ('idx_face_quality', 'face_quality'),
            ('idx_face_person_id', 'person_id'),
            ('idx_face_embedding_model', 'embedding_model'),
            ('idx_face_last_updated', 'last_updated')
        ]
        
        indices_created = 0
        for idx_name, idx_column in indices:
            try:
                cursor.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON face_detections({idx_column})')
                logger.info(f"📊 Created index: {idx_name}")
                indices_created += 1
            except sqlite3.Error as e:
                logger.warning(f"⚠️ Index {idx_name} might already exist: {e}")
        
        # Create a view for enhanced face detection results
        view_sql = '''
        CREATE VIEW IF NOT EXISTS enhanced_face_detections AS
        SELECT 
            fd.*,
            a.file_path,
            a.file_name,
            a.width as image_width,
            a.height as image_height,
            CASE 
                WHEN fd.confidence_score >= 0.8 THEN 'high'
                WHEN fd.confidence_score >= 0.5 THEN 'medium'
                ELSE 'low'
            END as confidence_category,
            CASE 
                WHEN fd.face_quality >= 0.7 THEN 'excellent'
                WHEN fd.face_quality >= 0.5 THEN 'good'
                WHEN fd.face_quality >= 0.3 THEN 'fair'
                ELSE 'poor'
            END as quality_category
        FROM face_detections fd
        JOIN assets a ON fd.asset_id = a.id
        '''
        
        cursor.execute(view_sql)
        logger.info("📊 Created enhanced_face_detections view")
        
        conn.commit()
        
        # Show updated schema
        logger.info("🎉 Updated face_detections schema:")
        cursor.execute('PRAGMA table_info(face_detections)')
        for row in cursor.fetchall():
            logger.info(f"  {row[1]}: {row[2]} (nullable: {not row[3]})")
        
        # Show statistics
        cursor.execute('SELECT COUNT(*) FROM face_detections')
        total_faces = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT person_id) FROM face_detections WHERE person_id IS NOT NULL')
        unique_persons = cursor.fetchone()[0]
        
        logger.info(f"📈 Database statistics:")
        logger.info(f"  Total faces: {total_faces}")
        logger.info(f"  Unique persons: {unique_persons}")
        logger.info(f"  Columns added: {columns_added}")
        logger.info(f"  Indices created: {indices_created}")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        logger.error(f"❌ Database error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False

def validate_schema_update():
    """Validate that the schema update was successful"""
    try:
        conn = sqlite3.connect('metadata.sqlite')
        cursor = conn.cursor()
        
        # Check for key new columns
        required_columns = ['detection_method', 'confidence_score', 'face_quality', 'processing_time_ms']
        cursor.execute('PRAGMA table_info(face_detections)')
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        missing_columns = [col for col in required_columns if col not in existing_columns]
        
        if missing_columns:
            logger.error(f"❌ Missing columns after update: {missing_columns}")
            return False
        
        # Test the enhanced view
        cursor.execute('SELECT COUNT(*) FROM enhanced_face_detections')
        view_count = cursor.fetchone()[0]
        logger.info(f"✅ Enhanced view working with {view_count} records")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Validation failed: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Updating face detection database schema...")
    print("=" * 60)
    
    if update_face_schema():
        print("\n✅ Schema update completed successfully!")
        
        if validate_schema_update():
            print("✅ Schema validation passed!")
        else:
            print("❌ Schema validation failed!")
    else:
        print("❌ Schema update failed!")
