from pathlib import Path
from uuid import uuid4

from app.db import Asset, FaceDetection
from app.main import SessionLocal


def _hash64() -> str:
    return f"{uuid4().hex}{uuid4().hex}"


def test_assign_face_stranger_creates_and_reuses_group(client, temp_env_root):
    asset_path = str(Path(temp_env_root["originals"]) / f"stranger_face_{uuid4().hex}.jpg")
    with SessionLocal() as session:
        asset = Asset(path=asset_path, hash_sha256=_hash64(), mime="image/jpeg")
        session.add(asset)
        session.flush()
        f1 = FaceDetection(asset_id=int(asset.id), bbox_x=0.1, bbox_y=0.1, bbox_w=0.3, bbox_h=0.3, person_id=None)
        f2 = FaceDetection(asset_id=int(asset.id), bbox_x=0.5, bbox_y=0.2, bbox_w=0.2, bbox_h=0.2, person_id=None)
        session.add_all([f1, f2])
        session.commit()
        face1_id = int(f1.id)
        face2_id = int(f2.id)

    first = client.post(f"/faces/{face1_id}/assign-stranger")
    assert first.status_code == 200
    first_body = first.json()
    stranger_person_id = int(first_body["person_id"])
    assert str(first_body.get("display_name") or "").strip().lower() == "stranger"
    assert bool(first_body.get("new_person_created")) is True

    second = client.post(f"/faces/{face2_id}/assign-stranger")
    assert second.status_code == 200
    second_body = second.json()
    assert int(second_body["person_id"]) == stranger_person_id
    assert bool(second_body.get("new_person_created")) is False

    faces = client.get("/faces", params={"person_id": stranger_person_id, "page": 1, "page_size": 20})
    assert faces.status_code == 200
    face_payload = faces.json()
    assert int(face_payload["total"]) == 2

    persons = client.get("/persons", params={"named_only": True, "name_query": "stranger", "page": 1, "page_size": 20})
    assert persons.status_code == 200
    person_payload = persons.json()
    assert any(int(p["id"]) == stranger_person_id for p in person_payload.get("persons", []))

    hist = client.get("/faces/assignment-history", params={"face_id": face1_id, "page": 1, "page_size": 10})
    assert hist.status_code == 200
    events = hist.json().get("events", [])
    assert any(e.get("reason") == "api.assign_face_stranger" for e in events)


def test_assign_face_stranger_returns_404_for_unknown_face(client):
    r = client.post("/faces/999999999/assign-stranger")
    assert r.status_code == 404
