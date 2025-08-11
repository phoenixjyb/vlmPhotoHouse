from fastapi import FastAPI, Depends, Body, Query, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import create_engine, MetaData, func, inspect
from sqlalchemy.orm import sessionmaker, Session
import os, threading, time
import logging, uuid
import math

from . import db
from .config import get_settings
from . import ingest as ingest_mod
from .tasks import TaskExecutor, INDEX_SINGLETON, EMBED_SERVICE, EMBED_DIM  # vector search globals
from .vector_index import load_index_from_embeddings, load_faiss_index_from_embeddings, FaissVectorIndex
from .db import Asset
from pathlib import Path
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from . import schemas
from typing import Generator, List
from .services import assets as asset_service
from .paths import DERIVED_PATH

settings = get_settings()
DATABASE_URL = settings.database_url
engine = create_engine(DATABASE_URL, future=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

_DB_READY = False

def ensure_db():
    global _DB_READY
    if not _DB_READY:
        try:
            insp = inspect(engine)
            if not insp.has_table('assets'):
                db.Base.metadata.create_all(bind=engine)
            # Fallback: if tasks table exists but new progress columns missing (e.g., older test DB before migration), add them for SQLite.
            if insp.has_table('tasks'):
                cols = {c['name'] for c in insp.get_columns('tasks')}
                with engine.begin() as conn:
                    if 'progress_current' not in cols:
                        try:
                            conn.exec_driver_sql('ALTER TABLE tasks ADD COLUMN progress_current INTEGER')
                        except Exception:
                            pass
                    if 'progress_total' not in cols:
                        try:
                            conn.exec_driver_sql('ALTER TABLE tasks ADD COLUMN progress_total INTEGER')
                        except Exception:
                            pass
                    if 'cancel_requested' not in cols:
                        try:
                            conn.exec_driver_sql("ALTER TABLE tasks ADD COLUMN cancel_requested BOOLEAN DEFAULT 0 NOT NULL")
                        except Exception:
                            pass
                    if 'started_at' not in cols:
                        try:
                            conn.exec_driver_sql('ALTER TABLE tasks ADD COLUMN started_at DATETIME')
                        except Exception:
                            pass
                    if 'finished_at' not in cols:
                        try:
                            conn.exec_driver_sql('ALTER TABLE tasks ADD COLUMN finished_at DATETIME')
                        except Exception:
                            pass
            # Fallback for embeddings new columns
            if insp.has_table('embeddings'):
                ecols = {c['name'] for c in insp.get_columns('embeddings')}
                with engine.begin() as conn:
                    if 'device' not in ecols:
                        try:
                            conn.exec_driver_sql('ALTER TABLE embeddings ADD COLUMN device VARCHAR(16)')
                        except Exception:
                            pass
                    if 'model_version' not in ecols:
                        try:
                            conn.exec_driver_sql('ALTER TABLE embeddings ADD COLUMN model_version VARCHAR(64)')
                        except Exception:
                            pass
            _DB_READY = True
        except Exception:
            pass

def init_db():
    db.Base.metadata.create_all(bind=engine)

app = FastAPI()

def get_db() -> Generator[Session, None, None]:
    ensure_db()
    with SessionLocal() as session:
        yield session

executor = TaskExecutor(SessionLocal, settings)

def task_worker_loop():
    while True:
        worked = executor.run_once()
        time.sleep(settings.worker_poll_interval if not worked else 0.05)

@app.on_event("startup")
def on_startup():
    if settings.auto_migrate:
        alembic_cfg = AlembicConfig(os.path.join(os.path.dirname(__file__), '..', 'alembic.ini'))
        alembic_cfg.set_main_option('script_location', settings.alembic_script_location)
        # ensure URL aligns with runtime settings
        alembic_cfg.set_main_option('sqlalchemy.url', settings.database_url)
        alembic_command.upgrade(alembic_cfg, 'head')
    else:
        init_db()
    if settings.enable_inline_worker and settings.run_mode in ("api", "all"):
        t = threading.Thread(target=task_worker_loop, daemon=True)
        t.start()
    # Optionally load existing embeddings into index
    if settings.vector_index_autoload and INDEX_SINGLETON is not None and not settings.vector_index_rebuild_on_demand_only:
        try:
            if isinstance(INDEX_SINGLETON, FaissVectorIndex):
                loaded = load_faiss_index_from_embeddings(SessionLocal, INDEX_SINGLETON, limit=settings.max_index_load)
                # save after load to persist meta
                try:
                    INDEX_SINGLETON.save(settings.vector_index_path)
                except Exception:
                    pass
            else:
                loaded = load_index_from_embeddings(SessionLocal, INDEX_SINGLETON, limit=settings.max_index_load)
            logging.getLogger('app').info(f"Vector index autoloaded embeddings: {loaded}")
        except Exception:
            logging.getLogger('app').warning('Vector index autoload failed', exc_info=True)
    # Schedule re-embed tasks if model or dim changed (compare sample embedding rows)
    try:
        from .db import Embedding, Task, Asset
        with SessionLocal() as session:
            # pick a small sample to compare
            sample = session.query(Embedding).filter(Embedding.modality=='image').limit(5).all()
            mismatch = False
            for emb in sample:
                if emb.model != settings.embed_model_image or emb.dim != EMBED_DIM or (settings.embed_model_version and emb.model_version != settings.embed_model_version):
                    mismatch = True
                    break
            if mismatch:
                # enqueue embed tasks for assets lacking up-to-date embeddings up to limit
                existing_asset_ids = session.query(Embedding.asset_id).filter(Embedding.modality=='image').subquery()
                stale = session.query(Embedding.asset_id).filter(Embedding.model!=settings.embed_model_image).all()
                stale_ids = {aid for (aid,) in stale}
                assets = session.query(Asset.id).limit(settings.embed_reembed_startup_limit).all()
                scheduled = 0
                for (aid,) in assets:
                    if aid in stale_ids:
                        session.add(Task(type='embed', priority=120, payload_json={'asset_id': aid}))
                        scheduled +=1
                if scheduled:
                    session.commit()
                    logging.getLogger('app').info(f"Scheduled {scheduled} re-embed tasks due to model change")
    except Exception:
        logging.getLogger('app').warning('Re-embed scheduling failed', exc_info=True)

@app.middleware('http')
async def request_logging_middleware(request: Request, call_next):
    req_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
    start = time.time()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception as e:
        logging.getLogger('app').error('Unhandled exception', extra={'request_id': req_id, 'path': request.url.path, 'method': request.method}, exc_info=True)
        raise
    finally:
        duration_ms = int((time.time()-start)*1000)
        extra = {
            'request_id': req_id,
            'path': request.url.path,
            'method': request.method,
            'status': status,
            'duration_ms': duration_ms,
        }
        lvl = logging.INFO
        if duration_ms >= settings.slow_request_ms:
            lvl = logging.WARNING
        logging.getLogger('access').log(lvl, f"{request.method} {request.url.path} {status} {duration_ms}ms", extra=extra)
    response.headers['X-Request-ID'] = req_id
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    req_id = request.headers.get('X-Request-ID') or 'unknown'
    logging.getLogger('app').error('Exception handled', extra={'request_id': req_id, 'path': request.url.path, 'method': request.method}, exc_info=True)
    return JSONResponse(status_code=500, content={'error': {'type': exc.__class__.__name__, 'message': str(exc), 'request_id': req_id}})

@app.get('/health', response_model=schemas.HealthResponse)
def health(request: Request, db_s: Session = Depends(get_db)):
    # basic DB check: can we run a trivial query
    db_ok = True
    try:
        db_s.execute(func.count(Asset.id))
    except Exception:
        db_ok = False
    # task stats
    from .db import Task
    pending = db_s.query(Task).filter(Task.state=='pending').count()
    running = db_s.query(Task).filter(Task.state=='running').count()
    failed = db_s.query(Task).filter(Task.state=='failed').count()
    index_initialized = INDEX_SINGLETON is not None
    index_size = len(INDEX_SINGLETON) if INDEX_SINGLETON else 0
    index_dim = EMBED_DIM if INDEX_SINGLETON else None
    return {
        'api_version': schemas.API_VERSION,
        'ok': db_ok,
        'db_ok': db_ok,
        'pending_tasks': pending,
        'running_tasks': running,
        'failed_tasks': failed,
        'index': {'initialized': index_initialized, 'size': index_size, 'dim': index_dim},
        'profile': settings.deploy_profile,
        'worker_enabled': settings.enable_inline_worker and settings.run_mode in ("api","all"),
    }

@app.get('/metrics', response_model=schemas.MetricsResponse)
def metrics(db_s: Session = Depends(get_db)):
    from .db import Task, Embedding, Caption, FaceDetection, Person
    assets_total = db_s.query(Asset).count()
    assets_deleted = db_s.query(Asset).filter(Asset.status=='deleted').count()
    assets_active = assets_total - assets_deleted
    embeddings = db_s.query(Embedding).count()
    captions = db_s.query(Caption).count()
    faces = db_s.query(FaceDetection).count()
    persons = db_s.query(Person).count()
    tasks_total = db_s.query(Task).count()
    by_state_rows = db_s.query(Task.state, func.count(Task.id)).group_by(Task.state).all()
    by_state = {state: cnt for state, cnt in by_state_rows}
    index_size = len(INDEX_SINGLETON) if INDEX_SINGLETON else 0
    index_dim = EMBED_DIM if INDEX_SINGLETON else None
    last_recluster = None
    # attempt to find last completed recluster summary
    last_recluster_task = db_s.query(Task).filter(Task.type=='person_recluster', Task.state=='done').order_by(Task.id.desc()).first()
    if last_recluster_task and last_recluster_task.payload_json and 'summary' in last_recluster_task.payload_json:
        last_recluster = last_recluster_task.payload_json.get('summary')
    # average task duration (completed tasks with both timestamps)
    durations = []
    done_tasks = db_s.query(Task.started_at, Task.finished_at).filter(Task.state=='done', Task.started_at!=None, Task.finished_at!=None).limit(500).all()
    for st, ft in done_tasks:
        try:
            durations.append((ft - st).total_seconds())
        except Exception:
            pass
    avg_duration = sum(durations)/len(durations) if durations else None
    return {
        'api_version': schemas.API_VERSION,
        'assets': {'total': assets_total, 'active': assets_active, 'deleted': assets_deleted},
        'embeddings': embeddings,
        'captions': captions,
        'faces': faces,
        'persons': persons,
        'tasks': {'total': tasks_total, 'by_state': by_state},
        'vector_index': {'size': index_size, 'dim': index_dim},
        'last_recluster': last_recluster,
        'task_duration_seconds_avg': avg_duration
    }

@app.post('/ingest/scan')
def trigger_ingest(roots: list[str] = Body(..., embed=True), db_s: Session = Depends(get_db)):
    result = ingest_mod.ingest_paths(db_s, roots)
    return result

@app.get('/search', response_model=schemas.SearchResponse)
def search(q: str = Query('', description='Query text (stub substring match on path)'), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200), db_s: Session = Depends(get_db)):
    base = db_s.query(Asset)
    if q:
        base = base.filter(Asset.path.like(f"%{q}%"))
    total = base.count()
    items = base.order_by(Asset.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {'api_version': schemas.API_VERSION, 'page': page, 'page_size': page_size, 'total': total, 'items': [{'id': a.id, 'path': a.path} for a in items]}

@app.get('/duplicates', response_model=schemas.DuplicatesResponse)
def list_duplicates(min_group_size: int = Query(2, ge=2), mode: str = Query('all', description='sha256|phash|all'), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db_s: Session = Depends(get_db)):
    results: dict = {'api_version': schemas.API_VERSION}
    offset = (page-1)*page_size
    slice_limit = page_size
    if mode in ('all','sha256'):
        sha_groups_q = (
            db_s.query(Asset.hash_sha256, func.count(Asset.id).label('cnt'))
            .group_by(Asset.hash_sha256)
            .having(func.count(Asset.id) >= min_group_size)
            .order_by(func.count(Asset.id).desc())
        )
        total_sha = sha_groups_q.count()
        sha_groups = sha_groups_q.offset(offset).limit(slice_limit).all()
        sha_list = []
        for h, cnt in sha_groups:
            assets = db_s.query(Asset.id, Asset.path).filter(Asset.hash_sha256==h).all()
            sha_list.append({'hash': h, 'count': cnt, 'assets': [{'id': a.id, 'path': a.path} for a in assets]})
        results['sha256'] = {'page': page, 'page_size': page_size, 'total_groups': total_sha, 'groups': sha_list}
    if mode in ('all','phash'):
        phash_groups_q = (
            db_s.query(Asset.perceptual_hash, func.count(Asset.id).label('cnt'))
            .filter(Asset.perceptual_hash != None)
            .group_by(Asset.perceptual_hash)
            .having(func.count(Asset.id) >= min_group_size)
            .order_by(func.count(Asset.id).desc())
        )
        total_ph = phash_groups_q.count()
        phash_groups = phash_groups_q.offset(offset).limit(slice_limit).all()
        phash_list = []
        for ph, cnt in phash_groups:
            assets = db_s.query(Asset.id, Asset.path).filter(Asset.perceptual_hash==ph).all()
            phash_list.append({'phash': ph, 'count': cnt, 'assets': [{'id': a.id, 'path': a.path} for a in assets]})
        results['phash'] = {'page': page, 'page_size': page_size, 'total_groups': total_ph, 'groups': phash_list}
    return results

@app.get('/duplicates/near', response_model=schemas.NearDuplicatesResponse)
def near_duplicates(max_distance: int = Query(5, ge=1, le=32), sample_limit: int = Query(1000, le=5000), cluster_limit: int = Query(50, le=200), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200), db_s: Session = Depends(get_db)):
    assets = db_s.query(Asset.id, Asset.path, Asset.perceptual_hash).filter(Asset.perceptual_hash != None).limit(sample_limit).all()
    processed = []
    def hex_to_int(h: str) -> int:
        try: return int(h, 16)
        except Exception: return 0
    for a in assets:
        if a.perceptual_hash:
            processed.append((a.id, a.path, a.perceptual_hash, hex_to_int(a.perceptual_hash)))
    visited = set()
    clusters = []
    def hamming_int(x: int, y: int) -> int: return (x ^ y).bit_count()
    for i,(aid, apath, ah, ai) in enumerate(processed):
        if aid in visited: continue
        group = [{'id': aid, 'path': apath, 'phash': ah, 'distance': 0}]
        visited.add(aid)
        for j in range(i+1, len(processed)):
            bid, bpath, bh, bi = processed[j]
            if bid in visited: continue
            dist = hamming_int(ai, bi)
            if dist <= max_distance:
                group.append({'id': bid, 'path': bpath, 'phash': bh, 'distance': dist})
                visited.add(bid)
        if len(group) > 1:
            group.sort(key=lambda x: (x['distance'], x['id']))
            clusters.append({'representative': group[0]['id'], 'size': len(group), 'members': group})
        if len(clusters) >= cluster_limit: break
    clusters.sort(key=lambda c: c['size'], reverse=True)
    total_clusters = len(clusters)
    start = (page-1)*page_size
    end = start + page_size
    clusters_page = clusters[start:end]
    return {'api_version': schemas.API_VERSION, 'page': page, 'page_size': page_size, 'total_clusters': total_clusters, 'clusters': clusters_page, 'max_distance': max_distance, 'scanned': len(processed), 'truncated': len(assets) == sample_limit}

@app.post('/duplicates/delete')
def delete_duplicates(asset_ids: List[int] = Body(..., embed=True), remove_files: bool = Body(True), db_s: Session = Depends(get_db)):
    if not asset_ids:
        raise HTTPException(status_code=400, detail='asset_ids empty')
    assets = db_s.query(Asset).filter(Asset.id.in_(asset_ids)).all()
    deleted = 0
    for a in assets:
        if getattr(a, 'status', None) == 'deleted':
            continue
        setattr(a, 'status', 'deleted')
        if remove_files:
            asset_service.remove_asset_files(db_s, a)
        deleted +=1
    db_s.commit()
    return {'deleted': deleted, 'requested': len(asset_ids)}

@app.post('/duplicates/keep')
def keep_duplicates(asset_ids: List[int] = Body(..., embed=True), db_s: Session = Depends(get_db)):
    if not asset_ids:
        raise HTTPException(status_code=400, detail='asset_ids empty')
    assets = db_s.query(Asset).filter(Asset.id.in_(asset_ids)).all()
    updated = 0
    for a in assets:
        if getattr(a, 'status', None) != 'active':
            setattr(a, 'status', 'active')
            updated +=1
    db_s.commit()
    return {'kept': updated, 'requested': len(asset_ids)}

@app.post('/assets/{asset_id}/delete')
def delete_single_asset(asset_id: int, remove_files: bool = Body(True), db_s: Session = Depends(get_db)):
    asset = db_s.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail='asset not found')
    if getattr(asset, 'status', None) != 'deleted':
        setattr(asset, 'status', 'deleted')
        if remove_files:
            asset_service.remove_asset_files(db_s, asset)
        db_s.commit()
    return {'asset_id': asset_id, 'status': asset.status}

@app.post('/search/vector', response_model=schemas.VectorSearchResponse)
def vector_search(text: str | None = Body(None), asset_id: int | None = Body(None), k: int = Body(10), db_s: Session = Depends(get_db)):
    if INDEX_SINGLETON is None or EMBED_SERVICE is None:
        raise HTTPException(status_code=503, detail='Vector index not initialized')
    if not text and not asset_id:
        raise HTTPException(status_code=400, detail='Provide text or asset_id')
    if text:
        query_vec = EMBED_SERVICE.embed_text_stub(text)
    else:
        asset = db_s.get(Asset, asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail='asset not found')
        apath = asset.path if isinstance(asset.path, str) else str(asset.path)
        query_vec = EMBED_SERVICE.embed_image_stub(apath)
    matches = INDEX_SINGLETON.search(query_vec, k=k)
    assets_map = {a.id: a for a in db_s.query(Asset).filter(Asset.id.in_([mid for mid,_ in matches])).all()}
    result_items = []
    for mid, score in matches:
        aobj = assets_map.get(mid)
        result_items.append({'asset_id': mid, 'score': float(score), 'path': aobj.path if aobj else None})
    return {'api_version': schemas.API_VERSION, 'query': {'text': text, 'asset_id': asset_id}, 'k': k, 'results': result_items}

@app.get('/embedding/backend', response_model=schemas.EmbeddingBackendStatus)
def embedding_backend_status(db_s: Session = Depends(get_db)):
    from .db import Asset, Embedding, Task
    total_assets = db_s.query(Asset).count()
    # count assets needing re-embed (model mismatch)
    stale = db_s.query(Embedding).filter(Embedding.modality=='image', Embedding.model!=settings.embed_model_image).count()
    return {
        'api_version': schemas.API_VERSION,
        'image_model': settings.embed_model_image,
        'text_model': settings.embed_model_text,
        'device': settings.embed_device,
        'dim': EMBED_DIM,
        'model_version': settings.embed_model_version or None,
        'reembed_scheduled': stale,
        'total_assets': total_assets,
    }

@app.post('/vector-index/rebuild')
def rebuild_vector_index(limit: int = Body(None), db_s: Session = Depends(get_db)):
    if INDEX_SINGLETON is None:
        raise HTTPException(status_code=503, detail='Index not initialized')
    # clear and reload
    INDEX_SINGLETON.clear()
    if isinstance(INDEX_SINGLETON, FaissVectorIndex):
        loaded = load_faiss_index_from_embeddings(SessionLocal, INDEX_SINGLETON, limit=limit or settings.max_index_load)
        try:
            INDEX_SINGLETON.save(settings.vector_index_path)
        except Exception:
            pass
    else:
        loaded = load_index_from_embeddings(SessionLocal, INDEX_SINGLETON, limit=limit or settings.max_index_load)
    return {'api_version': schemas.API_VERSION, 'reloaded': loaded, 'dim': EMBED_DIM, 'size': len(INDEX_SINGLETON), 'backend': settings.vector_index_backend}
# Routers
from .routers import people as people_router
app.include_router(people_router.router, prefix='')

# --- Plugin comment placeholder ---
# Add any plugin-specific initialization or route inclusion here
