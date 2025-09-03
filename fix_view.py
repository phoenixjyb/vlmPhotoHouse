import sqlite3

conn = sqlite3.connect('metadata.sqlite')
cursor = conn.cursor()

# Drop the existing view and recreate it with correct column names
cursor.execute('DROP VIEW IF EXISTS enhanced_face_detections')

view_sql = '''
CREATE VIEW enhanced_face_detections AS
SELECT 
    fd.*,
    a.path as file_path,
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
conn.commit()

# Test the view
cursor.execute('SELECT COUNT(*) FROM enhanced_face_detections')
count = cursor.fetchone()[0]
print(f'✅ Enhanced view created successfully with {count} records')

# Show sample data
cursor.execute('SELECT file_path, bbox_x, bbox_y, bbox_w, bbox_h, confidence_score, face_quality FROM enhanced_face_detections LIMIT 3')
print('\n📊 Sample enhanced face detection data:')
for row in cursor.fetchall():
    print(f'  {row}')

conn.close()
