import hashlib, os, time, mimetypes, io
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime
import exifread
from sqlalchemy.orm import Session
from .db import Asset, Task
from PIL import Image

SUPPORTED_EXT = {'.jpg','.jpeg','.png','.heic','.webp'}

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
    for root in roots:
        for p in Path(root).rglob('*'):
            if not p.is_file():
                continue
            if p.suffix.lower() not in SUPPORTED_EXT:
                continue
            rel = str(p.resolve())
            existing = session.query(Asset).filter_by(path=rel).first()
            if existing:
                skipped +=1
                continue
            sha = sha256_file(p)
            exif = read_exif(p)
            width = height = None
            try:
                with Image.open(p) as im:
                    width, height = im.size
            except Exception:
                pass
            asset = Asset(path=rel, hash_sha256=sha, file_size=p.stat().st_size, width=width, height=height, **exif)
            session.add(asset)
            session.flush()
            # enqueue tasks
            tasks_to_create = [
                Task(type='embed', priority=50, payload_json={'asset_id': asset.id, 'modality': 'image'}),
                Task(type='phash', priority=60, payload_json={'asset_id': asset.id}),
                Task(type='thumb', priority=80, payload_json={'asset_id': asset.id}),
                Task(type='caption', priority=110, payload_json={'asset_id': asset.id}),
                Task(type='face', priority=120, payload_json={'asset_id': asset.id}),
            ]
            for t in tasks_to_create:
                session.add(t)
            new_assets +=1
        session.commit()
    return {
        'new_assets': new_assets,
        'skipped': skipped,
        'elapsed_sec': round(time.time()-start,2)
    }
