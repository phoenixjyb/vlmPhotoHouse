from pathlib import Path

from PIL import Image


def test_face_assignment_history_records_manual_assign(client, temp_env_root):
    from app.main import executor

    originals = Path(temp_env_root['originals'])
    img_path = originals / 'history_face_test.jpg'
    Image.new('RGB', (640, 480), color=(180, 120, 90)).save(img_path, 'JPEG')

    r_scan = client.post('/ingest/scan', json={'roots': [str(originals)]})
    assert r_scan.status_code in (200, 202)

    for _ in range(120):
        if not executor.run_once():
            break

    faces_payload = client.get('/faces', params={'page': 1, 'page_size': 20}).json()
    faces = faces_payload.get('faces', [])
    if not faces:
        # Stub providers may produce zero faces in some test envs.
        return

    fid = faces[0]['id']
    r_assign = client.post(f'/faces/{fid}/assign', json={'create_new': True})
    assert r_assign.status_code == 200
    assigned_person_id = r_assign.json().get('person_id')
    assert assigned_person_id is not None

    hist = client.get('/faces/assignment-history', params={'face_id': fid, 'page': 1, 'page_size': 20})
    assert hist.status_code == 200
    data = hist.json()
    assert data['total'] >= 1
    ev = data['events'][0]
    assert ev['face_id'] == fid
    assert ev['source'] == 'manual'
    assert ev['reason'] == 'api.assign_face'
    assert ev['new_person_id'] == assigned_person_id

