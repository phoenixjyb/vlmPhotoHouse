from fastapi import FastAPI, Depends, Body, Query, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi import UploadFile, File, Body
from sqlalchemy import create_engine, MetaData, func, inspect
from sqlalchemy.orm import sessionmaker, Session
import os, threading, time
import logging, uuid
import math
import mimetypes

from . import db
from .config import get_settings
from . import ingest as ingest_mod
from . import tasks as tasks_mod  # use module to keep live globals
from .vector_index import load_index_from_embeddings, load_faiss_index_from_embeddings, FaissVectorIndex
from .db import Asset, Task
from pathlib import Path
try:
    from alembic import command as alembic_command  # type: ignore
    from alembic.config import Config as AlembicConfig  # type: ignore
    from alembic.script import ScriptDirectory  # type: ignore
    from alembic.runtime.migration import MigrationContext  # type: ignore
except Exception:
    alembic_command = AlembicConfig = ScriptDirectory = MigrationContext = None  # Optional in tests/dev
from . import schemas
from typing import Generator, List
from .services import assets as asset_service
from .paths import DERIVED_PATH
from .image_utils import safe_exif_transpose
try:
    from . import metrics as metrics_mod  # optional module; guard usage below
except Exception:
    metrics_mod = None
from . import dependencies as deps
from .dependencies import get_db, ensure_db

settings = get_settings()


def _visible_assets_filter():
    # Treat NULL as legacy-active for backward compatibility.
    return (Asset.status == None) | (Asset.status == 'active')

def init_db():
    # Ensure dependencies are bound and schema exists
    ensure_db()
    try:
        db.Base.metadata.create_all(bind=deps.engine)
    except Exception:
        pass

app = FastAPI()

# Initialize executor after DB is ensured (SessionLocal is defined in deps)
ensure_db()
# Backwards-compat: expose SessionLocal in this module for tests that import it from app.main
SessionLocal = deps.SessionLocal  # type: ignore
executor = tasks_mod.TaskExecutor(deps.SessionLocal, settings)

def task_worker_loop():
    logger = logging.getLogger('app.worker')
    logger.info("Task worker loop starting...")
    while True:
        try:
            worked = executor.run_once()
            if worked:
                logger.debug("Task processed successfully")
            time.sleep(settings.worker_poll_interval if not worked else 0.05)
        except Exception as e:
            logger.error(f"Task worker error: {e}", exc_info=True)
            time.sleep(settings.worker_poll_interval)  # back off on error

def _run_heavy_startup_tasks():
    """Run expensive startup work after API boot.

    This keeps process startup responsive by allowing uvicorn to bind quickly
    while indexes and re-embed scheduling continue in background.
    """
    # Optionally load existing embeddings into index
    if settings.vector_index_autoload and tasks_mod.INDEX_SINGLETON is not None and not settings.vector_index_rebuild_on_demand_only:
        try:
            if isinstance(tasks_mod.INDEX_SINGLETON, FaissVectorIndex):
                loaded = load_faiss_index_from_embeddings(deps.SessionLocal, tasks_mod.INDEX_SINGLETON, limit=settings.max_index_load)
                # save after load to persist meta
                try:
                    tasks_mod.INDEX_SINGLETON.save(settings.vector_index_path)
                except Exception:
                    pass
            else:
                loaded = load_index_from_embeddings(deps.SessionLocal, tasks_mod.INDEX_SINGLETON, limit=settings.max_index_load)
            logging.getLogger('app').info(f"Vector index autoloaded embeddings: {loaded}")
        except Exception:
            logging.getLogger('app').warning('Vector index autoload failed', exc_info=True)
    # Video index autoload (simple): scan derived/video_embeddings/*.npy
    try:
        from glob import glob
        from pathlib import Path as _Path
        if getattr(tasks_mod, 'VIDEO_INDEX_SINGLETON', None) is not None:
            vecs = []
            ids = []
            for fp in glob(str(_Path(settings.derived_path) / 'video_embeddings' / '*.npy'))[: settings.max_index_load]:
                try:
                    import numpy as _np
                    aid = int(_Path(fp).stem)
                    vec = _np.load(fp).astype('float32')
                    ids.append(aid); vecs.append(vec)
                except Exception:
                    continue
            if ids:
                tasks_mod.VIDEO_INDEX_SINGLETON.add(ids, __import__('numpy').stack(vecs))
    except Exception:
        logging.getLogger('app').warning('Video index autoload failed', exc_info=True)
    # Video segment index autoload: scan derived/video_embeddings/seg_*.npy
    try:
        from glob import glob as _glob
        from pathlib import Path as _P
        if getattr(tasks_mod, 'VIDEO_SEG_INDEX_SINGLETON', None) is not None:
            sids = []
            svecs = []
            for fp in _glob(str(_P(settings.derived_path) / 'video_embeddings' / 'seg_*.npy'))[: settings.max_index_load]:
                try:
                    import numpy as _np2
                    sid = int(_P(fp).stem.split('_',1)[1])
                    vec = _np2.load(fp).astype('float32')
                    sids.append(sid); svecs.append(vec)
                except Exception:
                    continue
            if sids:
                tasks_mod.VIDEO_SEG_INDEX_SINGLETON.add(sids, __import__('numpy').stack(svecs))
    except Exception:
        logging.getLogger('app').warning('Video segment index autoload failed', exc_info=True)
    # Schedule re-embed tasks if model or dim changed (compare sample embedding rows)
    try:
        from .db import Embedding, Task, Asset
        with deps.SessionLocal() as session:
            # pick a small sample to compare
            sample = session.query(Embedding).filter(Embedding.modality=='image').limit(5).all()
            mismatch = False
            for emb in sample:
                if emb.model != settings.embed_model_image or emb.dim != tasks_mod.EMBED_DIM or (settings.embed_model_version and emb.model_version != settings.embed_model_version):
                    mismatch = True
                    break
            if mismatch:
                # enqueue embed tasks for assets lacking up-to-date embeddings up to limit
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

# --- Test-only helpers ---
def reinit_executor_for_tests():
    """Reinitialize settings and executor to pick up env overrides in tests.

    Safe to call multiple times. Does not recreate the engine; assumes DATABASE_URL unchanged.
    """
    global settings, executor
    try:
        executor.stop_workers()
    except Exception:
        pass
    settings = get_settings()
    # Rebind dependencies to the current DATABASE_URL and ensure schema
    ensure_db()
    try:
        db.Base.metadata.create_all(bind=deps.engine)
    except Exception:
        pass
    executor = tasks_mod.TaskExecutor(deps.SessionLocal, settings)
    return executor

@app.on_event("startup")
def on_startup():
    # Simplified startup for testing
    print("Starting server with basic initialization...")
    init_db()  # Just create tables, skip Alembic for now
    print("Database initialized.")
    
    # Enable task workers for caption processing
    if settings.enable_inline_worker and settings.run_mode in ("api", "all"):
        print("Starting task workers...")
        # Backwards compatibility: if concurrency==1 use legacy single loop else multi-worker
        if settings.worker_concurrency <= 1:
            t = threading.Thread(target=task_worker_loop, daemon=True)
            t.start()
            print("Single task worker started.")
        else:
            executor.start_workers(settings.worker_concurrency)
            print(f"Multi-worker executor started with {settings.worker_concurrency} workers.")
    else:
        print("Task workers disabled.")
    defer_heavy = os.getenv('DEFER_HEAVY_STARTUP', 'true').lower() in ('1', 'true', 'yes')
    if defer_heavy:
        threading.Thread(target=_run_heavy_startup_tasks, daemon=True, name='startup-heavy-init').start()
        print("Deferred heavy startup tasks to background thread.")
    else:
        _run_heavy_startup_tasks()

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
    index_initialized = tasks_mod.INDEX_SINGLETON is not None
    index_size = len(tasks_mod.INDEX_SINGLETON) if tasks_mod.INDEX_SINGLETON else 0
    index_dim = tasks_mod.EMBED_DIM if tasks_mod.INDEX_SINGLETON else None
    # active face embedding provider (lazy; protected by try to avoid import failures on lightweight envs)
    face_embed_provider = None
    face_detect_provider = None
    face_device = settings.embed_device
    try:
        from .face_embedding_service import get_face_embedding_provider
        prov = get_face_embedding_provider()
        face_embed_provider = prov.__class__.__name__
        try:
            embed_dim = getattr(prov, 'dim', None)
        except Exception:
            embed_dim = None
    except Exception:
        face_embed_provider = 'unavailable'
        embed_dim = None
    # Detection provider info
    try:
        from .face_detection_service import get_face_detection_provider
        _det = get_face_detection_provider()
        face_detect_provider = _det.__class__.__name__
    except Exception:
        face_detect_provider = 'unavailable'
    try:
        from .face_detection_service import get_face_detection_provider
        dprov = get_face_detection_provider()
        face_detect_provider = dprov.__class__.__name__
    except Exception:
        face_detect_provider = 'unavailable'
    
    # Caption provider info
    caption_provider = None
    caption_device = settings.caption_device
    caption_model = settings.caption_model
    try:
        from .caption_service import get_caption_provider
        cprov = get_caption_provider()
        caption_provider = cprov.__class__.__name__
    except Exception:
        caption_provider = 'unavailable'
    
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
        'face': {
            'embed_provider': face_embed_provider,
            'embed_dim': embed_dim,
            'lvface_model_path': settings.lvface_model_path if face_embed_provider and 'lvface' in face_embed_provider.lower() else None,
            'lvface_external_dir': settings.lvface_external_dir if face_embed_provider and 'lvface' in face_embed_provider.lower() else None,
            'lvface_python_exe': settings.lvface_python_exe if face_embed_provider and 'lvface' in face_embed_provider.lower() else None,
            'lvface_model_name': settings.lvface_model_name if face_embed_provider and 'lvface' in face_embed_provider.lower() else None,
            'detect_provider': face_detect_provider,
            'device': face_device,
        },
        'caption': {
            'provider': caption_provider,
            'device': caption_device,
            'model': caption_model,
            'external_dir': settings.caption_external_dir if caption_provider and 'external' in caption_provider.lower() else None,
        },
    }

@app.get('/health/lvface')
def health_lvface():
    """Detailed LVFace configuration and status."""
    from .lvface_validation import get_config_summary
    return get_config_summary()

@app.get('/health/caption')
def health_caption():
    """Detailed caption provider configuration and status."""
    try:
        from .caption_service import get_caption_provider
        provider = get_caption_provider()
        provider_name = provider.__class__.__name__
        model_name = provider.get_model_name()
        
        status = {
            'provider': provider_name,
            'model': model_name,
            'device': settings.caption_device,
            'configured_provider': settings.caption_provider,
            'configured_model': settings.caption_model,
            'external_dir': settings.caption_external_dir,
            'mode': 'external' if settings.caption_external_dir and 'external' in model_name.lower() else 'builtin',
            'available_providers': ['stub', 'llava-next', 'qwen2.5-vl', 'blip2'],
        }
        
        # Test caption generation (if possible without long model loading)
        if provider_name == 'StubCaptionProvider':
            status['test_result'] = 'Stub provider active (filename-based heuristics)'
        elif 'external' in model_name.lower():
            status['test_result'] = f'External model provider active: {model_name}'
        else:
            status['test_result'] = f'Built-in model provider active: {model_name}'
            
        # Validate external directory if configured
        if settings.caption_external_dir:
            from pathlib import Path
            external_dir = Path(settings.caption_external_dir)
            status['external_validation'] = {
                'dir_exists': external_dir.exists(),
                'python_exists': (external_dir / ".venv" / "Scripts" / "python.exe").exists() or (external_dir / ".venv" / "bin" / "python").exists(),
                'inference_script_exists': (external_dir / "inference.py").exists(),
            }
            
        return status
        
    except Exception as e:
        return {
            'error': str(e),
            'provider': 'unavailable',
            'configured_provider': settings.caption_provider,
            'external_dir': settings.caption_external_dir,
            'available_providers': ['stub', 'llava-next', 'qwen2.5-vl', 'blip2'],
        }

@app.get('/metrics', response_model=schemas.MetricsResponse)
def metrics(db_s: Session = Depends(get_db)):
    from .db import Task, Embedding, Caption, FaceDetection, Person, AssetTag
    assets_total = db_s.query(Asset).count()
    assets_deleted = db_s.query(Asset).filter(Asset.status=='deleted').count()
    assets_active = assets_total - assets_deleted
    embeddings = db_s.query(Embedding).count()
    captions = db_s.query(Caption).count()
    faces = db_s.query(FaceDetection).count()
    persons = db_s.query(Person).count()
    tag_links = db_s.query(AssetTag).count()
    tag_assets = db_s.query(func.count(func.distinct(AssetTag.asset_id))).scalar() or 0
    tag_by_source_rows = db_s.query(AssetTag.source, func.count(AssetTag.id)).group_by(AssetTag.source).all()
    tag_by_source = {str(source or '(null)'): int(cnt) for source, cnt in tag_by_source_rows}
    tasks_total = db_s.query(Task).count()
    by_state_rows = db_s.query(Task.state, func.count(Task.id)).group_by(Task.state).all()
    by_state = {state: cnt for state, cnt in by_state_rows}
    index_size = len(tasks_mod.INDEX_SINGLETON) if tasks_mod.INDEX_SINGLETON else 0
    index_dim = tasks_mod.EMBED_DIM if tasks_mod.INDEX_SINGLETON else None
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
    # Update gauges (cheap) for exporter
    if metrics_mod is not None:
        try:
            pending = by_state.get('pending', 0)
            running = by_state.get('running', 0)
            dead = by_state.get('dead', 0)
            metrics_mod.update_queue_gauges(pending, running)
            metrics_mod.update_dead_tasks(dead)
            metrics_mod.update_vector_index_size(index_size)
            metrics_mod.update_persons_total(persons)
        except Exception:
            pass
    return {
        'api_version': schemas.API_VERSION,
        'assets': {'total': assets_total, 'active': assets_active, 'deleted': assets_deleted},
        'embeddings': embeddings,
        'captions': captions,
        'faces': faces,
        'persons': persons,
        'tags': {'total_links': int(tag_links), 'assets_with_tags': int(tag_assets), 'by_source': tag_by_source},
        'tasks': {'total': tasks_total, 'by_state': by_state},
    'vector_index': {'size': index_size, 'dim': index_dim},
        'last_recluster': last_recluster,
        'task_duration_seconds_avg': avg_duration
    }

@app.get('/system/usage')
def system_usage():
    """Lightweight system telemetry for UI (CPU/RAM/GPU)."""
    out: dict = {
        'api_version': schemas.API_VERSION,
        'cpu_percent': None,
        'memory': None,
        'gpus': [],
        'timestamp': int(time.time()),
    }

    try:
        import psutil  # type: ignore
        cpu = psutil.cpu_percent(interval=0.1)
        vm = psutil.virtual_memory()
        out['cpu_percent'] = float(cpu)
        out['memory'] = {
            'total': int(vm.total),
            'available': int(vm.available),
            'used': int(vm.used),
            'percent': float(vm.percent),
        }
    except Exception as e:
        out['cpu_mem_error'] = str(e)

    try:
        import subprocess
        cmd = [
            'nvidia-smi',
            '--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu',
            '--format=csv,noheader,nounits',
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=4, check=False)
        if proc.returncode == 0:
            gpus = []
            for raw in (proc.stdout or '').splitlines():
                line = raw.strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split(',', 5)]
                if len(parts) < 6:
                    continue
                idx, name, mem_total, mem_used, util, temp = parts
                try:
                    gpus.append({
                        'index': int(idx),
                        'name': name,
                        'memory_total_mb': int(float(mem_total)),
                        'memory_used_mb': int(float(mem_used)),
                        'utilization_gpu_percent': float(util),
                        'temperature_c': float(temp),
                    })
                except Exception:
                    continue
            out['gpus'] = gpus
        else:
            out['gpu_error'] = (proc.stderr or proc.stdout or f'nvidia-smi exit={proc.returncode}').strip()
    except FileNotFoundError:
        out['gpu_error'] = 'nvidia-smi not found'
    except Exception as e:
        out['gpu_error'] = str(e)

    return out

@app.post('/ingest/scan')
def trigger_ingest(roots: list[str] = Body(..., embed=True), db_s: Session = Depends(get_db)):
    result = ingest_mod.ingest_paths(db_s, roots)
    return result

@app.get('/search', response_model=schemas.SearchResponse)
def search(q: str = Query('', description='Query text (stub substring match on path)'), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200), db_s: Session = Depends(get_db)):
    base = db_s.query(Asset).filter(_visible_assets_filter())
    if q:
        base = base.filter(Asset.path.like(f"%{q}%"))
    total = base.count()
    items = base.order_by(Asset.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {'api_version': schemas.API_VERSION, 'page': page, 'page_size': page_size, 'total': total, 'items': [{'id': a.id, 'path': a.path} for a in items]}

@app.get('/assets/{asset_id}/media')
def get_asset_media(asset_id: int, download: bool = Query(False), db_s: Session = Depends(get_db)):
    """Serve original asset bytes for image/video preview in the web UI."""
    asset = db_s.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail='asset not found')
    apath = Path(asset.path)
    if not apath.exists() or not apath.is_file():
        raise HTTPException(status_code=404, detail='asset file not found on disk')

    media_type = asset.mime or mimetypes.guess_type(str(apath))[0] or 'application/octet-stream'
    if download:
        return FileResponse(str(apath), media_type=media_type, filename=apath.name)
    return FileResponse(str(apath), media_type=media_type)

@app.get('/assets/{asset_id}/thumbnail')
def get_asset_thumbnail(asset_id: int, size: int = Query(256, ge=64, le=1024), db_s: Session = Depends(get_db)):
    """Return a thumbnail for an asset, generating it on demand when missing."""
    asset = db_s.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail='asset not found')

    derived_root = Path(settings.derived_path)
    thumb_path = derived_root / 'thumbnails' / str(size) / f'{asset_id}.jpg'
    if thumb_path.exists():
        return FileResponse(str(thumb_path), media_type='image/jpeg')

    source_path: Path | None = None
    asset_path = Path(asset.path)
    mime = asset.mime or ''

    if mime.startswith('video'):
        frames_dir = derived_root / 'video_frames' / str(asset_id)
        if frames_dir.exists():
            for frame in sorted(frames_dir.glob('*.jpg')):
                source_path = frame
                break
    else:
        source_path = asset_path

    if source_path is None or (not source_path.exists()) or (not source_path.is_file()):
        raise HTTPException(status_code=404, detail='thumbnail source not found')

    try:
        from PIL import Image
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source_path) as im:
            upright = safe_exif_transpose(im)
            rgb = upright.convert('RGB')
            rgb.thumbnail((size, size))
            rgb.save(thumb_path, 'JPEG', quality=86)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'thumbnail generation failed: {e}')

    return FileResponse(str(thumb_path), media_type='image/jpeg')

# --- Captions management ---
@app.get('/assets/{asset_id}/captions')
def list_captions(asset_id: int, db_s: Session = Depends(get_db)):
    from .db import Caption
    a = db_s.get(Asset, asset_id)
    if not a:
        raise HTTPException(status_code=404, detail='Asset not found')
    caps = db_s.query(Caption).filter(Caption.asset_id==asset_id).order_by(Caption.created_at.asc()).all()
    return {'asset_id': asset_id, 'captions': [{'id': c.id, 'text': c.text, 'model': c.model, 'user_edited': c.user_edited, 'created_at': str(c.created_at) if c.created_at else None} for c in caps]}

@app.post('/assets/{asset_id}/captions/regenerate')
def regenerate_caption(asset_id: int, force: bool = Body(False, embed=True), db_s: Session = Depends(get_db)):
    # Enqueue a caption task; task handler enforces variant/word limits
    a = db_s.get(Asset, asset_id)
    if not a:
        raise HTTPException(status_code=404, detail='Asset not found')
    t = Task(type='caption', priority=110, payload_json={'asset_id': asset_id, 'force': force})
    db_s.add(t)
    db_s.commit()
    return {'enqueued': True, 'task_id': t.id}

@app.patch('/captions/{caption_id}')
def update_caption(caption_id: int, user_edited: bool | None = Body(None, embed=True), text: str | None = Body(None, embed=True), db_s: Session = Depends(get_db)):
    from .db import Caption
    cap = db_s.get(Caption, caption_id)
    if not cap:
        raise HTTPException(status_code=404, detail='Caption not found')
    changed = False
    if user_edited is not None:
        cap.user_edited = bool(user_edited)
        changed = True
    if text is not None:
        # enforce word limit similar to generation path
        import os as _os
        try:
            word_limit = int(_os.getenv('CAPTION_WORD_LIMIT', '40') or '40')
        except Exception:
            word_limit = 40
        new_text = text or ''
        try:
            words = new_text.split()
            if word_limit > 0 and len(words) > word_limit:
                new_text = ' '.join(words[:word_limit])
        except Exception:
            pass
        cap.text = new_text
        changed = True
    if changed:
        db_s.commit()
    return {'id': cap.id, 'asset_id': cap.asset_id, 'text': cap.text, 'model': cap.model, 'user_edited': cap.user_edited}

@app.delete('/captions/{caption_id}')
def delete_caption(caption_id: int, db_s: Session = Depends(get_db)):
    from .db import Caption
    cap = db_s.get(Caption, caption_id)
    if not cap:
        raise HTTPException(status_code=404, detail='Caption not found')
    db_s.delete(cap)
    db_s.commit()
    return {'deleted': True, 'id': caption_id}

@app.post('/video-index/rebuild')
def video_index_rebuild(db_s: Session = Depends(get_db)):
    # Clear and reload from derived/video_embeddings
    try:
        if tasks_mod.VIDEO_INDEX_SINGLETON is None:
            tasks_mod.VIDEO_INDEX_SINGLETON = tasks_mod.InMemoryVectorIndex(tasks_mod.EMBED_DIM)
        tasks_mod.VIDEO_INDEX_SINGLETON.clear()
        import numpy as np
        from glob import glob
        from pathlib import Path as _Path
        ids = []; vecs = []
        for fp in glob(str(_Path(settings.derived_path) / 'video_embeddings' / '*.npy')):
            try:
                aid = int(_Path(fp).stem)
                vec = np.load(fp).astype('float32')
                ids.append(aid); vecs.append(vec)
            except Exception:
                continue
        if ids:
            tasks_mod.VIDEO_INDEX_SINGLETON.add(ids, np.stack(vecs))
        return {'loaded': len(ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Caption search (simple LIKE) ---
@app.post('/search/captions')
def search_captions(text: str = Body('', embed=True), k: int = Body(20, embed=True), media: str = Body('all', embed=True), db_s: Session = Depends(get_db)):
    from .db import Caption
    from sqlalchemy import func as _f
    if not text:
        raise HTTPException(status_code=400, detail='text required')
    q = db_s.query(Asset).join(Caption, Caption.asset_id==Asset.id).filter(_visible_assets_filter(), _f.lower(Caption.text).like(f"%{text.lower()}%"))
    if media == 'image':
        q = q.filter((Asset.mime == None) | (~Asset.mime.startswith('video')))
    elif media == 'video':
        q = q.filter(Asset.mime.startswith('video'))
    items = q.order_by(Asset.id.desc()).limit(k).all()
    return {'query': text, 'results': [{'asset_id': a.id, 'path': a.path, 'mime': a.mime} for a in items]}

# --- Tag management ---
@app.get('/tags')
def list_tags(
    q: str = Query('', description='Substring filter for tag name'),
    source: str = Query('all', description='Filter by source: all|cap|img|cap+img|manual|rule|(null)'),
    page: int = Query(1, ge=1),
    page_size: int = Query(120, ge=1, le=500),
    db_s: Session = Depends(get_db),
):
    from sqlalchemy import case
    from .db import Tag, AssetTag

    name_filter = str(q or '').strip().lower()
    source_filter = str(source or 'all').strip().lower()
    allowed_sources = {'all', 'cap', 'img', 'cap+img', 'manual', 'rule', '(null)'}
    if source_filter not in allowed_sources:
        raise HTTPException(status_code=400, detail='Invalid source filter')

    count_q = (
        db_s.query(Tag.id)
        .join(AssetTag, AssetTag.tag_id == Tag.id)
        .join(Asset, Asset.id == AssetTag.asset_id)
        .filter(_visible_assets_filter())
    )
    if name_filter:
        count_q = count_q.filter(func.lower(Tag.name).like(f"%{name_filter}%"))
    if source_filter == '(null)':
        count_q = count_q.filter(AssetTag.source.is_(None))
    elif source_filter != 'all':
        count_q = count_q.filter(AssetTag.source == source_filter)
    total = int(count_q.distinct().count())

    src = func.coalesce(AssetTag.source, '(null)')
    rows_q = (
        db_s.query(
            Tag.id,
            Tag.name,
            Tag.type,
            func.count(AssetTag.id).label('links'),
            func.count(func.distinct(AssetTag.asset_id)).label('assets'),
            func.sum(case((src == 'cap', 1), else_=0)).label('cap_links'),
            func.sum(case((src == 'img', 1), else_=0)).label('img_links'),
            func.sum(case((src == 'cap+img', 1), else_=0)).label('capimg_links'),
            func.sum(case((src == 'manual', 1), else_=0)).label('manual_links'),
            func.sum(case((src == 'rule', 1), else_=0)).label('rule_links'),
            func.sum(case((src == '(null)', 1), else_=0)).label('null_links'),
        )
        .join(AssetTag, AssetTag.tag_id == Tag.id)
        .join(Asset, Asset.id == AssetTag.asset_id)
        .filter(_visible_assets_filter())
    )
    if name_filter:
        rows_q = rows_q.filter(func.lower(Tag.name).like(f"%{name_filter}%"))
    if source_filter == '(null)':
        rows_q = rows_q.filter(AssetTag.source.is_(None))
    elif source_filter != 'all':
        rows_q = rows_q.filter(AssetTag.source == source_filter)
    rows = (
        rows_q.group_by(Tag.id, Tag.name, Tag.type)
        .order_by(func.count(AssetTag.id).desc(), Tag.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        'q': q,
        'source': source_filter,
        'page': page,
        'page_size': page_size,
        'total': total,
        'rows': [
            {
                'id': int(r.id),
                'name': r.name,
                'type': r.type,
                'assets': int(r.assets or 0),
                'links': int(r.links or 0),
                'sources': {
                    'cap': int(r.cap_links or 0),
                    'img': int(r.img_links or 0),
                    'cap+img': int(r.capimg_links or 0),
                    'manual': int(r.manual_links or 0),
                    'rule': int(r.rule_links or 0),
                    '(null)': int(r.null_links or 0),
                },
            }
            for r in rows
        ],
    }


@app.get('/tags/{tag_id}/assets')
def list_tag_assets(
    tag_id: int,
    media: str = Query('all', description='Filter media: all|image|video'),
    source: str = Query('all', description='Filter by source: all|cap|img|cap+img|manual|rule|(null)'),
    page: int = Query(1, ge=1),
    page_size: int = Query(120, ge=1, le=500),
    db_s: Session = Depends(get_db),
):
    from .db import Tag, AssetTag

    tag = db_s.get(Tag, int(tag_id))
    if not tag:
        raise HTTPException(status_code=404, detail='Tag not found')

    media_filter = str(media or 'all').strip().lower()
    if media_filter not in ('all', 'image', 'video'):
        raise HTTPException(status_code=400, detail='Invalid media filter')

    source_filter = str(source or 'all').strip().lower()
    allowed_sources = {'all', 'cap', 'img', 'cap+img', 'manual', 'rule', '(null)'}
    if source_filter not in allowed_sources:
        raise HTTPException(status_code=400, detail='Invalid source filter')

    q = (
        db_s.query(Asset.id, Asset.path, Asset.mime)
        .join(AssetTag, AssetTag.asset_id == Asset.id)
        .filter(AssetTag.tag_id == int(tag_id), _visible_assets_filter())
    )
    if media_filter == 'image':
        q = q.filter((Asset.mime == None) | (~Asset.mime.startswith('video')))
    elif media_filter == 'video':
        q = q.filter(Asset.mime.startswith('video'))
    if source_filter == '(null)':
        q = q.filter(AssetTag.source.is_(None))
    elif source_filter != 'all':
        q = q.filter(AssetTag.source == source_filter)

    total = int(q.count())
    rows = (
        q.order_by(Asset.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        'tag': {'id': int(tag.id), 'name': tag.name, 'type': tag.type},
        'media': media_filter,
        'source': source_filter,
        'page': page,
        'page_size': page_size,
        'total': total,
        'items': [
            {'id': int(aid), 'path': path, 'mime': mime}
            for aid, path, mime in rows
        ],
    }


@app.get('/assets/{asset_id}/tags')
def get_asset_tags(asset_id: int, db_s: Session = Depends(get_db)):
    from .db import Tag, AssetTag
    a = db_s.get(Asset, asset_id)
    if not a:
        raise HTTPException(status_code=404, detail='Asset not found')
    rows = (
        db_s.query(Tag, AssetTag)
        .join(AssetTag, AssetTag.tag_id==Tag.id)
        .filter(AssetTag.asset_id==asset_id)
        .order_by(AssetTag.id.asc())
        .all()
    )
    return {
        'asset_id': asset_id,
        'tags': [
            {
                'id': t.id,
                'name': t.name,
                'type': t.type,
                'source': at.source,
                'score': at.score,
                'model': at.model,
            }
            for t, at in rows
        ],
    }

@app.post('/assets/{asset_id}/tags')
def add_asset_tags(asset_id: int, names: list[str] = Body(..., embed=True), tag_type: str | None = Body(None, embed=True), db_s: Session = Depends(get_db)):
    from .db import Tag, AssetTag, AssetTagBlock
    a = db_s.get(Asset, asset_id)
    if not a:
        raise HTTPException(status_code=404, detail='Asset not found')
    added = []
    effective_type = (str(tag_type or 'manual').strip() or None)
    for nm in names:
        nm = nm.strip()
        if not nm:
            continue
        t = db_s.query(Tag).filter(Tag.name==nm).first()
        if not t:
            t = Tag(name=nm, type=effective_type)
            db_s.add(t)
            db_s.flush()
        elif (not t.type) and effective_type:
            t.type = effective_type
        blocked = db_s.query(AssetTagBlock).filter(AssetTagBlock.asset_id==asset_id, AssetTagBlock.tag_id==t.id).first()
        if blocked is not None:
            db_s.delete(blocked)
        exists = db_s.query(AssetTag).filter(AssetTag.asset_id==asset_id, AssetTag.tag_id==t.id).first()
        if not exists:
            at = AssetTag(asset_id=asset_id, tag_id=t.id, source='manual', model='manual')
            db_s.add(at)
            added.append(nm)
        else:
            exists.source = 'manual'
            exists.model = 'manual'
    db_s.commit()
    return {'asset_id': asset_id, 'added': added}

@app.delete('/assets/{asset_id}/tags')
def remove_asset_tags(
    asset_id: int,
    tag_ids: list[int] = Body(..., embed=True),
    block_auto: bool = Body(True, embed=True),
    db_s: Session = Depends(get_db),
):
    from .db import Tag, AssetTag, AssetTagBlock

    a = db_s.get(Asset, asset_id)
    if not a:
        raise HTTPException(status_code=404, detail='Asset not found')

    clean_ids: list[int] = []
    for raw in (tag_ids or []):
        try:
            tid = int(raw)
        except Exception:
            continue
        if tid > 0:
            clean_ids.append(tid)
    if not clean_ids:
        return {'asset_id': asset_id, 'removed': [], 'blocked_tag_ids': []}

    removed: list[dict[str, object]] = []
    blocked_tag_ids: list[int] = []
    rows = db_s.query(Tag).filter(Tag.id.in_(clean_ids)).all()
    for t in rows:
        rel = db_s.query(AssetTag).filter(AssetTag.asset_id==asset_id, AssetTag.tag_id==t.id).first()
        if rel is not None:
            db_s.delete(rel)
            removed.append({'id': t.id, 'name': t.name})
        if block_auto:
            blocked = db_s.query(AssetTagBlock).filter(
                AssetTagBlock.asset_id==asset_id,
                AssetTagBlock.tag_id==t.id,
            ).first()
            if blocked is None:
                db_s.add(AssetTagBlock(asset_id=asset_id, tag_id=t.id))
            blocked_tag_ids.append(int(t.id))
    db_s.commit()
    return {'asset_id': asset_id, 'removed': removed, 'blocked_tag_ids': blocked_tag_ids}

@app.post('/search/tags')
def search_by_tags(tags: list[str] = Body(..., embed=True), mode: str = Body('any', embed=True), media: str = Body('all', embed=True), k: int = Body(100, embed=True), db_s: Session = Depends(get_db)):
    from sqlalchemy import func as _f
    from .db import Tag, AssetTag
    if not tags:
        raise HTTPException(status_code=400, detail='tags required')
    tag_rows = db_s.query(Tag).filter(Tag.name.in_(tags)).all()
    if not tag_rows:
        return {'query': tags, 'results': []}
    tag_ids = [t.id for t in tag_rows]
    q = db_s.query(AssetTag.asset_id, _f.count(AssetTag.tag_id).label('cnt')).filter(AssetTag.tag_id.in_(tag_ids)).group_by(AssetTag.asset_id)
    if mode == 'all':
        q = q.having(_f.count(AssetTag.tag_id) >= len(tag_ids))
    q = q.limit(k)
    asset_ids = [aid for (aid, _) in q.all()]
    if not asset_ids:
        return {'query': tags, 'results': []}
    qa = db_s.query(Asset).filter(Asset.id.in_(asset_ids), _visible_assets_filter())
    if media == 'image':
        qa = qa.filter((Asset.mime == None) | (~Asset.mime.startswith('video')))
    elif media == 'video':
        qa = qa.filter(Asset.mime.startswith('video'))
    assets = qa.all()
    return {'query': tags, 'mode': mode, 'results': [{'asset_id': a.id, 'path': a.path, 'mime': a.mime} for a in assets]}

# --- Smart search (hybrid): vector + caption + tags ---
@app.post('/search/smart')
def search_smart(text: str | None = Body(None, embed=True), tags: list[str] | None = Body(None, embed=True), media: str = Body('all', embed=True), k: int = Body(20, embed=True), db_s: Session = Depends(get_db)):
    from .db import Caption, Tag, AssetTag
    scores: dict[int, float] = {}
    # Vector search across images/videos
    if text:
        try:
            if media in ('all', 'image') and tasks_mod.INDEX_SINGLETON is not None:
                qv = tasks_mod.EMBED_SERVICE.embed_text(text) if tasks_mod.EMBED_SERVICE else None
                if qv is not None:
                    for aid, sc in tasks_mod.INDEX_SINGLETON.search(qv, k=k*2):
                        scores[aid] = max(scores.get(aid, 0.0), float(sc))
            if media in ('all', 'video') and getattr(tasks_mod, 'VIDEO_INDEX_SINGLETON', None) is not None:
                qv = tasks_mod.EMBED_SERVICE.embed_text(text) if tasks_mod.EMBED_SERVICE else None
                if qv is not None:
                    for aid, sc in tasks_mod.VIDEO_INDEX_SINGLETON.search(qv, k=k*2):
                        scores[aid] = max(scores.get(aid, 0.0), float(sc))
        except Exception:
            pass
    # Caption match boost
    if text:
        from sqlalchemy import func as _f
        cq = (
            db_s.query(Caption.asset_id)
            .join(Asset, Asset.id == Caption.asset_id)
            .filter(_visible_assets_filter(), _f.lower(Caption.text).like(f"%{text.lower()}%"))
            .limit(1000)
            .all()
        )
        for (aid,) in cq:
            scores[aid] = scores.get(aid, 0.0) + 0.1
    # Tag match boost
    if tags:
        tag_rows = db_s.query(Tag).filter(Tag.name.in_(tags)).all()
        if tag_rows:
            tag_ids = [t.id for t in tag_rows]
            tq = (
                db_s.query(AssetTag.asset_id)
                .join(Asset, Asset.id == AssetTag.asset_id)
                .filter(AssetTag.tag_id.in_(tag_ids), _visible_assets_filter())
                .limit(2000)
                .all()
            )
            for (aid,) in tq:
                scores[aid] = scores.get(aid, 0.0) + 0.1
    # Filter media type
    if media in ('image', 'video'):
        ids = list(scores.keys())
        if ids:
            m = db_s.query(Asset.id, Asset.mime).filter(Asset.id.in_(ids)).all()
            for (aid, mm) in m:
                is_vid = bool(mm and mm.startswith('video'))
                if media == 'image' and is_vid:
                    scores.pop(aid, None)
                if media == 'video' and not is_vid:
                    scores.pop(aid, None)
    # Return top-k
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
    if not top:
        return {'query': {'text': text, 'tags': tags, 'media': media}, 'results': []}
    aset = {a.id: a for a in db_s.query(Asset).filter(Asset.id.in_([i for i,_ in top]), _visible_assets_filter()).all()}
    out = []
    for aid, sc in top:
        a = aset.get(aid)
        if not a:
            continue
        out.append({'asset_id': aid, 'score': round(float(sc), 4), 'path': a.path, 'mime': a.mime})
    return {'query': {'text': text, 'tags': tags, 'media': media}, 'results': out}

@app.post('/search/video')
def search_video(text: str = Body('', embed=True), k: int = Body(10, embed=True)):
    if tasks_mod.VIDEO_INDEX_SINGLETON is None:
        raise HTTPException(status_code=400, detail='Video index not initialized')
    # Embed query text and search
    try:
        qvec = tasks_mod.EMBED_SERVICE.embed_text(text) if tasks_mod.EMBED_SERVICE else None
        if qvec is None:
            raise RuntimeError('Embedding service unavailable')
        results = tasks_mod.VIDEO_INDEX_SINGLETON.search(qvec, k=k)
        return {'query': text, 'results': [{'asset_id': aid, 'score': score} for aid, score in results]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/video-seg-index/rebuild')
def video_segment_index_rebuild():
    try:
        if tasks_mod.VIDEO_SEG_INDEX_SINGLETON is None:
            tasks_mod.VIDEO_SEG_INDEX_SINGLETON = tasks_mod.InMemoryVectorIndex(tasks_mod.EMBED_DIM)
        tasks_mod.VIDEO_SEG_INDEX_SINGLETON.clear()
        import numpy as np
        from glob import glob
        from pathlib import Path as _Path
        ids = []; vecs = []
        for fp in glob(str(_Path(settings.derived_path) / 'video_embeddings' / 'seg_*.npy')):
            try:
                sid = int(_Path(fp).stem.split('_',1)[1])
                vec = np.load(fp).astype('float32')
                ids.append(sid); vecs.append(vec)
            except Exception:
                continue
        if ids:
            tasks_mod.VIDEO_SEG_INDEX_SINGLETON.add(ids, np.stack(vecs))
        return {'loaded': len(ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/search/video-segments')
def search_video_segments(text: str = Body('', embed=True), k: int = Body(10, embed=True), db_s: Session = Depends(get_db)):
    if tasks_mod.VIDEO_SEG_INDEX_SINGLETON is None:
        raise HTTPException(status_code=400, detail='Video segment index not initialized')
    try:
        qvec = tasks_mod.EMBED_SERVICE.embed_text(text) if tasks_mod.EMBED_SERVICE else None
        if qvec is None:
            raise RuntimeError('Embedding service unavailable')
        results = tasks_mod.VIDEO_SEG_INDEX_SINGLETON.search(qvec, k=k)
        # Attach segment metadata
        from .db import VideoSegment
        out = []
        for sid, score in results:
            seg = db_s.get(VideoSegment, sid)
            item = {'segment_id': sid, 'score': score}
            if seg:
                item.update({'asset_id': seg.asset_id, 'start_sec': seg.start_sec, 'end_sec': seg.end_sec})
            out.append(item)
        return {'query': text, 'results': out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/videos/{asset_id}')
def get_video_info(asset_id: int, db_s: Session = Depends(get_db)):
    a = db_s.get(Asset, asset_id)
    if not a:
        raise HTTPException(status_code=404, detail='Asset not found')
    if not (a.mime or '').startswith('video'):
        raise HTTPException(status_code=400, detail='Asset is not a video')
    frames_dir = Path(DERIVED_PATH) / 'video_frames' / str(asset_id)
    frames = []
    try:
        if frames_dir.exists():
            for p in sorted(frames_dir.glob('frame_*.jpg')):
                frames.append(p.name)
            if (frames_dir / '_keyframes_stub.txt').exists():
                frames.append('_keyframes_stub.txt')
    except Exception:
        pass
    return {
        'id': a.id,
        'path': a.path,
        'mime': a.mime,
        'duration_sec': a.duration_sec,
        'fps': a.fps,
        'frames': frames,
    }

@app.get('/videos/{asset_id}/segments')
def get_video_segments(asset_id: int, db_s: Session = Depends(get_db)):
    from .db import VideoSegment
    a = db_s.get(Asset, asset_id)
    if not a:
        raise HTTPException(status_code=404, detail='Asset not found')
    segs = db_s.query(VideoSegment).filter(VideoSegment.asset_id==asset_id).order_by(VideoSegment.start_sec).all()
    return {
        'asset_id': asset_id,
        'segments': [
            {
                'id': s.id,
                'start_sec': s.start_sec,
                'end_sec': s.end_sec,
                'keyframe': s.keyframe_path,
                'embedding': s.embedding_path,
            } for s in segs
        ]
    }


def _asset_quality_tuple(asset: Asset) -> tuple[int, int, int, int]:
    pixels = int((getattr(asset, 'width', 0) or 0) * (getattr(asset, 'height', 0) or 0))
    return (
        1 if getattr(asset, 'taken_at', None) else 0,
        pixels,
        int(getattr(asset, 'file_size', 0) or 0),
        int(getattr(asset, 'id', 0) or 0),
    )


def _build_similarity_reduction_groups(
    db_s: Session,
    min_group_size: int,
    max_distance: int,
    sample_limit: int,
    cluster_limit: int,
) -> tuple[list[dict], dict]:
    groups: list[dict] = []
    visible = _visible_assets_filter()

    sha_rows = (
        db_s.query(Asset.hash_sha256, func.count(Asset.id).label('cnt'))
        .filter(visible)
        .group_by(Asset.hash_sha256)
        .having(func.count(Asset.id) >= min_group_size)
        .order_by(func.count(Asset.id).desc())
        .limit(cluster_limit)
        .all()
    )
    for idx, (sha, cnt) in enumerate(sha_rows):
        members = db_s.query(Asset).filter(Asset.hash_sha256 == sha, visible).order_by(Asset.id.desc()).all()
        if len(members) < min_group_size:
            continue
        keep = max(members, key=_asset_quality_tuple)
        hide_ids = [int(a.id) for a in members if int(a.id) != int(keep.id)]
        groups.append({
            'group_id': f"sha:{idx + 1}:{str(sha)[:12]}",
            'kind': 'sha256',
            'key': sha,
            'member_count': int(cnt or len(members)),
            'keep_asset_id': int(keep.id),
            'hide_asset_ids': hide_ids,
            'members': [
                {
                    'id': int(a.id),
                    'path': a.path,
                    'mime': a.mime,
                    'status': a.status,
                    'distance': 0,
                    'is_keep': int(a.id) == int(keep.id),
                }
                for a in members
            ],
        })

    phash_assets = (
        db_s.query(Asset)
        .filter(visible, Asset.perceptual_hash != None)
        .order_by(Asset.id.desc())
        .limit(sample_limit)
        .all()
    )

    processed: list[tuple[Asset, int]] = []
    for a in phash_assets:
        try:
            processed.append((a, int(str(a.perceptual_hash), 16)))
        except Exception:
            continue

    visited: set[int] = set()
    near_idx = 0
    for i, (asset_a, hash_a) in enumerate(processed):
        if int(asset_a.id) in visited:
            continue
        group: list[tuple[Asset, int]] = [(asset_a, 0)]
        visited.add(int(asset_a.id))
        for j in range(i + 1, len(processed)):
            asset_b, hash_b = processed[j]
            if int(asset_b.id) in visited:
                continue
            distance = (hash_a ^ hash_b).bit_count()
            if distance <= max_distance:
                group.append((asset_b, int(distance)))
                visited.add(int(asset_b.id))
        if len(group) < min_group_size:
            continue
        keep_asset = max([a for a, _ in group], key=_asset_quality_tuple)
        hide_ids = [int(a.id) for a, _ in group if int(a.id) != int(keep_asset.id)]
        near_idx += 1
        groups.append({
            'group_id': f"near:{near_idx}:{int(keep_asset.id)}",
            'kind': 'near',
            'key': str(getattr(keep_asset, 'perceptual_hash', '') or ''),
            'member_count': len(group),
            'keep_asset_id': int(keep_asset.id),
            'hide_asset_ids': hide_ids,
            'members': [
                {
                    'id': int(a.id),
                    'path': a.path,
                    'mime': a.mime,
                    'status': a.status,
                    'distance': int(dist),
                    'is_keep': int(a.id) == int(keep_asset.id),
                }
                for a, dist in sorted(group, key=lambda row: (0 if int(row[0].id) == int(keep_asset.id) else 1, row[1], int(row[0].id)))
            ],
        })
        if near_idx >= cluster_limit:
            break

    groups.sort(key=lambda g: (-int(g.get('member_count', 0)), str(g.get('kind', '')), str(g.get('group_id', ''))))
    keep_ids = sorted({int(g.get('keep_asset_id')) for g in groups if g.get('keep_asset_id') is not None})
    hide_ids_unique = sorted({int(aid) for g in groups for aid in (g.get('hide_asset_ids') or [])})
    summary = {
        'groups': len(groups),
        'keep_candidates': len(keep_ids),
        'hide_candidates': sum(len(g.get('hide_asset_ids') or []) for g in groups),
        'unique_hide_candidates': len(hide_ids_unique),
    }
    return groups, summary


@app.get('/duplicates/reduction/preview')
def preview_similarity_reduction(
    min_group_size: int = Query(2, ge=2),
    max_distance: int = Query(5, ge=1, le=32),
    sample_limit: int = Query(1000, ge=100, le=5000),
    cluster_limit: int = Query(60, ge=1, le=200),
    db_s: Session = Depends(get_db),
):
    groups, summary = _build_similarity_reduction_groups(
        db_s=db_s,
        min_group_size=min_group_size,
        max_distance=max_distance,
        sample_limit=sample_limit,
        cluster_limit=cluster_limit,
    )
    return {
        'api_version': schemas.API_VERSION,
        'min_group_size': min_group_size,
        'max_distance': max_distance,
        'sample_limit': sample_limit,
        'cluster_limit': cluster_limit,
        'summary': summary,
        'groups': groups,
    }


@app.post('/duplicates/reduction/apply')
def apply_similarity_reduction(
    min_group_size: int = Body(2, embed=True),
    max_distance: int = Body(5, embed=True),
    sample_limit: int = Body(1000, embed=True),
    cluster_limit: int = Body(60, embed=True),
    db_s: Session = Depends(get_db),
):
    groups, summary = _build_similarity_reduction_groups(
        db_s=db_s,
        min_group_size=max(2, int(min_group_size or 2)),
        max_distance=max(1, min(32, int(max_distance or 5))),
        sample_limit=max(100, min(5000, int(sample_limit or 1000))),
        cluster_limit=max(1, min(200, int(cluster_limit or 60))),
    )
    keep_ids = {int(g.get('keep_asset_id')) for g in groups if g.get('keep_asset_id') is not None}
    hide_ids = sorted({int(aid) for g in groups for aid in (g.get('hide_asset_ids') or []) if int(aid) not in keep_ids})
    if not hide_ids:
        return {
            'api_version': schemas.API_VERSION,
            'suppressed': 0,
            'summary': summary,
            'groups': groups,
            'suppressed_asset_ids': [],
        }

    assets = db_s.query(Asset).filter(Asset.id.in_(hide_ids), _visible_assets_filter()).all()
    suppressed_ids: list[int] = []
    for a in assets:
        if a.id in keep_ids:
            continue
        if getattr(a, 'status', None) != 'suppressed':
            a.status = 'suppressed'
            suppressed_ids.append(int(a.id))
    db_s.commit()
    return {
        'api_version': schemas.API_VERSION,
        'suppressed': len(suppressed_ids),
        'summary': summary,
        'groups': groups,
        'suppressed_asset_ids': suppressed_ids,
    }


@app.post('/duplicates/reduction/restore')
def restore_similarity_reduction(asset_ids: list[int] | None = Body(None, embed=True), db_s: Session = Depends(get_db)):
    q = db_s.query(Asset).filter(Asset.status == 'suppressed')
    if asset_ids is not None:
        if not asset_ids:
            return {'api_version': schemas.API_VERSION, 'restored': 0, 'asset_ids': []}
        q = q.filter(Asset.id.in_(asset_ids))
    rows = q.all()
    restored_ids: list[int] = []
    for a in rows:
        a.status = 'active'
        restored_ids.append(int(a.id))
    db_s.commit()
    return {'api_version': schemas.API_VERSION, 'restored': len(restored_ids), 'asset_ids': restored_ids}


@app.get('/assets/suppressed')
def list_suppressed_assets(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500), db_s: Session = Depends(get_db)):
    q = db_s.query(Asset).filter(Asset.status == 'suppressed')
    total = q.count()
    rows = q.order_by(Asset.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        'api_version': schemas.API_VERSION,
        'page': page,
        'page_size': page_size,
        'total': total,
        'items': [
            {
                'id': int(a.id),
                'path': a.path,
                'mime': a.mime,
                'status': a.status,
            }
            for a in rows
        ],
    }


@app.get('/duplicates', response_model=schemas.DuplicatesResponse)
def list_duplicates(min_group_size: int = Query(2, ge=2), mode: str = Query('all', description='sha256|phash|all'), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db_s: Session = Depends(get_db)):
    results: dict = {'api_version': schemas.API_VERSION}
    offset = (page-1)*page_size
    slice_limit = page_size
    if mode in ('all','sha256'):
        sha_groups_q = (
            db_s.query(Asset.hash_sha256, func.count(Asset.id).label('cnt'))
            .filter(_visible_assets_filter())
            .group_by(Asset.hash_sha256)
            .having(func.count(Asset.id) >= min_group_size)
            .order_by(func.count(Asset.id).desc())
        )
        total_sha = sha_groups_q.count()
        sha_groups = sha_groups_q.offset(offset).limit(slice_limit).all()
        sha_list = []
        for h, cnt in sha_groups:
            assets = db_s.query(Asset.id, Asset.path).filter(Asset.hash_sha256==h, _visible_assets_filter()).all()
            sha_list.append({'hash': h, 'count': cnt, 'assets': [{'id': a.id, 'path': a.path} for a in assets]})
        results['sha256'] = {'page': page, 'page_size': page_size, 'total_groups': total_sha, 'groups': sha_list}
    if mode in ('all','phash'):
        phash_groups_q = (
            db_s.query(Asset.perceptual_hash, func.count(Asset.id).label('cnt'))
            .filter(_visible_assets_filter(), Asset.perceptual_hash != None)
            .group_by(Asset.perceptual_hash)
            .having(func.count(Asset.id) >= min_group_size)
            .order_by(func.count(Asset.id).desc())
        )
        total_ph = phash_groups_q.count()
        phash_groups = phash_groups_q.offset(offset).limit(slice_limit).all()
        phash_list = []
        for ph, cnt in phash_groups:
            assets = db_s.query(Asset.id, Asset.path).filter(Asset.perceptual_hash==ph, _visible_assets_filter()).all()
            phash_list.append({'phash': ph, 'count': cnt, 'assets': [{'id': a.id, 'path': a.path} for a in assets]})
        results['phash'] = {'page': page, 'page_size': page_size, 'total_groups': total_ph, 'groups': phash_list}
    return results

@app.get('/duplicates/near', response_model=schemas.NearDuplicatesResponse)
def near_duplicates(max_distance: int = Query(5, ge=1, le=32), sample_limit: int = Query(1000, le=5000), cluster_limit: int = Query(50, le=200), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200), db_s: Session = Depends(get_db)):
    assets = db_s.query(Asset.id, Asset.path, Asset.perceptual_hash).filter(_visible_assets_filter(), Asset.perceptual_hash != None).limit(sample_limit).all()
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
    if tasks_mod.INDEX_SINGLETON is None or tasks_mod.EMBED_SERVICE is None:
        raise HTTPException(status_code=503, detail='Vector index not initialized')
    if not text and not asset_id:
        raise HTTPException(status_code=400, detail='Provide text or asset_id')
    if text:
        query_vec = tasks_mod.EMBED_SERVICE.embed_text_stub(text)
    else:
        asset = db_s.get(Asset, asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail='asset not found')
        apath = asset.path if isinstance(asset.path, str) else str(asset.path)
        query_vec = tasks_mod.EMBED_SERVICE.embed_image_stub(apath)
    matches = tasks_mod.INDEX_SINGLETON.search(query_vec, k=k)
    assets_map = {a.id: a for a in db_s.query(Asset).filter(Asset.id.in_([mid for mid,_ in matches]), _visible_assets_filter()).all()}
    result_items = []
    for mid, score in matches:
        aobj = assets_map.get(mid)
        if not aobj:
            continue
        result_items.append({'asset_id': mid, 'score': float(score), 'path': aobj.path})
    return {'api_version': schemas.API_VERSION, 'query': {'text': text, 'asset_id': asset_id}, 'k': k, 'results': result_items}

# --- Asset ingestion (upload) ---

def _ingest_asset_from_bytes(data: bytes, filename: str, db_s: Session) -> tuple[Asset, int]:
    """Create an Asset (or fetch existing by sha256) from raw bytes and enqueue tasks.

    Returns (asset, tasks_enqueued_count).
    """
    suffix = ''.join(['.', filename.split('.')[-1]]) if '.' in filename else '.jpg'
    if suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
        raise HTTPException(status_code=400, detail='unsupported file type')
    originals_root = Path(settings.originals_path)
    originals_root.mkdir(parents=True, exist_ok=True)
    import hashlib
    sha = hashlib.sha256(data).hexdigest()
    existing = db_s.query(Asset).filter(Asset.hash_sha256 == sha).first()
    if existing:
        return existing, 0
    fname = f"u_{int(time.time()*1000)}_{sha[:8]}{suffix or '.jpg'}"
    out_path = originals_root / fname
    with out_path.open('wb') as f:
        f.write(data)
    width = height = None
    try:
        from PIL import Image
        with Image.open(out_path) as im:
            upright = safe_exif_transpose(im)
            width, height = upright.size
    except Exception:
        pass
    asset = Asset(path=str(out_path.resolve()), hash_sha256=sha, width=width, height=height, file_size=len(data))
    db_s.add(asset)
    db_s.flush()
    enqueue = [
        Task(type='embed', priority=50, payload_json={'asset_id': asset.id, 'modality': 'image'}),
        Task(type='phash', priority=60, payload_json={'asset_id': asset.id}),
        Task(type='thumb', priority=80, payload_json={'asset_id': asset.id}),
        Task(type='caption', priority=110, payload_json={'asset_id': asset.id}),
        Task(type='face', priority=120, payload_json={'asset_id': asset.id}),
    ]
    for t in enqueue:
        db_s.add(t)
    db_s.commit()
    return asset, len(enqueue)

@app.post('/assets/upload', response_model=schemas.AssetUploadResponse)
async def upload_asset(data: bytes = Body(..., description='Raw image bytes'), filename: str = Query('upload.jpg'), db_s: Session = Depends(get_db)):
    """Upload a single image via raw body (no multipart)."""
    asset, enqueued = _ingest_asset_from_bytes(data, filename, db_s)
    return {
        'api_version': schemas.API_VERSION,
        'asset': {
            'id': asset.id,
            'path': asset.path,
            'mime': getattr(asset, 'mime', None),
            'hash_sha256': asset.hash_sha256,
            'perceptual_hash': getattr(asset, 'perceptual_hash', None),
            'width': asset.width,
            'height': asset.height,
            'file_size': getattr(asset, 'file_size', None),
            'taken_at': str(getattr(asset, 'taken_at', None)) if getattr(asset, 'taken_at', None) else None,
            'gps_lat': getattr(asset, 'gps_lat', None),
            'gps_lon': getattr(asset, 'gps_lon', None),
            'status': getattr(asset, 'status', None)
        },
        'tasks_enqueued': enqueued
    }

@app.get('/assets', response_model=schemas.AssetsListResponse)
def list_assets(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500), db_s: Session = Depends(get_db)):
    q = db_s.query(Asset).filter(_visible_assets_filter())
    total = q.count()
    rows = q.order_by(Asset.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    assets = []
    for a in rows:
        assets.append({
            'id': a.id,
            'path': a.path,
            'mime': a.mime,
            'hash_sha256': a.hash_sha256,
            'perceptual_hash': getattr(a,'perceptual_hash', None),
            'width': a.width,
            'height': a.height,
            'file_size': getattr(a,'file_size', None),
            'taken_at': str(getattr(a,'taken_at', None)) if getattr(a,'taken_at', None) else None,
            'gps_lat': getattr(a, 'gps_lat', None),
            'gps_lon': getattr(a, 'gps_lon', None),
            'status': getattr(a,'status', None)
        })
    return {
        'api_version': schemas.API_VERSION,
        'page': page,
        'page_size': page_size,
        'total': total,
        'assets': assets
    }

@app.get('/assets/detail/{asset_id}', response_model=schemas.AssetDetailResponse)
def get_asset_detail(asset_id: int, db_s: Session = Depends(get_db)):
    a = db_s.get(Asset, asset_id)
    if not a:
        raise HTTPException(status_code=404, detail='asset not found')
    return {
        'api_version': schemas.API_VERSION,
        'asset': {
            'id': a.id,
            'path': a.path,
            'mime': a.mime,
            'hash_sha256': a.hash_sha256,
            'perceptual_hash': getattr(a, 'perceptual_hash', None),
            'width': a.width,
            'height': a.height,
            'file_size': getattr(a, 'file_size', None),
            'taken_at': str(getattr(a, 'taken_at', None)) if getattr(a, 'taken_at', None) else None,
            'gps_lat': getattr(a, 'gps_lat', None),
            'gps_lon': getattr(a, 'gps_lon', None),
            'status': getattr(a, 'status', None),
        },
    }

@app.get('/assets/geo', response_model=schemas.AssetGeoResponse)
def list_geo_assets(
    media: str = Query('all', description='all|image|video'),
    limit: int = Query(3000, ge=1, le=20000),
    db_s: Session = Depends(get_db),
):
    media_val = (media or 'all').lower()
    if media_val not in ('all', 'image', 'video'):
        raise HTTPException(status_code=400, detail='media must be one of all|image|video')
    q = db_s.query(Asset).filter(_visible_assets_filter(), Asset.gps_lat != None, Asset.gps_lon != None)
    if media_val == 'image':
        q = q.filter(Asset.mime.like('image/%'))
    elif media_val == 'video':
        q = q.filter(Asset.mime.like('video/%'))
    total = q.count()
    rows = q.order_by(Asset.id.desc()).limit(limit).all()
    points = []
    for a in rows:
        points.append({
            'id': a.id,
            'path': a.path,
            'mime': a.mime,
            'gps_lat': float(a.gps_lat),
            'gps_lon': float(a.gps_lon),
            'taken_at': str(getattr(a, 'taken_at', None)) if getattr(a, 'taken_at', None) else None,
        })
    return {
        'api_version': schemas.API_VERSION,
        'total': total,
        'returned': len(points),
        'points': points,
    }

@app.post('/assets/upload/multipart', response_model=schemas.AssetUploadResponse)
async def upload_asset_multipart(file: UploadFile = File(...), db_s: Session = Depends(get_db)):
    """Upload a single image using multipart/form-data.

    Requires python-multipart to be installed; environment guard in tests ensures this.
    """
    data = await file.read()
    asset, enqueued = _ingest_asset_from_bytes(data, file.filename or 'upload.jpg', db_s)
    return {
        'api_version': schemas.API_VERSION,
        'asset': {
            'id': asset.id,
            'path': asset.path,
            'mime': getattr(asset, 'mime', None),
            'hash_sha256': asset.hash_sha256,
            'perceptual_hash': getattr(asset, 'perceptual_hash', None),
            'width': asset.width,
            'height': asset.height,
            'file_size': getattr(asset, 'file_size', None),
            'taken_at': str(getattr(asset, 'taken_at', None)) if getattr(asset, 'taken_at', None) else None,
            'gps_lat': getattr(asset, 'gps_lat', None),
            'gps_lon': getattr(asset, 'gps_lon', None),
            'status': getattr(asset, 'status', None)
        },
        'tasks_enqueued': enqueued
    }

@app.get('/debug/multipart')
def debug_multipart():
    try:
        import multipart  # type: ignore
        return {'ok': True, 'version': getattr(multipart, '__version__', None)}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

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
    'dim': tasks_mod.EMBED_DIM,
        'model_version': settings.embed_model_version or None,
        'reembed_scheduled': stale,
        'total_assets': total_assets,
    }

@app.post('/vector-index/rebuild')
def rebuild_vector_index(limit: int = Body(None), db_s: Session = Depends(get_db)):
    if tasks_mod.INDEX_SINGLETON is None:
        raise HTTPException(status_code=503, detail='Index not initialized')
    # clear and reload
    tasks_mod.INDEX_SINGLETON.clear()
    if isinstance(tasks_mod.INDEX_SINGLETON, FaissVectorIndex):
        loaded = load_faiss_index_from_embeddings(deps.SessionLocal, tasks_mod.INDEX_SINGLETON, limit=limit or settings.max_index_load)
        try:
            tasks_mod.INDEX_SINGLETON.save(settings.vector_index_path)
        except Exception:
            pass
    else:
        loaded = load_index_from_embeddings(deps.SessionLocal, tasks_mod.INDEX_SINGLETON, limit=limit or settings.max_index_load)
    return {'api_version': schemas.API_VERSION, 'reloaded': loaded, 'dim': tasks_mod.EMBED_DIM, 'size': len(tasks_mod.INDEX_SINGLETON), 'backend': settings.vector_index_backend}
# Routers
from .routers import people as people_router
from .routers import voice as voice_router
from .routers import voice_photo as voice_photo_router
from .routers import ui as ui_router
app.include_router(people_router.router, prefix='')
app.include_router(voice_router.router, prefix='')
app.include_router(voice_photo_router.router, prefix='')
app.include_router(ui_router.router, prefix='')

# --- Albums: Story generation (people/tags/location/caption)
@app.get('/albums/stories')
def albums_stories(
    media: str = Query('all', description='all|image|video'),
    story_type: str = Query('all', description='all|person|tag|location|caption'),
    min_assets: int = Query(3, ge=2, le=200),
    max_stories_per_type: int = Query(6, ge=1, le=30),
    story_asset_limit: int = Query(24, ge=1, le=200),
    caption_scan_limit: int = Query(4000, ge=200, le=20000),
    db_s: Session = Depends(get_db),
):
    from collections import defaultdict
    from .db import Asset, Person, FaceDetection, Tag, AssetTag, Caption
    from .tagging import extract_caption_tag_candidates

    media_filter = str(media or 'all').strip().lower()
    if media_filter not in ('all', 'image', 'video'):
        raise HTTPException(status_code=400, detail='Invalid media filter')

    story_filter = str(story_type or 'all').strip().lower()
    if story_filter not in ('all', 'person', 'tag', 'location', 'caption'):
        raise HTTPException(status_code=400, detail='Invalid story type')

    def _apply_media_filter(query):
        if media_filter == 'image':
            return query.filter((Asset.mime == None) | (~Asset.mime.startswith('video')))
        if media_filter == 'video':
            return query.filter(Asset.mime.startswith('video'))
        return query

    def _hydrate_items(asset_ids: list[int]) -> list[dict]:
        if not asset_ids:
            return []
        rows = db_s.query(Asset.id, Asset.path, Asset.mime).filter(Asset.id.in_(asset_ids)).all()
        by_id = {
            int(r.id): {'id': int(r.id), 'path': r.path, 'mime': r.mime}
            for r in rows
        }
        return [by_id[aid] for aid in asset_ids if aid in by_id]

    def _story_id(kind: str, raw: str) -> str:
        return f"{kind}:{uuid.uuid5(uuid.NAMESPACE_URL, f'{kind}:{raw}').hex[:12]}"

    stories: list[dict] = []

    if story_filter in ('all', 'person'):
        person_rows = _apply_media_filter(
            db_s.query(
                Person.id.label('person_id'),
                Person.display_name.label('person_name'),
                func.count(func.distinct(Asset.id)).label('cnt'),
            )
            .join(FaceDetection, FaceDetection.person_id == Person.id)
            .join(Asset, Asset.id == FaceDetection.asset_id)
            .filter(Asset.status == 'active')
        ).group_by(Person.id, Person.display_name) \
         .having(func.count(func.distinct(Asset.id)) >= min_assets) \
         .order_by(func.count(func.distinct(Asset.id)).desc(), Person.id.asc()) \
         .limit(max_stories_per_type) \
         .all()

        for row in person_rows:
            person_id = int(row.person_id)
            sample_ids = [
                int(aid) for (aid,) in _apply_media_filter(
                    db_s.query(Asset.id)
                    .join(FaceDetection, FaceDetection.asset_id == Asset.id)
                    .filter(FaceDetection.person_id == person_id, Asset.status == 'active')
                ).group_by(Asset.id).order_by(Asset.id.desc()).limit(story_asset_limit).all()
            ]
            items = _hydrate_items(sample_ids)
            if not items:
                continue
            title = (str(row.person_name or '').strip() or f"Person {person_id}")
            stories.append({
                'id': _story_id('person', str(person_id)),
                'type': 'person',
                'title': title,
                'subtitle': 'Face cluster story',
                'count': int(row.cnt or 0),
                'items': items,
                'open': {'mode': 'person', 'person_id': person_id, 'person_name': title},
            })

    if story_filter in ('all', 'tag'):
        tag_rows = _apply_media_filter(
            db_s.query(
                Tag.id.label('tag_id'),
                Tag.name.label('tag_name'),
                func.count(func.distinct(Asset.id)).label('cnt'),
            )
            .join(AssetTag, AssetTag.tag_id == Tag.id)
            .join(Asset, Asset.id == AssetTag.asset_id)
            .filter(Asset.status == 'active')
        ).group_by(Tag.id, Tag.name) \
         .having(func.count(func.distinct(Asset.id)) >= min_assets) \
         .order_by(func.count(func.distinct(Asset.id)).desc(), Tag.name.asc()) \
         .limit(max_stories_per_type) \
         .all()

        for row in tag_rows:
            tag_id = int(row.tag_id)
            sample_ids = [
                int(aid) for (aid,) in _apply_media_filter(
                    db_s.query(Asset.id)
                    .join(AssetTag, AssetTag.asset_id == Asset.id)
                    .filter(AssetTag.tag_id == tag_id, Asset.status == 'active')
                ).group_by(Asset.id).order_by(Asset.id.desc()).limit(story_asset_limit).all()
            ]
            items = _hydrate_items(sample_ids)
            if not items:
                continue
            tag_name = str(row.tag_name or f"Tag {tag_id}")
            stories.append({
                'id': _story_id('tag', str(tag_id)),
                'type': 'tag',
                'title': tag_name,
                'subtitle': 'Tag topic story',
                'count': int(row.cnt or 0),
                'items': items,
                'open': {'mode': 'tag', 'tag_id': tag_id, 'tag_name': tag_name},
            })

    if story_filter in ('all', 'location'):
        lat_bucket = func.round(Asset.gps_lat, 2)
        lon_bucket = func.round(Asset.gps_lon, 2)
        location_rows = _apply_media_filter(
            db_s.query(
                lat_bucket.label('lat_b'),
                lon_bucket.label('lon_b'),
                func.count(Asset.id).label('cnt'),
            )
            .filter(
                Asset.status == 'active',
                Asset.gps_lat != None,
                Asset.gps_lon != None,
            )
        ).group_by(lat_bucket, lon_bucket) \
         .having(func.count(Asset.id) >= min_assets) \
         .order_by(func.count(Asset.id).desc()) \
         .limit(max_stories_per_type) \
         .all()

        for row in location_rows:
            if row.lat_b is None or row.lon_b is None:
                continue
            lat_value = float(row.lat_b)
            lon_value = float(row.lon_b)
            sample_ids = [
                int(aid) for (aid,) in _apply_media_filter(
                    db_s.query(Asset.id).filter(
                        Asset.status == 'active',
                        Asset.gps_lat != None,
                        Asset.gps_lon != None,
                        func.round(Asset.gps_lat, 2) == lat_value,
                        func.round(Asset.gps_lon, 2) == lon_value,
                    )
                ).order_by(Asset.id.desc()).limit(story_asset_limit).all()
            ]
            items = _hydrate_items(sample_ids)
            if not items:
                continue
            title = f"Near {lat_value:.2f}, {lon_value:.2f}"
            stories.append({
                'id': _story_id('location', f"{lat_value:.2f},{lon_value:.2f}"),
                'type': 'location',
                'title': title,
                'subtitle': 'Geo cluster story',
                'count': int(row.cnt or 0),
                'items': items,
                'open': {'mode': 'location', 'lat': lat_value, 'lon': lon_value},
            })

    if story_filter in ('all', 'caption'):
        caption_rows = _apply_media_filter(
            db_s.query(Caption.asset_id, Caption.text)
            .join(Asset, Asset.id == Caption.asset_id)
            .filter(Asset.status == 'active', Caption.superseded == False)
        ).order_by(Caption.id.desc()).limit(caption_scan_limit).all()

        keyword_assets: dict[str, set[int]] = defaultdict(set)
        for row in caption_rows:
            text = str(row.text or '').strip()
            if not text:
                continue
            try:
                candidates = extract_caption_tag_candidates(text, max_tags=8)
            except Exception:
                continue
            seen: set[str] = set()
            for cand in candidates:
                name = str((cand or {}).get('name') or '').strip().lower()
                if len(name) < 2:
                    continue
                if name in seen:
                    continue
                seen.add(name)
                keyword_assets[name].add(int(row.asset_id))

        ranked_caption_topics = sorted(
            [
                (name, len(asset_ids), sorted(list(asset_ids), reverse=True))
                for name, asset_ids in keyword_assets.items()
                if len(asset_ids) >= min_assets
            ],
            key=lambda x: (-x[1], x[0]),
        )[:max_stories_per_type]

        for name, count, asset_ids in ranked_caption_topics:
            sample_ids = [int(aid) for aid in asset_ids[:story_asset_limit]]
            items = _hydrate_items(sample_ids)
            if not items:
                continue
            stories.append({
                'id': _story_id('caption', name),
                'type': 'caption',
                'title': name,
                'subtitle': 'Caption theme story',
                'count': int(count),
                'items': items,
                'open': {'mode': 'caption', 'query': name},
            })

    stories.sort(key=lambda s: (-int(s.get('count') or 0), str(s.get('type') or ''), str(s.get('title') or '')))
    return {
        'api_version': schemas.API_VERSION,
        'media': media_filter,
        'story_type': story_filter,
        'min_assets': min_assets,
        'total': len(stories),
        'stories': stories,
    }

# --- Albums: Time hierarchy (year -> month -> day)
@app.get('/albums/time', response_model=schemas.TimeAlbumsResponse)
def albums_time(limit_per_bucket: int = Query(5, ge=1, le=50), path_prefix: str | None = Query(None, description="Optional prefix to restrict asset paths (test isolation)"), db_s: Session = Depends(get_db)):
    """Return hierarchical time albums (year/month/day) with counts and sample asset ids.

    Uses Asset.taken_at when available; falls back to created_at if taken_at is NULL.
    """
    from sqlalchemy import func, case
    from .db import Asset
    # Determine effective timestamp
    ts_col = case((Asset.taken_at != None, Asset.taken_at), else_=Asset.created_at)  # type: ignore
    # SQLite strftime tokens: %Y, %m, %d
    year_expr = func.strftime('%Y', ts_col)
    month_expr = func.strftime('%m', ts_col)
    day_expr = func.strftime('%d', ts_col)
    # Aggregate counts
    y_l = year_expr.label('y')
    m_l = month_expr.label('m')
    d_l = day_expr.label('d')
    base_q = db_s.query(y_l, m_l, d_l, func.count(Asset.id).label('cnt')).filter(_visible_assets_filter())
    if path_prefix:
        base_q = base_q.filter(Asset.path.like(f"{path_prefix}%"))
    rows = base_q.group_by(y_l, m_l, d_l).order_by(y_l, m_l, d_l).all()
    # Fetch sample assets per (y,m,d) using window or fallback simple query per bucket (bounded by total rows * limit)
    # Build mapping for faster second pass
    from collections import defaultdict
    day_map = defaultdict(list)
    for r in rows:
        day_map[(r.y, r.m, r.d)] = [r.cnt]  # store count first
    # Collect samples in one query limited to recent assets per date (heuristic: order by id desc)
    # Simpler: iterate (bounded) and query per bucket while respecting limit_per_bucket
    for (y,m,d), meta in day_map.items():
        filt = [func.strftime('%Y', ts_col)==y, func.strftime('%m', ts_col)==m, func.strftime('%d', ts_col)==d]
        if path_prefix:
            filt.append(Asset.path.like(f"{path_prefix}%"))
        q = db_s.query(Asset.id).filter(_visible_assets_filter(), *filt)\
            .order_by(Asset.id.desc()).limit(limit_per_bucket).all()
        ids = [rid for (rid,) in q]
        day_map[(y,m,d)] = [meta[0], ids]
    # Organize hierarchy
    from collections import OrderedDict
    years: OrderedDict[str, dict] = OrderedDict()
    for r in rows:
        y, m, d, cnt = r.y, r.m, r.d, r.cnt
        y_int = int(y)
        m_int = int(m)
        d_int = int(d)
        total_cnt, sample_ids = day_map[(y,m,d)]
        if y_int not in years:
            years[y_int] = {'count':0, 'months': OrderedDict(), 'sample': set()}
        y_entry = years[y_int]
        y_entry['count'] += cnt
        if m_int not in y_entry['months']:
            y_entry['months'][m_int] = {'count':0, 'days': OrderedDict(), 'sample': set()}
        m_entry = y_entry['months'][m_int]
        m_entry['count'] += cnt
        # Day
        m_entry['days'][d_int] = {'count': cnt, 'sample': sample_ids}
        # Accumulate samples (union up to limit_per_bucket)
        for sid in sample_ids:
            if len(y_entry['sample']) < limit_per_bucket:
                y_entry['sample'].add(sid)
            if len(m_entry['sample']) < limit_per_bucket:
                m_entry['sample'].add(sid)
    # Convert to schema objects
    year_objs: list[schemas.TimeAlbumYear] = []
    for y_int, y_entry in years.items():
        month_objs: list[schemas.TimeAlbumMonth] = []
        for m_int, m_entry in y_entry['months'].items():
            day_objs: list[schemas.TimeAlbumDay] = []
            for d_int, d_entry in m_entry['days'].items():
                day_objs.append(schemas.TimeAlbumDay(day=d_int, count=d_entry['count'], sample_asset_ids=d_entry['sample']))
            month_objs.append(schemas.TimeAlbumMonth(month=m_int, count=m_entry['count'], days=day_objs, sample_asset_ids=list(m_entry['sample'])))
        year_objs.append(schemas.TimeAlbumYear(year=y_int, count=y_entry['count'], months=month_objs, sample_asset_ids=list(y_entry['sample'])))
    return schemas.TimeAlbumsResponse(api_version=schemas.API_VERSION, years=year_objs)

# --- Plugin comment placeholder ---
# Add any plugin-specific initialization or route inclusion here

@app.get('/metrics.prom')
def metrics_prometheus(db_s: Session = Depends(get_db)):
    """Prometheus exposition endpoint."""
    # ensure gauges roughly current
    try:
        from .db import Task, Person
        pending = db_s.query(Task).filter(Task.state=='pending').count()
        running = db_s.query(Task).filter(Task.state=='running').count()
        dead = db_s.query(Task).filter(Task.state=='dead').count()
        persons = db_s.query(Person).count()
        metrics_mod.update_queue_gauges(pending, running)
        metrics_mod.update_dead_tasks(dead)
        metrics_mod.update_persons_total(persons)
        metrics_mod.update_vector_index_size(len(tasks_mod.INDEX_SINGLETON) if tasks_mod.INDEX_SINGLETON else 0)
    except Exception:
        pass
    blob = metrics_mod.render_prometheus()
    return Response(content=blob, media_type='text/plain; version=0.0.4')

# --- Admin: Dead-letter queue management ---
@app.get('/admin/tasks/dead')
def list_dead_tasks(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db_s: Session = Depends(get_db)):
    from .db import Task
    q = db_s.query(Task).filter(Task.state=='dead')
    total = q.count()
    items = q.order_by(Task.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {
        'api_version': schemas.API_VERSION,
        'page': page,
        'page_size': page_size,
        'total': total,
        'tasks': [
            {
                'id': t.id,
                'type': t.type,
                'state': t.state,
                'retry_count': t.retry_count,
                'last_error': t.last_error,
                'created_at': str(t.created_at) if t.created_at else None,
                'updated_at': str(t.updated_at) if t.updated_at else None,
                'started_at': str(t.started_at) if t.started_at else None,
                'finished_at': str(t.finished_at) if t.finished_at else None,
            } for t in items
        ]
    }

@app.post('/admin/tasks/{task_id}/requeue')
def requeue_task(task_id: int, db_s: Session = Depends(get_db)):
    from .db import Task
    task = db_s.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail='task not found')
    # Only allow requeue from dead|failed|canceled states
    if task.state not in ('dead','failed','canceled'):
        raise HTTPException(status_code=400, detail=f'cannot requeue from state {task.state}')
    task.state = 'pending'
    task.retry_count = 0
    task.started_at = None
    task.finished_at = None
    task.last_error = None
    task.scheduled_at = func.now()
    db_s.commit()
    return {'api_version': schemas.API_VERSION, 'task_id': task.id, 'state': task.state}

@app.on_event("shutdown")
def on_shutdown():
    try:
        executor.stop_workers()
    except Exception:
        pass

if __name__ == "__main__":
    import uvicorn
    # Temporarily disable startup events for debugging
    import os
    os.environ['RUN_MODE'] = 'debug'
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="info")
