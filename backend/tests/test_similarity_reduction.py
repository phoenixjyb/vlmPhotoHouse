from pathlib import Path
from uuid import uuid4

from app.db import Asset
from app.main import SessionLocal


def _hash64(seed: str) -> str:
    s = (seed or uuid4().hex).replace("-", "")
    return (s * 64)[:64]


def test_similarity_reduction_apply_hides_and_restore_unhides(client, temp_env_root):
    prefix = f"simdup-{uuid4().hex[:8]}"
    same_hash = _hash64(uuid4().hex)

    with SessionLocal() as session:
        a1 = Asset(path=str(Path(temp_env_root["originals"]) / f"{prefix}_1.jpg"), hash_sha256=same_hash, mime="image/jpeg")
        a2 = Asset(path=str(Path(temp_env_root["originals"]) / f"{prefix}_2.jpg"), hash_sha256=same_hash, mime="image/jpeg")
        a3 = Asset(path=str(Path(temp_env_root["originals"]) / f"{prefix}_3.jpg"), hash_sha256=same_hash, mime="image/jpeg")
        session.add_all([a1, a2, a3])
        session.commit()
        ids = {int(a1.id), int(a2.id), int(a3.id)}

    preview = client.get("/duplicates/reduction/preview?min_group_size=2&max_distance=5&sample_limit=500&cluster_limit=30")
    assert preview.status_code == 200
    groups = preview.json().get("groups", [])
    target = None
    for g in groups:
        member_ids = {int(m["id"]) for m in g.get("members", [])}
        if ids.issubset(member_ids):
            target = g
            break
    assert target is not None
    assert target["kind"] == "sha256"

    apply_resp = client.post(
        "/duplicates/reduction/apply",
        json={"min_group_size": 2, "max_distance": 5, "sample_limit": 500, "cluster_limit": 30},
    )
    assert apply_resp.status_code == 200

    with SessionLocal() as session:
        rows = session.query(Asset).filter(Asset.path.like(f"%{prefix}%")).all()
        statuses = {int(a.id): str(a.status) for a in rows}
    assert len([aid for aid in ids if statuses.get(aid) == "active"]) == 1
    assert len([aid for aid in ids if statuses.get(aid) == "suppressed"]) == 2

    visible_after_apply = client.get(f"/search?q={prefix}&page=1&page_size=20")
    assert visible_after_apply.status_code == 200
    assert int(visible_after_apply.json()["total"]) == 1

    restore_resp = client.post("/duplicates/reduction/restore", json={"asset_ids": list(ids)})
    assert restore_resp.status_code == 200
    assert int(restore_resp.json()["restored"]) == 2

    with SessionLocal() as session:
        rows = session.query(Asset).filter(Asset.path.like(f"%{prefix}%")).all()
        statuses = [str(a.status) for a in rows]
    assert statuses.count("active") == 3

    visible_after_restore = client.get(f"/search?q={prefix}&page=1&page_size=20")
    assert visible_after_restore.status_code == 200
    assert int(visible_after_restore.json()["total"]) == 3


def test_similarity_reduction_preview_includes_near_duplicates(client, temp_env_root):
    prefix = f"simnear-{uuid4().hex[:8]}"
    with SessionLocal() as session:
        a1 = Asset(
            path=str(Path(temp_env_root["originals"]) / f"{prefix}_1.jpg"),
            hash_sha256=_hash64("a"),
            perceptual_hash="0000000000000000",
            mime="image/jpeg",
        )
        a2 = Asset(
            path=str(Path(temp_env_root["originals"]) / f"{prefix}_2.jpg"),
            hash_sha256=_hash64("b"),
            perceptual_hash="0000000000000001",
            mime="image/jpeg",
        )
        session.add_all([a1, a2])
        session.commit()
        expected_ids = {int(a1.id), int(a2.id)}

    preview = client.get("/duplicates/reduction/preview?min_group_size=2&max_distance=1&sample_limit=500&cluster_limit=30")
    assert preview.status_code == 200
    groups = preview.json().get("groups", [])
    near_group = None
    for g in groups:
        if g.get("kind") != "near":
            continue
        member_ids = {int(m["id"]) for m in g.get("members", [])}
        if expected_ids.issubset(member_ids):
            near_group = g
            break
    assert near_group is not None
    assert int(near_group["keep_asset_id"]) in expected_ids
    assert len(near_group.get("hide_asset_ids", [])) == 1
