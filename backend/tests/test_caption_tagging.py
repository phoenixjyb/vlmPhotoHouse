from pathlib import Path
from uuid import uuid4

from app.db import Asset, AssetTag, AssetTagBlock, Tag
from app.main import SessionLocal
from app.tagging import extract_caption_tag_candidates, upsert_asset_tags
from app.tasks import _caption_model_allowed_for_auto_tag


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


def test_caption_auto_tag_model_filter_defaults_to_qwen(monkeypatch):
    monkeypatch.delenv("CAPTION_AUTO_TAG_SOURCE_MODEL_CONTAINS", raising=False)
    assert _caption_model_allowed_for_auto_tag("http-qwen-vl")
    assert not _caption_model_allowed_for_auto_tag("http-blip2")


def test_caption_auto_tag_model_filter_supports_override(monkeypatch):
    monkeypatch.setenv("CAPTION_AUTO_TAG_SOURCE_MODEL_CONTAINS", "blip2")
    assert _caption_model_allowed_for_auto_tag("http-blip2")
    assert not _caption_model_allowed_for_auto_tag("http-qwen-vl")


def test_tags_catalog_endpoint_lists_counts_and_sources(client, temp_env_root):
    tag_name = f"stroller-catalog-{uuid4().hex[:8]}"
    asset1_path = str(Path(temp_env_root["originals"]) / "tags_catalog_asset_1.jpg")
    asset2_path = str(Path(temp_env_root["originals"]) / "tags_catalog_asset_2.jpg")
    with SessionLocal() as session:
        a1 = Asset(path=asset1_path, hash_sha256="d" * 64, mime="image/jpeg")
        a2 = Asset(path=asset2_path, hash_sha256="e" * 64, mime="image/jpeg")
        session.add_all([a1, a2])
        session.commit()

        upsert_asset_tags(
            session,
            asset_id=int(a1.id),
            names=[tag_name],
            tag_type="object",
            source="cap",
            source_model="http-qwen-vl",
        )
        session.commit()
        upsert_asset_tags(
            session,
            asset_id=int(a1.id),
            names=[tag_name],
            tag_type="object",
            source="img",
            source_model="ram-plus",
        )
        session.commit()
        upsert_asset_tags(
            session,
            asset_id=int(a2.id),
            names=[tag_name],
            tag_type="object",
            source="img",
            source_model="ram-plus",
        )
        session.commit()

    resp = client.get(f"/tags?q={tag_name}&page=1&page_size=20")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 1
    stroller = next(row for row in payload["rows"] if row["name"] == tag_name)
    assert stroller["assets"] == 2
    assert stroller["links"] == 2
    assert stroller["sources"]["cap+img"] == 1
    assert stroller["sources"]["img"] == 1

    resp_img = client.get(f"/tags?q={tag_name}&source=img&page=1&page_size=20")
    assert resp_img.status_code == 200
    stroller_img = next(row for row in resp_img.json()["rows"] if row["name"] == tag_name)
    assert stroller_img["assets"] == 1
    assert stroller_img["links"] == 1

    resp_bad = client.get("/tags?source=bad-source")
    assert resp_bad.status_code == 400


def test_tag_assets_endpoint_supports_media_and_source_filters(client, temp_env_root):
    tag_name = f"tag-assets-{uuid4().hex[:8]}"
    image_path = str(Path(temp_env_root["originals"]) / "tag_assets_image.jpg")
    video_path = str(Path(temp_env_root["originals"]) / "tag_assets_video.mp4")
    with SessionLocal() as session:
        a_img = Asset(path=image_path, hash_sha256="f" * 64, mime="image/jpeg")
        a_vid = Asset(path=video_path, hash_sha256="0" * 64, mime="video/mp4")
        session.add_all([a_img, a_vid])
        session.commit()

        upsert_asset_tags(
            session,
            asset_id=int(a_img.id),
            names=[tag_name],
            tag_type="object",
            source="cap",
            source_model="http-qwen-vl",
        )
        session.commit()
        upsert_asset_tags(
            session,
            asset_id=int(a_vid.id),
            names=[tag_name],
            tag_type="object",
            source="img",
            source_model="ram-plus",
        )
        session.commit()

    catalog = client.get(f"/tags?q={tag_name}&page=1&page_size=10")
    assert catalog.status_code == 200
    row = next(r for r in catalog.json()["rows"] if r["name"] == tag_name)
    tag_id = int(row["id"])

    all_assets = client.get(f"/tags/{tag_id}/assets?media=all&source=all&page=1&page_size=20")
    assert all_assets.status_code == 200
    all_payload = all_assets.json()
    assert all_payload["total"] == 2
    assert len(all_payload["items"]) == 2

    image_only = client.get(f"/tags/{tag_id}/assets?media=image&source=all&page=1&page_size=20")
    assert image_only.status_code == 200
    assert image_only.json()["total"] == 1
    assert str(image_only.json()["items"][0]["mime"]).startswith("image/")

    video_only = client.get(f"/tags/{tag_id}/assets?media=video&source=all&page=1&page_size=20")
    assert video_only.status_code == 200
    assert video_only.json()["total"] == 1
    assert str(video_only.json()["items"][0]["mime"]).startswith("video/")

    source_img = client.get(f"/tags/{tag_id}/assets?media=all&source=img&page=1&page_size=20")
    assert source_img.status_code == 200
    assert source_img.json()["total"] == 1
    assert str(source_img.json()["items"][0]["mime"]).startswith("video/")

    bad_source = client.get(f"/tags/{tag_id}/assets?source=bad")
    assert bad_source.status_code == 400

    bad_media = client.get(f"/tags/{tag_id}/assets?media=bad")
    assert bad_media.status_code == 400
