from pathlib import Path

import pytest

from app.config import get_settings
from app.db import Asset, Person, FaceDetection
from app.main import SessionLocal


@pytest.fixture
def voice_env(monkeypatch):
    monkeypatch.setenv('VOICE_ENABLED', 'true')
    monkeypatch.setenv('VOICE_PROVIDER', 'external')
    monkeypatch.setenv('VOICE_EXTERNAL_BASE_URL', 'http://127.0.0.1:8001')
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_voice_command_search_assets_read_only(client, temp_env_root, voice_env):
    _ = voice_env

    asset_path = str(Path(temp_env_root['originals']) / 'vacation_sunset.jpg')
    with SessionLocal() as session:
        asset = Asset(path=asset_path, hash_sha256='1' * 64, mime='image/jpeg')
        session.add(asset)
        session.commit()

    resp = client.post('/voice/command', json={'text': 'search vacation', 'language': 'en', 'limit': 5})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['success'] is True
    assert payload['phase'] == 'phase2-read-only'
    assert payload['executed'] is True
    assert payload['contract']['action'] == 'search.assets'
    assert payload['contract']['mode'] == 'read'
    assert payload['contract']['needs_confirmation'] is False
    assert payload['data']['total'] >= 1
    assert any('vacation' in str(item['path']).lower() for item in payload['data']['items'])


def test_voice_command_blocks_mutating_request(client, voice_env):
    _ = voice_env

    resp = client.post('/voice/command', json={'text': 'rename person 12 to Alice', 'language': 'en'})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['success'] is True
    assert payload['executed'] is False
    assert payload['contract']['action'] == 'mutate.request'
    assert payload['contract']['mode'] == 'mutate'
    assert payload['contract']['needs_confirmation'] is True
    assert payload['data']['reason'] == 'confirmation_required'


def test_voice_command_show_person_photos(client, temp_env_root, voice_env):
    _ = voice_env

    asset_path = str(Path(temp_env_root['originals']) / 'chuan_birthday.jpg')
    with SessionLocal() as session:
        person = Person(display_name='Chuan', face_count=1)
        asset = Asset(path=asset_path, hash_sha256='2' * 64, mime='image/jpeg')
        session.add_all([person, asset])
        session.flush()
        face = FaceDetection(
            asset_id=asset.id,
            person_id=person.id,
            bbox_x=0.1,
            bbox_y=0.1,
            bbox_w=0.4,
            bbox_h=0.4,
            label_source='manual',
            label_score=1.0,
        )
        session.add(face)
        session.commit()

    resp = client.post('/voice/command', json={'text': 'show me the photos of chuan', 'language': 'en', 'limit': 10})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['success'] is True
    assert payload['executed'] is True
    assert payload['contract']['action'] == 'search.person.assets'
    assert payload['contract']['mode'] == 'read'
    assert payload['data']['person_name'] == 'Chuan'
    assert payload['data']['total'] >= 1
    assert any('chuan' in str(item['path']).lower() for item in payload['data']['items'])

    resp2 = client.post('/voice/command', json={'text': 'show me the photo of a chuan', 'language': 'en', 'limit': 10})
    assert resp2.status_code == 200
    payload2 = resp2.json()
    assert payload2['contract']['action'] == 'search.person.assets'
    assert payload2['data']['person_name'] == 'Chuan'


def test_voice_command_show_person_photos_chinese(client, temp_env_root, voice_env):
    _ = voice_env

    asset_path = str(Path(temp_env_root['originals']) / 'chuan_cn.jpg')
    with SessionLocal() as session:
        person = Person(display_name='川川', face_count=1)
        asset = Asset(path=asset_path, hash_sha256='3' * 64, mime='image/jpeg')
        session.add_all([person, asset])
        session.flush()
        face = FaceDetection(
            asset_id=asset.id,
            person_id=person.id,
            bbox_x=0.2,
            bbox_y=0.2,
            bbox_w=0.3,
            bbox_h=0.3,
            label_source='manual',
            label_score=1.0,
        )
        session.add(face)
        session.commit()

    resp = client.post('/voice/command', json={'text': '给我看一下川川的照片', 'language': 'zh', 'limit': 10})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['success'] is True
    assert payload['executed'] is True
    assert payload['contract']['action'] == 'search.person.assets'
    assert payload['contract']['mode'] == 'read'
    assert payload['data']['person_name'] == '川川'
    assert payload['data']['total'] >= 1
