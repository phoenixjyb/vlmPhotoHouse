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
VERSION = '2.0.0-candidate.16'


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

        def call(name, method, path, status, *, token=None, body=None, headers=None, record=True, content=None):
            sent = dict(headers or {})
            if token: sent['Authorization'] = 'Bearer ' + token
            response = env.client.request(method, path, json=body, headers=sent, content=content)
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
            if content is not None:
                request['content'] = {'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
            cases.append({'id': name, 'request': request,
                          'response': {'status': status, 'headers': selected, 'body': output}})
            return response

        call('anonymous_session', 'GET', '/auth/session', 401)
        call('anonymous_library', 'GET', '/assets?library=family-a', 401)
        # A display name is required at registration: it is how the family recognises a member,
        # and it is the source of that member's incoming upload folder label.
        denied = {'phone': '+12025550105', 'password': 'Test1234', 'code': '0' * 32,
                  'transport': 'native', 'name': 'Synthetic Member'}
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

        # Additive gallery media captures use rows introduced after the existing
        # gallery cases, so all prior candidate cases retain their exact wire data.
        env.mutate("INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at) VALUES (104,'private-synthetic/104.mp4','private-hash-104','active','video/mp4',640,480,'2026-01-03')")
        env.mutate("INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at) VALUES (105,'private-synthetic/105.jpg','private-hash-105','active','image/jpeg',640,480,'2026-01-02T12:00:00')")
        env.mutate("INSERT INTO access_asset_libraries VALUES (104,'family-a')")
        env.mutate("INSERT INTO access_asset_libraries VALUES (105,'family-a')")
        env.mutate("UPDATE assets SET mime='video/mp4' WHERE id=101")
        call('gallery_media_default', 'GET', '/assets?library=family-a', 200, token=native)
        call('gallery_media_all', 'GET', '/assets?library=family-a&media=all', 200, token=native)
        call('gallery_media_image', 'GET', '/assets?library=family-a&media=image&page=1&page_size=1', 200, token=native)
        call('gallery_media_video_page_one', 'GET', '/assets?library=family-a&media=video&page=1&page_size=1', 200, token=native)
        call('gallery_media_video_page_two', 'GET', '/assets?library=family-a&media=video&page=2&page_size=1', 200, token=native)
        call('gallery_media_invalid', 'GET', '/assets?library=family-a&media=audio', 400, token=native)
        call('gallery_media_duplicate', 'GET', '/assets?library=family-a&media=image&media=video', 400, token=native)
        env.mutate("UPDATE assets SET mime='image/jpeg' WHERE id=101")

        root = env.path.parent.resolve()
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
        from app.access.prepared_video import PreparedVideos
        from app.home_catalog import identity
        from dataclasses import replace
        movie = originals/'102.mov'; movie.write_bytes(b'synthetic-original-video')
        env.mutate('UPDATE assets SET path=? WHERE id=102',(str(movie),))
        call('playback_without_provider','HEAD','/assets/102/playback?library=family-a',503,token=native)
        call('prepared_gallery_without_provider','GET','/assets?library=family-a&media=prepared_video',503,token=native)
        prepared = root/'prepared'; folder = prepared/'102-ready'; folder.mkdir(parents=True)
        video_bytes = (ROOT/'tests/security/fixtures/home-video.mp4').read_bytes()
        chunk_bytes = json.dumps([hashlib.sha256(video_bytes).hexdigest()]).encode()
        (folder/'video.mp4').write_bytes(video_bytes); (folder/'video.chunks.json').write_bytes(chunk_bytes)
        descriptor = dict(state='ready',mime='video/mp4',video_codec='h264',audio_codec=None,
            width=320,height=180,duration_ms=500,bytes=len(video_bytes),sha256=hashlib.sha256(video_bytes).hexdigest(),
            chunks_sha256=hashlib.sha256(chunk_bytes).hexdigest())
        index = root/'protected-videos.json'
        raw = json.dumps(dict(version=1,assets=[dict(id=102,source_identity=list(identity(movie)),
            directory=folder.name,video=descriptor)])).encode(); index.write_bytes(raw)
        provider = PreparedVideos(index,hashlib.sha256(raw).hexdigest(),prepared)
        env.client.app.state.media_runtime = replace(env.client.app.state.media_runtime,prepared_videos=provider)
        with env.connection() as db:
            previous_mime = db.execute('SELECT mime FROM assets WHERE id=102').fetchone()[0]
        env.mutate("UPDATE assets SET mime='video/mp4' WHERE id=102")
        call('prepared_gallery_page_one','GET','/assets?library=family-a&media=prepared_video&page_size=1',200,token=native)
        call('prepared_gallery_page_two','GET','/assets?library=family-a&media=prepared_video&page_size=1&page=2',200,token=native)
        call('prepared_gallery_foreign','GET','/assets?library=family-unavailable&media=prepared_video',401,token=native)
        call('prepared_gallery_anonymous','GET','/assets?library=family-a&media=prepared_video',401)
        call('prepared_gallery_duplicate','GET','/assets?library=family-a&media=prepared_video&media=all',400,token=native)
        call('prepared_gallery_invalid','GET','/assets?library=family-a&media=prepared',400,token=native)
        env.mutate('UPDATE assets SET mime=? WHERE id=102',(previous_mime,))
        call('playback_anonymous','GET','/assets/102/playback?library=family-a',401)
        call('playback_foreign','GET','/assets/201/playback?library=family-a',401,token=native)
        call('playback_head','HEAD','/assets/102/playback?library=family-a',200,token=native)
        call('playback_viewer_range','GET','/assets/102/playback?library=family-a',206,token=native,headers={'Range':'bytes=0-15'})
        call('playback_suffix','GET','/assets/102/playback?library=family-a',206,token=native,headers={'Range':'bytes=-8'})
        call('playback_range_eof','GET','/assets/102/playback?library=family-a',416,token=native,headers={'Range':'bytes=999999-'})
        call('playback_original_still_denied','GET','/assets/102/media?library=family-a',401,token=native)
        movie.write_bytes(b'changed-synthetic-original-video')
        call('playback_source_changed','GET','/assets/102/playback?library=family-a',409,token=native)
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
        # The member upload route is mounted in the default app but answers 503 until a
        # deployment opts in with an incoming root, so no existing deployment gains a write
        # surface by accident. It is not library-scoped: the accepted photo is in no library
        # until an operator promotes and assigns it.
        call('upload_requires_opt_in', 'POST', '/uploads', 503, token=native, body={})
        # Opt-in uploads preserve canonical provenance across retries and never grant
        # a library mapping. Real filesystem and DB; only the fixture JPEG is sent.
        from app.access.upload import UploadRuntime
        upload_access = env.client.app.state.access_runtime
        env.client.app.state.upload_runtime = UploadRuntime(upload_access, root / 'incoming', (root / 'originals',))
        with env.connection() as db:
            _, label = AccessService(db, clock=lambda: env.now).uploader(native)
        identities[label] = 'Synthetic-Member-00000000-0000-0000-0000-000000000004'
        upload_bytes = (ROOT / 'tests/security/fixtures/home-8x8.jpg').read_bytes()
        upload_headers = {'Content-Type': 'application/octet-stream',
                          'X-Upload-Filename': 'synthetic.jpg', 'X-Upload-Batch': 'a' * 32}
        accepted = call('upload_accepted', 'POST', '/uploads', 201, token=native,
                        headers=upload_headers, content=upload_bytes).json()
        call('upload_retry_other_batch', 'POST', '/uploads', 201, token=native,
             headers={**upload_headers, 'X-Upload-Batch': 'b' * 32}, content=upload_bytes)
        call('upload_not_in_library', 'GET', '/assets/detail/' + accepted['asset_id'] + '?library=family-a', 401, token=native)
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
        env.mutate("UPDATE access_memberships SET status='revoked', revision=revision+1 WHERE account_id=?",
                   (fixture.LibraryReadTests.member_id,))
        call('gallery_media_revoked', 'GET', '/assets?library=family-a&media=video', 401,
             token=env.member_token)
        call('prepared_gallery_revoked','GET','/assets?library=family-a&media=prepared_video',401,token=env.member_token)
        return {'contract_version': VERSION, 'synthetic_only': True,
                'normalization': 'random account IDs/session tokens/invitation code replaced with fixed synthetic values; story IDs fixed in generator',
                'media_evidence': 'generated fixture JPEG; on-demand renderer stubbed; authorization/file/range behavior real; gallery all/image/video filtering and denial captured; no decoder/device claim',
                'cases': normalize(cases)}
    finally:
        env.doCleanups()
        fixture.LibraryReadTests.tearDownClass()


if __name__ == '__main__':
    print(json.dumps(capture(), ensure_ascii=False, indent=2))
