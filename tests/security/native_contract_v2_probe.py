"""Capture real protected ASGI wire cases using migrated synthetic storage only.

No listener or live configuration. Random accounts/tokens are replaced with explicit
synthetic identities. Photo rendering is stubbed at the existing CPU cache boundary;
authorization, file opens, routing, serializers and original Range reads are real.
"""
import base64
import hashlib
import json
from pathlib import Path
import uuid
from unittest.mock import patch

import test_library_reads as fixture
from app.access.service import AccessService
from app.access.media import MediaRuntime
from app.photo_delivery import PhotoCache

ROOT = Path(__file__).resolve().parents[2]
VERSION = '2.0.0-candidate.2'


def capture():
    fixture.LibraryReadTests.setUpClass()
    env = fixture.LibraryReadTests()
    env.setUp()
    try:
        env.client.headers.pop('sec-fetch-site', None)
        # The legacy caption table defaults to wall-clock SQL time; fix fixture
        # input rather than normalizing serializer output and hiding wire drift.
        env.mutate("UPDATE captions SET created_at='2026-01-01 00:00:00', updated_at=NULL")
        identities = {env.owner_token: 'O' * 43, env.member_token: 'V' * 43,
                      env.other_token: 'X' * 43}
        for number, token in enumerate((env.owner_token, env.member_token, env.other_token), 1):
            with env.connection() as db:
                profile = AccessService(db, clock=lambda: env.now).profile(token)
            identities[profile['account_id']] = str(uuid.UUID(int=number))
        cases = []

        def normalize(value):
            if isinstance(value, dict): return {k: normalize(v) for k, v in value.items()}
            if isinstance(value, list): return [normalize(v) for v in value]
            return identities.get(value, value) if isinstance(value, str) else value

        def call(name, method, path, status, *, token=None, body=None, headers=None, record=True):
            sent = dict(headers or {})
            if token: sent['Authorization'] = 'Bearer ' + token
            response = env.client.request(method, path, json=body, headers=sent)
            assert response.status_code == status, (name, response.status_code, response.text[:200])
            assert response.headers.get('cache-control') == 'no-store', name
            if path in ('/auth/register', '/auth/login') and status in (200, 201):
                assert 'set-cookie' not in response.headers, name
            if not record: return response
            selected = {k: response.headers[k] for k in ('content-type', 'cache-control', 'content-range',
                        'accept-ranges', 'retry-after') if k in response.headers}
            if method == 'HEAD': output = None
            elif 'application/json' in selected.get('content-type', ''): output = response.json()
            else: output = {'encoding': 'base64', 'data': base64.b64encode(response.content).decode(),
                            'sha256': hashlib.sha256(response.content).hexdigest(), 'bytes': len(response.content)}
            # Token normalization happens at the value boundary, never by fuzzy replacement.
            request = {'method': method, 'path': path, 'credential':
                       'none' if token is None else token, 'headers': dict(headers or {})}
            if body is not None: request['json'] = body
            cases.append({'id': name, 'request': request,
                          'response': {'status': status, 'headers': selected, 'body': output}})
            return response

        call('anonymous_session', 'GET', '/auth/session', 401)
        call('anonymous_library', 'GET', '/assets?library=family-a', 401)
        denied = {'phone': '+12025550105', 'password': 'Test1234', 'code': '0' * 32, 'transport': 'native'}
        call('registration_requires_invitation', 'POST', '/auth/register', 401, body=denied)
        with env.connection() as db:
            assert not db.execute('SELECT 1 FROM access_accounts WHERE phone_login=?', (denied['phone'],)).fetchone()
        invitation = call('owner_invitation', 'POST', '/libraries/family-a/invitations', 201,
                          token=env.owner_token, body={'phone': denied['phone']}).json()['code']
        identities[invitation] = '11111111-22222222-33333333-44444444'
        registration = {**denied, 'code': invitation}
        for size in (7, 129):
            call('registration_password_' + str(size), 'POST', '/auth/register', 401,
                 body={**registration, 'password': 'a' * size})
        registered = call('invited_registration_8', 'POST', '/auth/register', 201,
                          body=registration).json()
        native = registered['access_token']; identities[native] = 'N' * 43
        with env.connection() as db:
            new_id = AccessService(db, clock=lambda: env.now).profile(native)['account_id']
        identities[new_id] = str(uuid.UUID(int=4))
        login_body = {'phone': denied['phone'], 'password': 'Test1234', 'transport': 'native'}
        logged = call('login_8', 'POST', '/auth/login', 200, body=login_body).json()
        identities[logged['access_token']] = 'L' * 43
        call('native_login_rejects_origin', 'POST', '/auth/login', 403, body=login_body,
             headers={'Origin': 'https://photohouse.test'})
        call('invited_viewer_session', 'GET', '/auth/session', 200, token=native)
        call('bearer_rejects_origin', 'GET', '/auth/session', 401, token=native,
             headers={'Origin': 'https://photohouse.test'})
        call('viewer_cannot_invite', 'POST', '/libraries/family-a/invitations', 401,
             token=native, body={'phone': '+12025550106'})
        other_invitation = call('other_owner_invitation', 'POST', '/libraries/family-b/invitations', 201,
                                token=env.other_token, body={'phone': denied['phone']}).json()['code']
        identities[other_invitation] = '22222222-33333333-44444444-55555555'
        call('owner_cancel_invitation', 'POST', '/libraries/family-b/invitations/cancel', 200,
             token=env.other_token, body={'code': other_invitation})
        call('cancelled_invitation_denied', 'POST', '/auth/invitations/accept', 401,
             token=native, body={'code': other_invitation})
        replacement = call('replacement_invitation', 'POST', '/libraries/family-b/invitations', 201,
                           token=env.other_token, body={'phone': denied['phone']}).json()['code']
        identities[replacement] = '33333333-44444444-55555555-66666666'
        call('existing_account_accepts_invitation', 'POST', '/auth/invitations/accept', 200,
             token=native, body={'code': replacement})
        call('accepted_second_library_session', 'GET', '/auth/session', 200, token=native)
        call('owner_member_list', 'GET', '/libraries/family-a/members?page=1&page_size=10', 200, token=env.owner_token)
        call('gallery_page_one', 'GET', '/assets?library=family-a&page=1&page_size=1', 200, token=native)
        call('gallery_page_two', 'GET', '/assets?library=family-a&page=2&page_size=1', 200, token=native)
        call('gallery_duplicate_query', 'GET', '/assets?library=family-a&page=1&page=2', 400, token=native)
        call('asset_detail', 'GET', '/assets/detail/101?library=family-a', 200, token=native)
        call('foreign_asset', 'GET', '/assets/detail/201?library=family-a', 401, token=native)
        call('captions', 'GET', '/assets/101/captions?library=family-a', 200, token=native)

        root = env.path.parent
        originals, derived = root / 'originals', root / 'derived'
        originals.mkdir(); derived.mkdir()
        jpeg = (ROOT / 'tests/security/fixtures/home-8x8.jpg').read_bytes()
        photo = originals / '101.jpg'; photo.write_bytes(jpeg)
        env.mutate('UPDATE assets SET path=? WHERE id=101', (str(photo),))
        thumb = derived / 'thumbnails/256/101.jpg'; thumb.parent.mkdir(parents=True); thumb.write_bytes(jpeg)
        env.client.app.state.media_runtime = MediaRuntime((originals,), derived)
        call('cached_thumbnail', 'GET', '/assets/101/thumbnail?library=family-a', 200, token=native)
        call('thumbnail_head', 'HEAD', '/assets/101/thumbnail?library=family-a', 200, token=native)
        call('display_without_provider', 'GET', '/assets/101/display?library=family-a', 503, token=native)
        cache = PhotoCache(root / 'cache')
        env.client.app.state.media_runtime = MediaRuntime((originals,), derived, cache)
        with patch.object(PhotoCache, 'render_opened', return_value=jpeg):
            call('display_library_read', 'GET', '/assets/101/display?library=family-a', 200, token=native)
            thumb.unlink()
            call('thumbnail_on_demand', 'GET', '/assets/101/thumbnail?library=family-a', 200, token=native)
        call('original_without_grant', 'GET', '/assets/101/media?library=family-a', 401, token=native)
        env.mutate('UPDATE access_memberships SET originals=1 WHERE account_id=?', (new_id,))
        call('original_range', 'GET', '/assets/101/media?library=family-a', 206, token=native, headers={'Range': 'bytes=0-15'})
        call('original_if_range_full', 'GET', '/assets/101/media?library=family-a', 200, token=native,
             headers={'Range': 'bytes=0-15', 'If-Range': 'synthetic-weak-validator'})
        call('original_invalid_range', 'GET', '/assets/101/media?library=family-a', 400, token=native, headers={'Range': 'bytes=0-1,4-5'})
        call('original_range_eof', 'GET', '/assets/101/media?library=family-a', 416, token=native, headers={'Range': 'bytes=999999-'})
        photo.unlink()
        call('missing_original', 'GET', '/assets/101/media?library=family-a', 404, token=native)

        initial = None
        for i in range(1, 7):
            body = {'title': 'Memory ' + str(i), 'text': 'A family story. 奶奶的花园。', 'byline': 'Synthetic author',
                    'language': 'mixed', 'mutation_id': str(uuid.UUID(int=200+i))}
            with patch('app.access.stories.uuid.uuid4', return_value=uuid.UUID(int=100+i)):
                response = call('story_create_' + str(i), 'POST', '/assets/101/stories?library=family-a', 201,
                                token=env.owner_token, body=body, record=(i == 1))
            if i == 1: initial = body; story = response.json()
        call('story_list_page_one', 'GET', '/assets/101/stories?library=family-a&page=1', 200, token=native)
        call('story_list_page_two', 'GET', '/assets/101/stories?library=family-a&page=2', 200, token=native)
        call('viewer_cannot_create_story', 'POST', '/assets/101/stories?library=family-a', 401, token=native, body=initial)
        story_path = '/stories/' + story['id']
        call('viewer_cannot_read_history', 'GET', story_path + '/history?library=family-a', 401, token=native)
        edited = {**initial, 'text': 'The current story. 奶奶的新故事。', 'revision': '1', 'mutation_id': str(uuid.UUID(int=301))}
        call('story_update', 'PUT', story_path + '?library=family-a', 200, token=env.owner_token, body=edited)
        call('story_stale_update', 'PUT', story_path + '?library=family-a', 409, token=env.owner_token,
             body={**edited, 'mutation_id': str(uuid.UUID(int=302))})
        call('story_exact_old_retry', 'POST', '/assets/101/stories?library=family-a', 201, token=env.owner_token, body=initial)
        call('story_history', 'GET', story_path + '/history?library=family-a', 200, token=env.owner_token)
        call('story_search', 'POST', '/library/search?library=family-a', 200, token=native,
             body={'text': '新故事', 'source': 'family', 'media': 'all', 'page': '1'})
        tombstone = {'revision': '2', 'mutation_id': str(uuid.UUID(int=401))}
        call('story_delete', 'DELETE', story_path + '?library=family-a', 200, token=env.owner_token, body=tombstone)
        call('story_delete_retry', 'DELETE', story_path + '?library=family-a', 200, token=env.owner_token, body=tombstone)
        call('story_deleted_search', 'POST', '/library/search?library=family-a', 200, token=native,
             body={'text': '新故事', 'source': 'family', 'media': 'all', 'page': '1'})
        for path in ('/upload', '/voice/transcribe', '/auth/refresh'):
            call('closed_' + path.strip('/').replace('/', '_'), 'POST', path, 403, token=native, body={})
        env.mutate("UPDATE access_memberships SET status='revoked', revision=revision+1 WHERE account_id=?", (new_id,))
        call('revoked_session_still_authenticated', 'GET', '/auth/session', 200, token=native)
        call('revoked_story_list', 'GET', '/assets/101/stories?library=family-a', 401, token=native)
        call('native_logout', 'POST', '/auth/logout', 200, token=native)
        call('native_logout_retry', 'POST', '/auth/logout', 200, token=native)
        call('logged_out_session', 'GET', '/auth/session', 401, token=native)
        call('wrong_password', 'POST', '/auth/login', 401,
             body={**login_body, 'password': 'incorrect'})
        call('login_rate_limited', 'POST', '/auth/login', 429, body=login_body)
        env.now += 86401
        call('expired_session', 'GET', '/auth/session', 401, token=logged['access_token'])
        return {'contract_version': VERSION, 'synthetic_only': True,
                'normalization': 'random account IDs/session tokens/invitation code replaced with fixed synthetic values; story IDs fixed in generator',
                'media_evidence': 'generated fixture JPEG; on-demand renderer stubbed; authorization/file/range behavior real; no decoder/device claim',
                'cases': normalize(cases)}
    finally:
        env.doCleanups()
        fixture.LibraryReadTests.tearDownClass()


if __name__ == '__main__':
    print(json.dumps(capture(), ensure_ascii=False, indent=2))
