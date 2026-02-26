from pathlib import Path

from app.db import Asset, AssetTag, AssetTagBlock, Tag
from app.main import SessionLocal
from app.tagging import extract_caption_tag_candidates, upsert_asset_tags


def test_extract_caption_tag_candidates_canonical_quota():
    text = (
        "A toddler is playing in an indoor play area with a ball pit and stroller. "
        "This is a portrait close-up photo. 天气是晴天。"
    )
    tags = extract_caption_tag_candidates(text, max_tags=8)
    names = {str(t.get("name")) for t in tags}
    types = [str(t.get("type")) for t in tags]

    assert 1 <= len(tags) <= 8
    assert "toddler" in names
    assert "playing" in names
    assert "indoor play area" in names
    assert ("ball pit" in names) or ("stroller" in names)
    assert "shot" in types
    assert types.count("shot") <= 1


def test_remove_tag_blocks_auto_readd_and_manual_add_unblocks(client, temp_env_root):
    asset_path = str(Path(temp_env_root["originals"]) / "tag_block_asset.jpg")
    with SessionLocal() as session:
        asset = Asset(path=asset_path, hash_sha256="b" * 64, mime="image/jpeg")
        session.add(asset)
        session.commit()
        asset_id = int(asset.id)

    add_resp = client.post(f"/assets/{asset_id}/tags", json={"names": ["ball pit"]})
    assert add_resp.status_code == 200

    tag_rows = client.get(f"/assets/{asset_id}/tags").json()["tags"]
    ball_pit = next(t for t in tag_rows if t["name"] == "ball pit")
    tag_id = int(ball_pit["id"])

    del_resp = client.request(
        "DELETE",
        f"/assets/{asset_id}/tags",
        json={"tag_ids": [tag_id], "block_auto": True},
    )
    assert del_resp.status_code == 200
    assert tag_id in del_resp.json().get("blocked_tag_ids", [])

    with SessionLocal() as session:
        added = upsert_asset_tags(session, asset_id=asset_id, names=["ball pit"], tag_type="caption-auto")
        session.commit()
    assert added == []

    names_after_block = [t["name"] for t in client.get(f"/assets/{asset_id}/tags").json()["tags"]]
    assert "ball pit" not in names_after_block

    add_again = client.post(f"/assets/{asset_id}/tags", json={"names": ["ball pit"]})
    assert add_again.status_code == 200

    with SessionLocal() as session:
        blocked_row = (
            session.query(AssetTagBlock)
            .filter(AssetTagBlock.asset_id == asset_id, AssetTagBlock.tag_id == tag_id)
            .first()
        )
        assert blocked_row is None

    names_final = [t["name"] for t in client.get(f"/assets/{asset_id}/tags").json()["tags"]]
    assert "ball pit" in names_final


def test_upsert_asset_tags_merges_cap_and_img_sources(temp_env_root):
    asset_path = str(Path(temp_env_root["originals"]) / "tag_source_merge_asset.jpg")
    with SessionLocal() as session:
        asset = Asset(path=asset_path, hash_sha256="c" * 64, mime="image/jpeg")
        session.add(asset)
        session.commit()
        asset_id = int(asset.id)

        upsert_asset_tags(
            session,
            asset_id=asset_id,
            names=["stroller"],
            tag_type="object",
            source="cap",
            source_model="http-qwen-vl",
            score_by_name={"stroller": 0.61},
        )
        session.commit()

        upsert_asset_tags(
            session,
            asset_id=asset_id,
            names=["stroller"],
            tag_type="object",
            source="img",
            source_model="ram-plus",
            score_by_name={"stroller": 0.84},
        )
        session.commit()

        tag = session.query(Tag).filter(Tag.name == "stroller").first()
        assert tag is not None
        link = session.query(AssetTag).filter(AssetTag.asset_id == asset_id, AssetTag.tag_id == tag.id).first()
        assert link is not None
        assert link.source == "cap+img"
        assert float(link.score or 0.0) >= 0.84
