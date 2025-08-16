"""
Test script for Person-Based Search functionality.

This script demonstrates the complete person workflow:
1. Asset ingestion
2. Face detection
3. Face embedding
4. Person clustering
5. Person management (naming, merging)
6. Person-based search

Note: This is a demonstration script. In a real environment, you would
have actual photos and the ML models would be properly configured.
"""

import sys
sys.path.insert(0, 'backend')

from app.main import app
from fastapi.testclient import TestClient
import tempfile
import json
from PIL import Image
import io

def create_test_image(name: str, size=(400, 300)):
    """Create a simple test image with text overlay."""
    from PIL import ImageDraw, ImageFont
    
    img = Image.new('RGB', size, color='lightblue')
    draw = ImageDraw.Draw(img)
    
    # Try to use a default font, fallback to basic if not available
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()
    
    # Add text to image
    text = f"Test Photo: {name}"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = (size[0] - text_width) // 2
    y = (size[1] - text_height) // 2
    
    draw.text((x, y), text, fill='darkblue', font=font)
    
    return img

def test_person_search_workflow():
    """Test the complete person search workflow."""
    client = TestClient(app)
    
    print("=" * 60)
    print("PERSON-BASED SEARCH WORKFLOW TEST")
    print("=" * 60)
    
    # Step 1: Check initial state
    print("\n1. Checking initial state...")
    response = client.get('/health')
    health = response.json()
    print(f"   API Status: {response.status_code}")
    print(f"   Vector Index: {health.get('index', {}).get('initialized', False)}")
    
    response = client.get('/persons')
    persons_data = response.json()
    print(f"   Total Persons: {persons_data.get('total', 0)}")
    
    # Step 2: Test person search endpoints (should be empty initially)
    print("\n2. Testing person search endpoints with empty database...")
    
    # Test person search by ID (should fail)
    response = client.get('/search/person/999')
    print(f"   Search by non-existent person: {response.status_code} (expected 404)")
    
    # Test person search by name (should return empty)
    response = client.get('/search/person/name/John')
    if response.status_code == 200:
        search_data = response.json()
        print(f"   Search by name 'John': {search_data.get('total', 0)} results (expected 0)")
    
    # Step 3: Simulate asset ingestion (create mock assets)
    print("\n3. Simulating asset ingestion...")
    
    # Note: In a real environment, you would upload actual photos
    # Here we'll create test images and upload them
    test_images = [
        ("john_photo1.jpg", "Photo of John"),
        ("jane_photo1.jpg", "Photo of Jane"), 
        ("group_photo.jpg", "Group photo with John and Jane"),
    ]
    
    uploaded_assets = []
    for filename, description in test_images:
        try:
            # Create test image
            img = create_test_image(description)
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='JPEG')
            img_bytes.seek(0)
            
            # Upload image
            files = {'file': (filename, img_bytes.getvalue(), 'image/jpeg')}
            response = client.post('/upload', files=files)
            
            if response.status_code == 200:
                asset_data = response.json()
                uploaded_assets.append(asset_data)
                print(f"   ✓ Uploaded {filename}: Asset ID {asset_data.get('asset_id')}")
            else:
                print(f"   ✗ Failed to upload {filename}: {response.status_code}")
                
        except Exception as e:
            print(f"   ✗ Error uploading {filename}: {e}")
    
    print(f"   Total uploaded assets: {len(uploaded_assets)}")
    
    # Step 4: Check if face detection would be triggered
    print("\n4. Checking task system...")
    response = client.get('/tasks?type=face_detect')
    if response.status_code == 200:
        tasks_data = response.json()
        print(f"   Face detection tasks: {tasks_data.get('total', 0)}")
    
    # Step 5: Simulate person creation (since we don't have real faces detected)
    print("\n5. Creating test persons manually...")
    
    # Create test persons
    test_persons = []
    for name in ["John Doe", "Jane Smith"]:
        # Note: In real usage, persons are created automatically by clustering
        # or manually through the assign face endpoints
        # Here we simulate having persons
        try:
            # We'll use the face assignment endpoint to create persons
            response = client.post('/faces/assign', json={
                'face_ids': [],  # Empty list since we don't have real faces
                'create_new': True
            })
            if response.status_code == 200:
                person_data = response.json()
                person_id = person_data.get('person_id')
                
                # Set the person name
                response = client.post(f'/persons/{person_id}/name', json={
                    'display_name': name
                })
                if response.status_code == 200:
                    test_persons.append({'id': person_id, 'name': name})
                    print(f"   ✓ Created person: {name} (ID: {person_id})")
                    
        except Exception as e:
            print(f"   ✗ Error creating person {name}: {e}")
    
    # Step 6: Test person management endpoints
    print("\n6. Testing person management...")
    
    response = client.get('/persons')
    if response.status_code == 200:
        persons_data = response.json()
        print(f"   Total persons: {persons_data.get('total', 0)}")
        for person in persons_data.get('persons', []):
            print(f"     - {person.get('display_name')} (ID: {person.get('id')}, Faces: {person.get('face_count')})")
    
    # Step 7: Test person search endpoints
    print("\n7. Testing person-based search...")
    
    for person in test_persons:
        person_id = person['id']
        name = person['name']
        
        # Test search by person ID
        response = client.get(f'/search/person/{person_id}')
        print(f"   Search by person ID {person_id} ({name}): {response.status_code}")
        if response.status_code == 200:
            search_data = response.json()
            print(f"     Results: {search_data.get('total', 0)} photos")
        
        # Test search by person name
        search_name = name.split()[0]  # First name only
        response = client.get(f'/search/person/name/{search_name}')
        print(f"   Search by name '{search_name}': {response.status_code}")
        if response.status_code == 200:
            search_data = response.json()
            matched = search_data.get('matched_persons', [])
            print(f"     Matched persons: {len(matched)}")
            print(f"     Results: {search_data.get('total', 0)} photos")
    
    # Step 8: Test vector search with person filter
    print("\n8. Testing vector search with person filter...")
    
    if test_persons:
        person_id = test_persons[0]['id']
        
        # Test text-based vector search with person filter
        response = client.post('/search/person/vector', json={
            'text': 'photo',
            'person_id': person_id,
            'k': 5
        })
        print(f"   Vector search with person filter: {response.status_code}")
        if response.status_code == 200:
            search_data = response.json()
            results = search_data.get('results', [])
            filter_info = search_data.get('person_filter', {})
            print(f"     Results: {len(results)} items")
            print(f"     Filter: Person {filter_info.get('person_id')} ({filter_info.get('person_name')})")
        elif response.status_code == 503:
            print("     Vector index not initialized (expected in test environment)")
    
    # Step 9: Test person merging
    print("\n9. Testing person merging...")
    
    if len(test_persons) >= 2:
        target_id = test_persons[0]['id']
        source_id = test_persons[1]['id']
        
        response = client.post('/persons/merge', json={
            'target_id': target_id,
            'source_ids': [source_id]
        })
        print(f"   Merge persons {source_id} → {target_id}: {response.status_code}")
        if response.status_code == 200:
            merge_data = response.json()
            print(f"     Moved faces: {merge_data.get('moved_faces', 0)}")
            print(f"     Final face count: {merge_data.get('face_count', 0)}")
    
    # Step 10: Summary
    print("\n10. Workflow Summary...")
    response = client.get('/persons')
    if response.status_code == 200:
        persons_data = response.json()
        print(f"    Final person count: {persons_data.get('total', 0)}")
    
    response = client.get('/faces')
    if response.status_code == 200:
        faces_data = response.json()
        print(f"    Total faces: {faces_data.get('total', 0)}")
    
    response = client.get('/assets')
    if response.status_code == 200:
        assets_data = response.json()
        print(f"    Total assets: {assets_data.get('total', 0)}")
    
    print("\n" + "=" * 60)
    print("PERSON-BASED SEARCH TEST COMPLETE")
    print("=" * 60)
    
    print("\nNext steps for production use:")
    print("1. Ingest real photos with faces")
    print("2. Configure face detection models (MTCNN, etc.)")
    print("3. Configure face embedding models (Facenet, LVFace, etc.)")
    print("4. Run face clustering to create persons automatically")
    print("5. Use person management API to refine clusters")
    print("6. Search photos by person using the new endpoints")

if __name__ == "__main__":
    test_person_search_workflow()
