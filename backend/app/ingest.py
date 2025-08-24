import hashlib, os, time, mimetypes, io
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime
import exifread
from sqlalchemy.orm import Session
from .db import Asset, Task
from .config import get_settings
from PIL import Image

# Image extensions always supported
SUPPORTED_IMAGE_EXT = {'.jpg','.jpeg','.png','.heic','.webp'}

def sha256_file(path: Path, buf_size: int = 1024*1024) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            chunk = f.read(buf_size)
            if not chunk: break
            h.update(chunk)
    return h.hexdigest()

def extract_exif_datetime(tags) -> Optional[datetime]:
    for key in ("EXIF DateTimeOriginal","EXIF DateTimeDigitized","Image DateTime"):
        if key in tags:
            try:
                raw = str(tags[key])
                return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
            except Exception:
                continue
    return None

def read_exif(path: Path) -> dict:
    out = {}
    try:
        with path.open('rb') as f:
            tags = exifread.process_file(f, details=False)
        dt = extract_exif_datetime(tags)
        if dt: out['taken_at'] = dt
        out['camera_make'] = str(tags.get('Image Make','') )[:64]
        out['camera_model'] = str(tags.get('Image Model','') )[:64]
    except Exception:
        pass
    return out

def ingest_paths(session: Session, roots: List[str]) -> dict:
    new_assets = 0
    skipped = 0
    start = time.time()
    settings = get_settings()
    # Build allowed extensions set (images + optional videos)
    allowed_ext = set(SUPPORTED_IMAGE_EXT)
    if getattr(settings, 'video_enabled', False):
        try:
            vids = [e.strip().lower() for e in settings.video_extensions.split(',') if e.strip()]
            allowed_ext.update(vids)
        except Exception:
            pass
    for root in roots:
        for p in Path(root).rglob('*'):
            if not p.is_file():
                continue
            if p.suffix.lower() not in allowed_ext:
                continue
            rel = str(p.resolve())
            existing = session.query(Asset).filter_by(path=rel).first()
            if existing:
                skipped +=1
                continue
            sha = sha256_file(p)
            width = height = None
            mime = None
            exif = {}
            if p.suffix.lower() in SUPPORTED_IMAGE_EXT:
                exif = read_exif(p)
                try:
                    with Image.open(p) as im:
                        width, height = im.size
                except Exception:
                    pass
                mime = 'image/jpeg' if p.suffix.lower() in ('.jpg','.jpeg') else mimetypes.guess_type(p.name)[0]
            else:
                # Video: we don't probe heavy metadata in ingest (MVP)
                mime = mimetypes.guess_type(p.name)[0] or 'video/unknown'
            asset = Asset(path=rel, hash_sha256=sha, file_size=p.stat().st_size, width=width, height=height, mime=mime, **exif)
            session.add(asset)
            session.flush()
            # enqueue tasks
            tasks_to_create = []
            if p.suffix.lower() in SUPPORTED_IMAGE_EXT:
                tasks_to_create.extend([
                    Task(type='embed', priority=50, payload_json={'asset_id': asset.id, 'modality': 'image'}),
                    Task(type='phash', priority=60, payload_json={'asset_id': asset.id}),
                    Task(type='thumb', priority=80, payload_json={'asset_id': asset.id}),
                    Task(type='caption', priority=110, payload_json={'asset_id': asset.id}),
                    Task(type='face', priority=120, payload_json={'asset_id': asset.id}),
                ])
            else:
                # Minimal video pipeline: probe + keyframes + embed (all optional/no-op stubs for now)
                if settings.video_enabled:
                    tasks_to_create.extend([
                        Task(type='video_probe', priority=40, payload_json={'asset_id': asset.id}),
                        Task(type='video_keyframes', priority=70, payload_json={'asset_id': asset.id}),
                        Task(type='video_embed', priority=90, payload_json={'asset_id': asset.id}),
                    ])
                    # Optional scene detection
                    if getattr(settings, 'video_scene_detect', False):
                        tasks_to_create.append(Task(type='video_scene_detect', priority=80, payload_json={'asset_id': asset.id}))
            for t in tasks_to_create:
                session.add(t)
            new_assets +=1
        session.commit()
    return {
        'new_assets': new_assets,
        'skipped': skipped,
        'elapsed_sec': round(time.time()-start,2)
    }
