#!/usr/bin/env python3
"""Build a fixed source-only package for approved-upload worker qualification.

The package contains no media, credentials, model weights, environment, or
launcher registration. Its immutable commit and per-file hashes are recorded so
the Windows operator can qualify the exact installed source before activation.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = tuple(sorted([
    *('backend/app/' + name + '.py' for name in (
        '__init__', 'config', 'image_utils', 'vector_index',
        'face_detection_service', 'face_embedding_service', 'metrics',
        'scoped_face_worker')),
    *('scripts/' + name + '.py' for name in (
        'home_media_worker', 'home_preparation_resources', 'home_memory_envelope',
        'run_approved_cpu_worker', 'run_approved_video_worker',
        'run_approved_image_embed_worker', 'run_approved_video_embed_worker',
        'run_approved_face_worker', 'qualify_approved_workers_windows')),
    'docs/security/APPROVED_UPLOAD_PROCESSING_V37.md',
]))


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def source_files(commit: str) -> dict[str, bytes]:
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or git('cat-file', '-t', commit).strip() != b'commit':
        raise ValueError('Explicit immutable local commit required')
    entries = {}
    for row in filter(None, git('ls-tree', '-r', '-z', '--full-tree', commit, '--', *FILES).split(b'\0')):
        identity, name = row.split(b'\t', 1)
        mode, kind, oid = identity.decode('ascii').split()
        if mode not in ('100644', '100755') or kind != 'blob':
            raise ValueError('Regular source blobs required')
        entries[name.decode('utf-8')] = oid
    if set(entries) != set(FILES):
        raise ValueError('Worker source files missing')
    sizes = {name: int(git('cat-file', '-s', oid)) for name, oid in entries.items()}
    if any(size > 1_000_000 for size in sizes.values()) or sum(sizes.values()) > 5_000_000:
        raise ValueError('Worker source budget exceeded')
    return {name: git('cat-file', 'blob', entries[name]) for name in FILES}


def package_bytes(commit: str, files: dict[str, bytes]) -> bytes:
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or set(files) != set(FILES):
        raise ValueError('Exact immutable worker source manifest required')
    manifest = {
        'format_version': 1, 'source_commit': commit,
        'artifact_kind': 'approved_upload_workers_source_only',
        'schema_revision': 'a8d4c2e6f901', 'activated': False,
        'dependencies_included': False, 'private_configuration_included': False,
        'model_weights_included': False, 'media_included': False,
        'files': {name: hashlib.sha256(files[name]).hexdigest() for name in FILES},
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in [*sorted(files.items()),
                           ('manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())]:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if (not args.out.is_absolute() or '..' in args.out.parts
                or args.out.parent.resolve(strict=True) != args.out.parent):
            raise ValueError('Explicit direct output required')
        data = package_bytes(args.commit, source_files(args.commit))
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
        with os.fdopen(os.open(args.out, flags, 0o600), 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({'source_commit': args.commit, 'files': len(FILES),
                          'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                          'activated': False}))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError):
        print('Worker packaging refused; existing output was not overwritten.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
