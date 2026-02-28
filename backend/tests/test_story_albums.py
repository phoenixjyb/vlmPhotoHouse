from pathlib import Path
from uuid import uuid4

from app.db import Asset, Caption, FaceDetection, Person
from app.main import SessionLocal
from app.tagging import upsert_asset_tags


def _new_hash64() -> str:
    return f"{uuid4().hex}{uuid4().hex}"


def test_story_albums_endpoint_groups_people_tags_location_caption(client, temp_env_root):
    tag_name = f"story-tag-{uuid4().hex[:8]}"
    shared_caption = "A toddler playing in a playground with a slide."
    prefix = uuid4().hex[:8]

    with SessionLocal() as session:
        a1 = Asset(
            path=str(Path(temp_env_root["originals"]) / f"{prefix}_story_a1.jpg"),
            hash_sha256=_new_hash64(),
            mime="image/jpeg",
            gps_lat=31.2304,
            gps_lon=121.4737,
        )
        a2 = Asset(
            path=str(Path(temp_env_root["originals"]) / f"{prefix}_story_a2.jpg"),
            hash_sha256=_new_hash64(),
            mime="image/jpeg",
            gps_lat=31.2305,
            gps_lon=121.4738,
        )
        a3 = Asset(
            path=str(Path(temp_env_root["originals"]) / f"{prefix}_story_a3.jpg"),
            hash_sha256=_new_hash64(),
            mime="image/jpeg",
            gps_lat=31.2306,
            gps_lon=121.4736,
        )
        session.add_all([a1, a2, a3])
        session.commit()

        person = Person(display_name=f"jane-story-{prefix}")
        session.add(person)
        session.flush()
        person_id = int(person.id)

        session.add_all(
            [
                FaceDetection(
                    asset_id=int(a1.id),
                    bbox_x=0.1,
                    bbox_y=0.1,
                    bbox_w=0.4,
                    bbox_h=0.4,
                    person_id=person_id,
                    label_source="manual",
                    label_score=1.0,
                ),
                FaceDetection(
                    asset_id=int(a2.id),
                    bbox_x=0.2,
                    bbox_y=0.2,
                    bbox_w=0.4,
                    bbox_h=0.4,
                    person_id=person_id,
                    label_source="manual",
                    label_score=1.0,
                ),
            ]
        )

        session.add_all(
            [
                Caption(asset_id=int(a1.id), text=shared_caption, model="http-qwen-vl"),
                Caption(asset_id=int(a3.id), text=shared_caption, model="http-qwen-vl"),
            ]
        )
        session.commit()

        upsert_asset_tags(
            session,
            asset_id=int(a2.id),
            names=[tag_name],
            tag_type="object",
            source="cap",
            source_model="http-qwen-vl",
        )
        upsert_asset_tags(
            session,
            asset_id=int(a3.id),
            names=[tag_name],
            tag_type="object",
            source="img",
            source_model="ram-plus",
        )
        session.commit()

    resp = client.get("/albums/stories?media=all&story_type=all&min_assets=2&max_stories_per_type=8&story_asset_limit=12")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 4
    stories = payload["stories"]
    story_types = {str(s.get("type")) for s in stories}
    assert {"person", "tag", "location", "caption"}.issubset(story_types)

    person_story = next(s for s in stories if s.get("type") == "person")
    assert person_story["open"]["mode"] == "person"
    assert int(person_story["open"]["person_id"]) == person_id
    assert int(person_story["count"]) >= 2
    assert len(person_story["items"]) >= 2

    tag_story = next(s for s in stories if s.get("type") == "tag" and s.get("title") == tag_name)
    assert tag_story["open"]["mode"] == "tag"
    assert int(tag_story["count"]) >= 2

    location_story = next(s for s in stories if s.get("type") == "location")
    assert location_story["open"]["mode"] == "location"
    assert "lat" in location_story["open"]
    assert "lon" in location_story["open"]

    caption_story = next(s for s in stories if s.get("type") == "caption")
    assert caption_story["open"]["mode"] == "caption"
    assert str(caption_story["open"]["query"]).strip() != ""
    assert int(caption_story["count"]) >= 2


def test_story_albums_endpoint_rejects_invalid_filters(client):
    bad_story_type = client.get("/albums/stories?story_type=bad")
    assert bad_story_type.status_code == 400

    bad_media = client.get("/albums/stories?media=bad")
    assert bad_media.status_code == 400
