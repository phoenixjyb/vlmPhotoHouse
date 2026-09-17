#!/usr/bin/env python3
"""Offline drift check for the backend-owned protected native candidate pack."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = Path('docs/contracts/protected-native-v2')
SOURCE = '0ea007535545003b0c7fc2bae5efad6b75132278'


def verify(root=ROOT):
    root = Path(root).resolve()
    manifest = json.loads((root / PACK / 'manifest.json').read_text())
    if manifest['backend_source_commit'] != SOURCE:
        raise ValueError('Unexpected backend source pin')
    if manifest['contract_version'] != '2.0.0-candidate.6':
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
    required = {str(PACK / name) for name in ('CONTRACT.md', 'UPLOAD_NEXT.md', 'VALIDATION.md', 'cases.json')}
    required |= {'scripts/verify_protected_native_contract.py',
                 'tests/security/native_contract_v2_probe.py',
                 'tests/security/test_protected_native_contract.py'}
    if set(payloads) != required:
        raise ValueError('Incomplete or unexpected payload set')
    # Pin all application Python and migration code, including transitive imports.
    expected_sources = {
        str(path.relative_to(root))
        for directory in ('backend/app', 'backend/migrations')
        for path in (root / directory).rglob('*.py')
        if '__pycache__' not in path.parts
    }
    expected_sources |= {'tests/security/test_library_reads.py',
                         'tests/security/test_access_foundation.py',
                         'tests/security/test_orm_migrations.py',
                         'tests/security/fixtures/home-8x8.jpg', 'backend/alembic.ini',
                         'scripts/home_media_worker.py', 'backend/requirements-access.lock',
                         'backend/requirements-access-test.lock'}
    if set(manifest['source_sha256']) != expected_sources:
        raise ValueError('Source closure has changed; review and version the profile')
    cases = json.loads((root / PACK / 'cases.json').read_text())
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
