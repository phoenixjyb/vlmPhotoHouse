from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import schemas
from ..db import Album, AlbumAsset, Asset
from ..dependencies import get_db


router = APIRouter()

ALBUM_THEMES = {
    'birthday',
    'trip',
    'growing_up',
    'grandparents',
    'year_in_review',
    'seasonal',
    'custom',
}
ALBUM_SORT_MODES = {'chronological', 'newest', 'as_provided'}
MAX_ALBUM_ASSETS = 60


def _clean_text(value: str | None, field: str, *, required: bool = False, limit: int = 160) -> str | None:
    cleaned = str(value or '').strip()
    if required and not cleaned:
        raise HTTPException(status_code=400, detail=f'{field} is required')
    if len(cleaned) > limit:
        raise HTTPException(status_code=400, detail=f'{field} must be at most {limit} characters')
    return cleaned or None


def _normalize_theme(value: str | None) -> str:
    theme = str(value or 'custom').strip().lower()
    if theme not in ALBUM_THEMES:
        raise HTTPException(status_code=400, detail='Invalid album theme')
    return theme


def _normalize_asset_ids(values: list[int] | None) -> list[int]:
    ordered: list[int] = []
    seen: set[int] = set()
    for raw in values or []:
        try:
            asset_id = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail='asset_ids must contain integers')
        if asset_id <= 0:
            raise HTTPException(status_code=400, detail='asset_ids must contain positive integers')
        if asset_id not in seen:
            seen.add(asset_id)
            ordered.append(asset_id)
    if not ordered:
        raise HTTPException(status_code=400, detail='An album draft requires at least one asset')
    if len(ordered) > MAX_ALBUM_ASSETS:
        raise HTTPException(status_code=400, detail=f'An album draft supports at most {MAX_ALBUM_ASSETS} assets')
    return ordered


def _load_assets(db_s: Session, asset_ids: list[int]) -> dict[int, Asset]:
    rows = db_s.query(Asset).filter(Asset.id.in_(asset_ids)).all()
    by_id = {int(asset.id): asset for asset in rows}
    missing = [asset_id for asset_id in asset_ids if asset_id not in by_id]
    if missing:
        raise HTTPException(status_code=400, detail=f'Unknown asset ids: {missing[:8]}')
    unavailable = [
        asset_id for asset_id in asset_ids
        if str(getattr(by_id[asset_id], 'status', None) or 'active').lower() != 'active'
    ]
    if unavailable:
        raise HTTPException(status_code=400, detail=f'Album assets must be active: {unavailable[:8]}')
    return by_id


def _ordered_asset_ids(asset_ids: list[int], assets: dict[int, Asset], sort_mode: str) -> list[int]:
    mode = str(sort_mode or 'chronological').strip().lower()
    if mode not in ALBUM_SORT_MODES:
        raise HTTPException(status_code=400, detail='Invalid album sort mode')
    if mode == 'as_provided':
        return asset_ids
    if mode == 'newest':
        return sorted(
            asset_ids,
            key=lambda asset_id: (
                getattr(assets[asset_id], 'taken_at', None)
                or getattr(assets[asset_id], 'created_at', None)
                or datetime.min,
                asset_id,
            ),
            reverse=True,
        )
    return sorted(
        asset_ids,
        key=lambda asset_id: (
            getattr(assets[asset_id], 'taken_at', None) is None
            and getattr(assets[asset_id], 'created_at', None) is None,
            getattr(assets[asset_id], 'taken_at', None)
            or getattr(assets[asset_id], 'created_at', None)
            or datetime.max,
            asset_id,
        ),
    )


def _serialize_album(album: Album) -> dict:
    ordered_items = sorted(album.items, key=lambda item: (int(item.position), int(item.id)))
    items = [
        {
            'id': int(item.asset.id),
            'path': item.asset.path,
            'mime': item.asset.mime,
            'taken_at': str(item.asset.taken_at) if item.asset.taken_at else None,
            'position': int(item.position),
        }
        for item in ordered_items
        if item.asset is not None
    ]
    item_ids = {int(item['id']) for item in items}
    cover_asset_id = int(album.cover_asset_id) if album.cover_asset_id in item_ids else None
    if cover_asset_id is None and items:
        cover_asset_id = int(items[0]['id'])
    return {
        'id': int(album.id),
        'title': album.title,
        'title_zh': album.title_zh,
        'description': album.description,
        'theme': album.theme,
        'status': album.status,
        'cover_asset_id': cover_asset_id,
        'source_kind': album.source_kind,
        'source_ref': album.source_ref,
        'asset_count': len(items),
        'items': items,
        'created_at': str(album.created_at) if album.created_at else None,
        'updated_at': str(album.updated_at) if album.updated_at else None,
    }


def _replace_album_assets(db_s: Session, album: Album, asset_ids: list[int]) -> None:
    db_s.query(AlbumAsset).filter(AlbumAsset.album_id == album.id).delete(synchronize_session=False)
    db_s.flush()
    for position, asset_id in enumerate(asset_ids):
        db_s.add(AlbumAsset(album_id=int(album.id), asset_id=asset_id, position=position))


@router.get('/albums/drafts', response_model=schemas.AlbumDraftListResponse)
def list_album_drafts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db_s: Session = Depends(get_db),
):
    query = db_s.query(Album).filter(Album.status == 'draft')
    total = query.count()
    rows = query.order_by(Album.updated_at.desc(), Album.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        'api_version': schemas.API_VERSION,
        'page': page,
        'page_size': page_size,
        'total': total,
        'albums': [_serialize_album(album) for album in rows],
    }


@router.get('/albums/drafts/{album_id}', response_model=schemas.AlbumDraftResponse)
def get_album_draft(album_id: int, db_s: Session = Depends(get_db)):
    album = db_s.get(Album, album_id)
    if album is None or album.status != 'draft':
        raise HTTPException(status_code=404, detail='Album draft not found')
    return {'api_version': schemas.API_VERSION, 'album': _serialize_album(album)}


@router.post('/albums/drafts', response_model=schemas.AlbumDraftResponse, status_code=201)
def create_album_draft(payload: schemas.AlbumDraftCreate, db_s: Session = Depends(get_db)):
    title = _clean_text(payload.title, 'title', required=True)
    title_zh = _clean_text(payload.title_zh, 'title_zh')
    description = _clean_text(payload.description, 'description', limit=1000)
    source_kind = _clean_text(payload.source_kind, 'source_kind', limit=32)
    source_ref = _clean_text(payload.source_ref, 'source_ref', limit=160)
    theme = _normalize_theme(payload.theme)
    asset_ids = _normalize_asset_ids(payload.asset_ids)
    assets = _load_assets(db_s, asset_ids)
    ordered_ids = _ordered_asset_ids(asset_ids, assets, payload.sort_mode)
    cover_asset_id = int(payload.cover_asset_id) if payload.cover_asset_id is not None else ordered_ids[0]
    if cover_asset_id not in ordered_ids:
        raise HTTPException(status_code=400, detail='cover_asset_id must belong to the album')

    album = Album(
        title=title,
        title_zh=title_zh,
        description=description,
        theme=theme,
        status='draft',
        cover_asset_id=cover_asset_id,
        source_kind=source_kind,
        source_ref=source_ref,
    )
    db_s.add(album)
    db_s.flush()
    _replace_album_assets(db_s, album, ordered_ids)
    db_s.commit()
    db_s.refresh(album)
    return {'api_version': schemas.API_VERSION, 'album': _serialize_album(album)}


@router.patch('/albums/drafts/{album_id}', response_model=schemas.AlbumDraftResponse)
def update_album_draft(
    album_id: int,
    payload: schemas.AlbumDraftUpdate,
    db_s: Session = Depends(get_db),
):
    album = db_s.get(Album, album_id)
    if album is None or album.status != 'draft':
        raise HTTPException(status_code=404, detail='Album draft not found')

    fields_set = getattr(payload, 'model_fields_set', getattr(payload, '__fields_set__', set()))
    if 'title' in fields_set:
        album.title = _clean_text(payload.title, 'title', required=True)  # type: ignore[assignment]
    if 'title_zh' in fields_set:
        album.title_zh = _clean_text(payload.title_zh, 'title_zh')
    if 'description' in fields_set:
        album.description = _clean_text(payload.description, 'description', limit=1000)
    if 'theme' in fields_set:
        album.theme = _normalize_theme(payload.theme)

    if payload.asset_ids is not None:
        asset_ids = _normalize_asset_ids(payload.asset_ids)
        _load_assets(db_s, asset_ids)
        _replace_album_assets(db_s, album, asset_ids)
    else:
        asset_ids = [int(item.asset_id) for item in sorted(album.items, key=lambda item: item.position)]

    if 'cover_asset_id' in fields_set:
        if payload.cover_asset_id is None:
            album.cover_asset_id = asset_ids[0]
        else:
            cover_asset_id = int(payload.cover_asset_id)
            if cover_asset_id not in asset_ids:
                raise HTTPException(status_code=400, detail='cover_asset_id must belong to the album')
            album.cover_asset_id = cover_asset_id
    elif album.cover_asset_id not in asset_ids:
        album.cover_asset_id = asset_ids[0]

    album.updated_at = datetime.utcnow()
    db_s.commit()
    db_s.refresh(album)
    return {'api_version': schemas.API_VERSION, 'album': _serialize_album(album)}
