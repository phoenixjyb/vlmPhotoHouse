#!/usr/bin/env python3
"""Create an enabled synthetic v2 publication in a NEW directory; never listen."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.home_catalog import CHUNK_BYTES, asset_result, validate_catalog


def sha(data): return hashlib.sha256(data).hexdigest()


def build(output):
    if not output.is_absolute() or output.exists(): raise ValueError('New absolute output required')
    jpeg = (ROOT/'tests/security/fixtures/home-8x8.jpg').read_bytes()
    video = (ROOT/'tests/security/fixtures/home-video.mp4').read_bytes()
    chunks = json.dumps([sha(video[i:i+CHUNK_BYTES]) for i in range(0, len(video), CHUNK_BYTES)]).encode()
    preview = {'state': 'ready', 'width': 8, 'height': 8, 'bytes': len(jpeg), 'sha256': sha(jpeg)}
    missing = {'state': 'unavailable', 'reason': 'not_prepared'}
    stream = {'state': 'ready', 'mime': 'video/mp4', 'video_codec': 'h264', 'audio_codec': 'aac',
              'width': 320, 'height': 180, 'duration_ms': 500, 'bytes': len(video), 'sha256': sha(video), 'chunks_sha256': sha(chunks)}
    value = validate_catalog({'version': 2, 'revision': 1, 'library_id': 'synthetic-library', 'title': 'Synthetic / 合成',
        'assets': [{'id': 102, 'kind': 'video', 'label': 'Synthetic video', 'width': None, 'height': None,
                    'previews': {'grid': dict(missing), 'display': dict(missing)}, 'video': stream},
                   {'id': 101, 'kind': 'photo', 'label': 'Synthetic photo', 'width': 8, 'height': 8,
                    'previews': {'grid': dict(preview), 'display': dict(preview)}, 'video': None}]})
    raw = json.dumps(value).encode()
    output.mkdir(mode=0o700)
    (output/'catalog.json').write_bytes(raw)
    (output/'control.json').write_text(json.dumps({'version': 2, 'enabled': True, 'revision': 1, 'catalog_sha256': sha(raw)}))
    for variant in ('grid', 'display', 'video'): (output/'prepared'/variant).mkdir(parents=True)
    for variant in ('grid', 'display'): (output/'prepared'/variant/'101.jpg').write_bytes(jpeg)
    (output/'prepared/video/102.mp4').write_bytes(video)
    (output/'prepared/video/102.chunks.json').write_bytes(chunks)
    return {'version': 2, 'revision': 1, 'library': {'id': value['library_id'], 'title': value['title']},
            'page': 1, 'page_size': 50, 'total': 2, 'has_more': False,
            'items': [asset_result(a, 1) for a in value['assets']]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); print(json.dumps(build(args.output)))
