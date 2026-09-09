from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.db import Asset
from app.main import SessionLocal


def _asset(temp_env_root, name: str, taken_at: datetime, *, status: str = 'active') -> int:
    with SessionLocal() as session:
        asset = Asset(
            path=str(Path(temp_env_root['originals']) / f'{uuid4().hex}_{name}.jpg'),
            hash_sha256=f'{uuid4().hex}{uuid4().hex}',
            mime='image/jpeg',
            taken_at=taken_at,
            status=status,
        )
        session.add(asset)
        session.commit()
        return int(asset.id)


def test_album_draft_create_list_get_and_update(client, temp_env_root):
    oldest = _asset(temp_env_root, 'oldest', datetime(2022, 5, 1, 9, 0, 0))
    middle = _asset(temp_env_root, 'middle', datetime(2023, 6, 2, 10, 0, 0))
    newest = _asset(temp_env_root, 'newest', datetime(2024, 7, 3, 11, 0, 0))

    created = client.post(
        '/albums/drafts',
        json={
            'title': 'Summer together',
            'title_zh': '一起过夏天',
            'theme': 'seasonal',
            'asset_ids': [newest, oldest, middle, newest],
            'sort_mode': 'chronological',
            'source_kind': 'story',
            'source_ref': 'tag:summer',
        },
    )
    assert created.status_code == 201, created.text
    album = created.json()['album']
    album_id = int(album['id'])
    assert album['status'] == 'draft'
    assert album['theme'] == 'seasonal'
    assert album['title_zh'] == '一起过夏天'
    assert album['cover_asset_id'] == oldest
    assert album['asset_count'] == 3
    assert [item['id'] for item in album['items']] == [oldest, middle, newest]
    assert [item['position'] for item in album['items']] == [0, 1, 2]

    listed = client.get('/albums/drafts?page=1&page_size=20')
    assert listed.status_code == 200
    assert any(int(row['id']) == album_id for row in listed.json()['albums'])

    fetched = client.get(f'/albums/drafts/{album_id}')
    assert fetched.status_code == 200
    assert fetched.json()['album']['source_ref'] == 'tag:summer'

    updated = client.patch(
        f'/albums/drafts/{album_id}',
        json={
            'title': 'Our summer',
            'title_zh': '我们的夏天',
            'theme': 'trip',
            'asset_ids': [newest, oldest],
            'cover_asset_id': oldest,
        },
    )
    assert updated.status_code == 200, updated.text
    updated_album = updated.json()['album']
    assert updated_album['title'] == 'Our summer'
    assert updated_album['title_zh'] == '我们的夏天'
    assert updated_album['theme'] == 'trip'
    assert updated_album['cover_asset_id'] == oldest
    assert [item['id'] for item in updated_album['items']] == [newest, oldest]


def test_album_draft_validation_is_fail_closed(client, temp_env_root):
    active = _asset(temp_env_root, 'active', datetime(2024, 1, 1))
    hidden = _asset(temp_env_root, 'hidden', datetime(2024, 1, 2), status='hidden_similar')

    assert client.post('/albums/drafts', json={'title': '', 'asset_ids': [active]}).status_code == 400
    assert client.post(
        '/albums/drafts',
        json={'title': 'Bad theme', 'theme': 'unknown', 'asset_ids': [active]},
    ).status_code == 400
    assert client.post(
        '/albums/drafts',
        json={'title': 'Hidden item', 'asset_ids': [active, hidden]},
    ).status_code == 400
    assert client.post(
        '/albums/drafts',
        json={'title': 'Bad cover', 'asset_ids': [active], 'cover_asset_id': hidden},
    ).status_code == 400
    assert client.get('/albums/drafts/999999999').status_code == 404
