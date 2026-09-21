#!/usr/bin/env python3
"""Offline drift check for the backend-owned protected native candidate pack."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = Path('docs/contracts/protected-native-v2')
SOURCE = 'd6192b91bc0983ab7b67aa14458eb052ed3c0ee6'


def verify(root=ROOT):
    root = Path(root).resolve()
    manifest = json.loads((root / PACK / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['backend_source_commit'] != SOURCE:
        raise ValueError('Unexpected backend source pin')
    if manifest['contract_version'] != '2.0.0-candidate.22':
        raise ValueError('Unexpected contract version')
    if manifest['client_profile_defaults'] != {
        'protected_native_v2': False, 'protected_photo_display': False,
        'protected_story_read': False,
    }:
        raise ValueError('Client profile must remain explicitly off by default')
    groups = ('source_sha256', 'payload_sha256')
    for group in groups:
        entries = manifest[group]
        if not entries:
            raise ValueError('Empty hash group: ' + group)
        for name, digest in entries.items():
            path = Path(name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Invalid manifest path: ' + name)
            target = (root / path).resolve()
            if not target.is_relative_to(root):
                raise ValueError('Manifest path escapes repository: ' + name)
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError('Hash mismatch: ' + name)
    payloads = manifest['payload_sha256']
    required = {(PACK / name).as_posix() for name in ('CONTRACT.md', 'UPLOAD_NEXT.md', 'VALIDATION.md', 'cases.json')}
    required |= {'scripts/verify_protected_native_contract.py',
                 'tests/security/native_contract_v2_probe.py',
                 'tests/security/test_protected_native_contract.py'}
    if set(payloads) != required:
        raise ValueError('Incomplete or unexpected payload set')
    # Pin all application Python and migration code, including transitive imports.
    expected_sources = {
        path.relative_to(root).as_posix()
        for directory in ('backend/app', 'backend/migrations')
        for path in (root / directory).rglob('*.py')
        if '__pycache__' not in path.parts
    }
    expected_sources |= {'scripts/prepare_access_places.py',
                         'scripts/create_library_presets.py',
                         'docs/security/LIBRARY_ORGANIZATION_V27.md',
                         'scripts/prepare_access_discovery_index.py',
                         'docs/security/PLACE_BROWSING_V24.md',
                         'docs/security/PLACE_REFRESH_V25.md',
                         'docs/security/PLACE_NAME_SEARCH_V26.md',
                         'docs/security/place-catalogue-china-starter.json',
                         'docs/security/PLACE_CATALOGUE_SOURCES.md',
                         'tests/security/test_place_name_search.py',
                         'tests/security/test_library_organization.py',
                         'tests/security/test_promotion.py',
                         'docs/security/route_capabilities.json',
                         'tests/security/test_phone_discovery_http.py',
                         'tests/security/phone_discovery_fixture.py',
                         'tests/security/test_library_reads.py',
                         'tests/security/test_gallery_media_filter.py',
                         'tests/security/test_access_foundation.py',
                         'tests/security/test_orm_migrations.py',
                         'tests/security/fixtures/home-8x8.jpg', 'tests/security/fixtures/home-video.mp4',
                         'scripts/export_protected_videos.py', 'scripts/staging_app.py',
                         'scripts/build_staging_package.py', 'docs/security/PROTECTED_PREPARED_MEDIA.md',
                         'backend/alembic.ini',
                         'scripts/home_media_worker.py', 'backend/requirements-access.lock',
                         'backend/requirements-access-test.lock'}
    if set(manifest['source_sha256']) != expected_sources:
        raise ValueError('Source closure has changed; review and version the profile')
    cases = json.loads((root / PACK / 'cases.json').read_text(encoding='utf-8'))
    if (cases['contract_version'] != manifest['contract_version']
            or cases['synthetic_only'] is not True
            or len(cases['cases']) != manifest['case_count']):
        raise ValueError('Case metadata mismatch')
    ids = [case['id'] for case in cases['cases']]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate case IDs')
    return manifest


if __name__ == '__main__':
    result = verify()
    print(f"PASS {result['contract_version']}: {result['case_count']} cases; "
          f"{len(result['source_sha256'])} source hashes; "
          f"{len(result['payload_sha256'])} payload hashes; profile defaults off")
