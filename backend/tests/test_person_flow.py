def test_person_assignment_flow(client, temp_env_root):
    # ensure at least one person by running tasks after ingest
    from pathlib import Path
    from app.main import executor
    originals = Path(temp_env_root['originals'])
    # create one image
    from PIL import Image
    img_path = originals / 'face_test.jpg'
    Image.new('RGB', (500,400), color=(200,150,100)).save(img_path, 'JPEG')
    client.post('/ingest/scan', json={'roots':[str(originals)]})
    for _ in range(100):
        if not executor.run_once():
            break
    persons = client.get('/persons', params={'include_faces':True}).json()
    # updated key: total replaces count
    if persons['total'] == 0:
        return  # no faces generated in stub
    first = persons['persons'][0]
    pid = first['id']
    # update name
    r = client.post(f'/persons/{pid}/name', json={'display_name':'Alice'})
    assert r.status_code == 200
    # assign a face to new person
    faces = first.get('sample_faces') or []
    if faces:
        fid = faces[0]
        r = client.post(f'/faces/{fid}/assign', json={'new_person':True})
        assert r.status_code == 200
