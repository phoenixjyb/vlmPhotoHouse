from __future__ import annotations
from sqlalchemy.orm import Session
import os
from pathlib import Path
from typing import Iterable
from ..db import Asset, Embedding, FaceDetection
from ..paths import DERIVED_PATH

def remove_asset_files(session: Session, asset: Asset):
    emb = session.query(Embedding).filter(Embedding.asset_id==asset.id).first()
    if emb is not None:
        sp = emb.storage_path
        if sp is not None and isinstance(sp, str) and os.path.exists(sp):
            try:
                os.remove(sp)
            except OSError:
                pass
    for size in ('256','1024'):
        thumb = DERIVED_PATH / 'thumbnails' / size / f'{asset.id}.jpg'
        if thumb.exists():
            try:
                thumb.unlink()
            except OSError:
                pass
    faces = session.query(FaceDetection).filter(FaceDetection.asset_id==asset.id).all()
    for f in faces:
        crop = DERIVED_PATH / 'faces' / '256' / f'{f.id}.jpg'
        if crop.exists():
            try:
                crop.unlink()
            except OSError:
                pass
        ep = f.embedding_path
        if ep is not None and isinstance(ep, str) and os.path.exists(ep):
            try:
                os.remove(ep)
            except OSError:
                pass

