import os, json, time, random, numpy as np
import threading
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, text, update
from .db import Task, Asset, Embedding, Caption, FaceDetection, Person
from .vector_index import InMemoryVectorIndex, FaissVectorIndex, EmbeddingService
from .config import get_settings
from .image_utils import safe_exif_transpose
from pathlib import Path
from PIL import Image
import imagehash
from datetime import datetime, timedelta
from . import metrics as metrics_mod
from .gps_utils import probe_video_metadata
import logging
logger = logging.getLogger(__name__)

# Allow very large photos from camera roll exports; avoids PIL decompression-bomb guard
# causing caption/face fallbacks on valid high-resolution images.
Image.MAX_IMAGE_PIXELS = None

EMBED_DIM = 512  # default; may be updated after loading real model
DERIVED_DIR = Path(os.getenv('DERIVED_PATH', os.path.join(os.getenv('VLM_DATA_ROOT', r'E:\VLM_DATA'), 'derived')))
( DERIVED_DIR / 'embeddings').mkdir(parents=True, exist_ok=True)
( DERIVED_DIR / 'thumbnails' / '256').mkdir(parents=True, exist_ok=True)
( DERIVED_DIR / 'thumbnails' / '1024').mkdir(parents=True, exist_ok=True)
( DERIVED_DIR / 'faces' / '256').mkdir(parents=True, exist_ok=True)
( DERIVED_DIR / 'face_embeddings').mkdir(parents=True, exist_ok=True)
( DERIVED_DIR / 'person_embeddings').mkdir(parents=True, exist_ok=True)
THUMB_SIZES = [256, 1024]
FACE_CLUSTER_DIST_THRESHOLD = 0.35  # default; overridden by settings

INDEX_SINGLETON: InMemoryVectorIndex | None = None
VIDEO_INDEX_SINGLETON: InMemoryVectorIndex | None = None
VIDEO_SEG_INDEX_SINGLETON: InMemoryVectorIndex | None = None
EMBED_SERVICE: EmbeddingService | None = None

class TaskExecutor:
    def __init__(self, session_factory=None, settings=None):
        # Allow tests to instantiate without wiring by pulling from app.main lazily
        if session_factory is None or settings is None:
            try:
                from . import dependencies as _deps
                from .config import get_settings as _gs
                if session_factory is None:
                    session_factory = _deps.SessionLocal
                if settings is None:
                    settings = _gs()
            except Exception:
                raise TypeError("TaskExecutor requires session_factory and settings when app deps unavailable")
        self.session_factory = session_factory
        self.settings = settings
        self._last_dim_backfill_scan = 0.0
        self._dim_backfill_interval = 300  # seconds
        # Legacy single-worker fields (still used by tests)
        self._stop = False
        self._threads: list = []
        # New multi-worker control
        self._workers: list[threading.Thread] = []
        self._stop_event = threading.Event()
        global INDEX_SINGLETON, VIDEO_INDEX_SINGLETON, VIDEO_SEG_INDEX_SINGLETON, EMBED_SERVICE, EMBED_DIM, FACE_CLUSTER_DIST_THRESHOLD
        if EMBED_SERVICE is None:
            EMBED_SERVICE = EmbeddingService(self.settings.embed_model_image, self.settings.embed_model_text, EMBED_DIM, getattr(self.settings,'embed_device','cpu'))
            if EMBED_SERVICE.dim != EMBED_DIM:
                EMBED_DIM = EMBED_SERVICE.dim
        if INDEX_SINGLETON is None:
            if self.settings.vector_index_backend == 'faiss':
                INDEX_SINGLETON = FaissVectorIndex(EMBED_DIM, getattr(self.settings,'vector_index_path',None))  # type: ignore
            else:
                INDEX_SINGLETON = InMemoryVectorIndex(EMBED_DIM)
        if VIDEO_INDEX_SINGLETON is None:
            # Video index: memory-only for MVP
            VIDEO_INDEX_SINGLETON = InMemoryVectorIndex(EMBED_DIM)
        if VIDEO_SEG_INDEX_SINGLETON is None:
            VIDEO_SEG_INDEX_SINGLETON = InMemoryVectorIndex(EMBED_DIM)
        # override cluster threshold if provided
        if getattr(self.settings, 'face_cluster_threshold', None):
            FACE_CLUSTER_DIST_THRESHOLD = self.settings.face_cluster_threshold

    def start_workers(self, concurrency: int):
        # Avoid double start
        if self._threads:
            return
        for wid in range(concurrency):
            import threading
            t = threading.Thread(target=self._worker_loop, args=(wid,), daemon=True, name=f"worker-{wid}")
            t.start()
            self._threads.append(t)

    def stop_workers(self):
        self._stop = True

    def _worker_loop(self, worker_id: int):
        base_idle = self.settings.worker_poll_interval
        while not self._stop:
            worked = self.run_once(worker_id=worker_id)
            if not worked:
                # jittered backoff when idle
                sleep_for = base_idle * (0.5 + random.random())
                time.sleep(min(2.0, sleep_for))
            else:
                # brief yield
                time.sleep(0.01)

    def _claim_next_task(self, session: Session):
        """Atomically claim the next pending task using optimistic update.

        Works on SQLite by performing an UPDATE guarded by state predicate.
        Returns the Task object if claim succeeded else None.
        """
        # Fetch candidate id first (simple query) then attempt guarded update
        now = datetime.utcnow()
        candidate = session.execute(
            select(Task.id).where(
                Task.state=='pending',
                (Task.scheduled_at==None) | (Task.scheduled_at <= now)
            ).order_by(Task.priority, Task.id).limit(1)
        ).scalar_one_or_none()
        if candidate is None:
            return None
        # Optimistic claim
        now = datetime.utcnow()
        updated = session.execute(
            text("UPDATE tasks SET state='running', started_at=:now WHERE id=:tid AND state='pending'").bindparams(now=now, tid=candidate)
        )
        if updated.rowcount != 1:  # lost race
            session.rollback()
            return None
        session.commit()  # persist state change before loading full row
        return session.get(Task, candidate)

    def run_once(self, worker_id: int | None = None):
        with self.session_factory() as session:
            task = self._claim_next_task(session)
            if not task:
                # maybe enqueue dim backfill batch periodically
                self._maybe_enqueue_dim_backfill(session)
                # update gauges (pending / running) periodically when idle
                try:
                    pending = session.query(Task).filter(Task.state=='pending').count()
                    running = session.query(Task).filter(Task.state=='running').count()
                    metrics_mod.update_queue_gauges(pending, running)
                except Exception:
                    pass
                return False
            # task already transitioned to running by _claim_next_task
            # initialize progress fields for known long-running tasks
            if task.type in ('person_recluster',) and task.progress_current is None:
                task.progress_current = 0
                session.commit()
            try:
                start_time = time.time()
                if task.type == 'embed':
                    self._handle_embed(session, task)
                elif task.type == 'thumb':
                    self._handle_thumb(session, task)
                elif task.type == 'caption':
                    self._handle_caption(session, task)
                elif task.type == 'face':
                    self._handle_face(session, task)
                elif task.type == 'face_embed':
                    self._handle_face_embed(session, task)
                elif task.type == 'person_cluster':
                    self._handle_person_cluster(session, task)
                elif task.type == 'person_label_propagate':
                    self._handle_person_label_propagate(session, task)
            except Exception as exc:
                task.state = 'failed'
                task.last_error = str(exc)[:4000]
                session.commit()
                return True
            # success transition
            task.state = 'finished'
            task.finished_at = datetime.utcnow()
            session.commit()
            # metrics
            try:
                metrics_mod.task_durations_seconds.labels(task.type).observe(time.time()-start_time)
            except Exception:
                pass
            return True
        return False

    def stop_workers(self):
        self._stop_event.set()
        for t in self._workers:
            try:
                t.join(timeout=1.0)
            except Exception:
                pass
        self._workers.clear()

    def _handle_embed(self, session: Session, task: Task):
        asset_id = task.payload_json['asset_id']
        asset = session.get(Asset, asset_id)
        if not asset:
            raise ValueError('asset missing')
        embed_sleep = float(os.getenv('EMBED_TASK_SLEEP','0') or '0')
        if embed_sleep > 0:
            time.sleep(embed_sleep)
        vec = EMBED_SERVICE.embed_image(asset.path) if EMBED_SERVICE else np.random.rand(EMBED_DIM).astype('float32')
        emb_path = DERIVED_DIR / 'embeddings' / f'{asset_id}.npy'
        np.save(emb_path, vec)
        existing = session.query(Embedding).filter_by(asset_id=asset_id, modality='image').first()
        if existing:
            existing.storage_path = str(emb_path)
            existing.model = self.settings.embed_model_image
            existing.dim = EMBED_DIM
            existing.device = getattr(self.settings, 'embed_device', 'cpu')
            if getattr(self.settings, 'embed_model_version', None):
                existing.model_version = self.settings.embed_model_version
        else:
            session.add(Embedding(asset_id=asset_id, modality='image', model=self.settings.embed_model_image, dim=EMBED_DIM, storage_path=str(emb_path), device=getattr(self.settings,'embed_device','cpu'), model_version=getattr(self.settings,'embed_model_version', None)))
        session.commit()
        if INDEX_SINGLETON:
            INDEX_SINGLETON.add([asset_id], vec.reshape(1, -1))
        try:
            metrics_mod.embeddings_generated.inc()
            metrics_mod.update_vector_index_size(len(INDEX_SINGLETON) if INDEX_SINGLETON else 0)
        except Exception:
            pass

    def _handle_thumb(self, session: Session, task: Task):
        asset_id = task.payload_json['asset_id']
        asset = session.get(Asset, asset_id)
        if not asset:
            raise ValueError('asset missing')
        thumb_sleep = float(os.getenv('THUMB_TASK_SLEEP','0') or '0')
        if thumb_sleep > 0:
            time.sleep(thumb_sleep)
        src = Path(asset.path)
        if not src.exists():
            raise FileNotFoundError(src)
        for size in THUMB_SIZES:
            out_dir = DERIVED_DIR / 'thumbnails' / str(size)
            out_path = out_dir / f"{asset_id}.jpg"
            if out_path.exists():
                continue
            with Image.open(src) as im:
                im = safe_exif_transpose(im)
                im.thumbnail((size, size))
                im.convert('RGB').save(out_path, 'JPEG', quality=85)
    def _handle_caption(self, session: Session, task: Task):
        """Generate a caption (or variant) for an asset and update status fields."""
        payload = task.payload_json or {}
        asset_id = payload.get('asset_id')
        force = bool(payload.get('force', False))
        profile = (payload.get('profile') or os.getenv('CAPTION_PROFILE','balanced')).lower()
        max_variants = int(os.getenv('CAPTION_MAX_VARIANTS','3') or '3')
        word_limit = int(os.getenv('CAPTION_WORD_LIMIT','40') or '40')
        asset = session.get(Asset, asset_id)
        if not asset:
            raise ValueError('asset missing')
        existing = session.query(Caption).filter(Caption.asset_id==asset_id).order_by(Caption.created_at.asc()).all()
        if existing and not force and len(existing) >= max_variants:
            return existing[-1]
        text = ''
        model_name = 'unknown'
        err = None
        try:
            from .caption_service import get_caption_provider
            from PIL import Image as _Im
            prov = get_caption_provider()
            with _Im.open(asset.path) as im:
                upright = safe_exif_transpose(im)
                text = prov.generate_caption(upright.convert('RGB'))
            model_name = prov.get_model_name()
        except Exception as e:  # fallback heuristics
            err = str(e)
            allow_stub_fallback = os.getenv('CAPTION_ENABLE_STUB_FALLBACK', 'false').lower() in ('1', 'true', 'yes')
            if not allow_stub_fallback:
                try:
                    asset.caption_variant_count = session.query(Caption).filter(Caption.asset_id==asset_id, Caption.superseded==False).count()
                    asset.caption_processed = bool(asset.caption_variant_count > 0)
                    asset.caption_processed_at = datetime.utcnow()
                    asset.caption_model_profile_last = profile
                    asset.caption_error_last = err
                    session.commit()
                except Exception:
                    session.rollback()
                # Do not generate stub captions by default; keep asset eligible for future backfill.
                return None
            base = os.path.splitext(Path(asset.path).name)[0]
            toks = [t for t in base.replace('-',' ').replace('_',' ').split() if t]
            text = 'Photo' if not toks else ' '.join(toks[:8])
            model_name = 'stub-fallback'
        # Word cap
        try:
            parts = text.split()
            if word_limit > 0 and len(parts) > word_limit:
                text = ' '.join(parts[:word_limit])
        except Exception:
            pass
        # Replace oldest non user_edited if at capacity
        if existing and len(existing) >= max_variants:
            target = next((c for c in existing if not c.user_edited), None)
            if target is None:
                return existing[-1]
            target.text = text
            target.model = model_name
            session.commit()
            return target
        # Infer quality tier
        qtier = 'balanced'
        if profile in ('fast','quality','balanced'):
            qtier = profile
        elif 'qwen' in model_name.lower():
            qtier = 'quality'
        elif 'blip' in model_name.lower():
            qtier = 'balanced'
        elif 'vit' in model_name.lower() or 'mini' in model_name.lower():
            qtier = 'fast'
        cap = Caption(asset_id=asset_id, text=text, model=model_name, user_edited=False, quality_tier=qtier, model_version=None)
        session.add(cap)
        session.flush()
        # Update asset status
        try:
            asset.caption_variant_count = session.query(Caption).filter(Caption.asset_id==asset_id, Caption.superseded==False).count()
            asset.caption_processed = True
            asset.caption_processed_at = datetime.utcnow()
            asset.caption_model_profile_last = profile
            asset.caption_error_last = err
            session.commit()
        except Exception:
            session.rollback()
        return cap

    def _handle_face(self, session: Session, task: Task):
        payload = task.payload_json or {}
        asset_id = payload.get('asset_id')
        force_redetect = bool(payload.get('force_redetect', False))
        supplement_only = bool(payload.get('supplement_only', True))
        dedupe_iou = float(payload.get('dedupe_iou', 0.60) or 0.60)
        if dedupe_iou < 0.0:
            dedupe_iou = 0.0
        if dedupe_iou > 1.0:
            dedupe_iou = 1.0

        def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
            ax1, ay1, aw, ah = a
            bx1, by1, bw, bh = b
            ax2 = ax1 + aw
            ay2 = ay1 + ah
            bx2 = bx1 + bw
            by2 = by1 + bh
            ix1 = max(ax1, bx1)
            iy1 = max(ay1, by1)
            ix2 = min(ax2, bx2)
            iy2 = min(ay2, by2)
            iw = max(0.0, ix2 - ix1)
            ih = max(0.0, iy2 - iy1)
            inter = iw * ih
            if inter <= 0.0:
                return 0.0
            union = (aw * ah) + (bw * bh) - inter
            if union <= 0.0:
                return 0.0
            return inter / union

        asset = session.get(Asset, asset_id)
        if not asset:
            raise ValueError(f'Asset {asset_id} not found for face task')
        src = Path(asset.path)
        if not src.exists():
            raise FileNotFoundError(src)
        faces = session.query(FaceDetection).filter(FaceDetection.asset_id==asset.id).all()
        if force_redetect or not faces:
            # Run detection provider
            try:
                from .face_detection_service import get_face_detection_provider
                provider = get_face_detection_provider()
                from PIL import Image as _Im
                import time as _t
                t0_det = _t.time()
                with _Im.open(src) as im_det:
                    upright = safe_exif_transpose(im_det)
                    dets = provider.detect(upright.convert('RGB'))
                try:  # pragma: no cover
                    import app.metrics as m
                    prov_name = type(provider).__name__.replace('DetectionProvider','').lower()
                    m.face_detection_inference_seconds.labels(prov_name or 'unknown').observe(_t.time()-t0_det)
                except Exception:
                    pass
            except Exception:
                # Do not inject fake face boxes by default; this pollutes face_detections.
                # Optional legacy behavior can be enabled via FACE_DETECT_CENTER_FALLBACK=true.
                dets = []
                if os.getenv('FACE_DETECT_CENTER_FALLBACK', 'false').lower() in ('1', 'true', 'yes'):
                    from PIL import Image as _Im
                    with _Im.open(src) as im_det:
                        w,h = safe_exif_transpose(im_det).size
                    size = min(w,h)*0.4
                    dets.append(type('DF',(),{'x':(w-size)/2,'y':(h-size)/2,'w':size,'h':size})())
                else:
                    logger.warning(f"Face detection failed for asset_id={asset.id}; skipping fallback box insertion", exc_info=True)
            existing_boxes = [(float(f.bbox_x), float(f.bbox_y), float(f.bbox_w), float(f.bbox_h)) for f in faces]
            for d in dets:
                cand = (float(d.x), float(d.y), float(d.w), float(d.h))
                is_dup = any(_iou(cand, box) >= dedupe_iou for box in existing_boxes)
                if is_dup and supplement_only:
                    continue
                face = FaceDetection(asset_id=asset.id, bbox_x=cand[0], bbox_y=cand[1], bbox_w=cand[2], bbox_h=cand[3], embedding_path=None)
                session.add(face)
                existing_boxes.append(cand)
            session.flush()
            faces = session.query(FaceDetection).filter(FaceDetection.asset_id==asset.id).all()
        # Generate / ensure crops
        out_dir = DERIVED_DIR / 'faces' / '256'
        with Image.open(src) as im_raw:
            im = safe_exif_transpose(im_raw)
            w, h = im.size
            for face in faces:
                crop_path = out_dir / f"{face.id}.jpg"
                if crop_path.exists():
                    continue
                x1 = int(max(0, face.bbox_x))
                y1 = int(max(0, face.bbox_y))
                x2 = int(min(w, face.bbox_x + face.bbox_w))
                y2 = int(min(h, face.bbox_y + face.bbox_h))
                # Optional margin expansion
                try:
                    from .config import get_settings as _gs
                    _s = _gs()
                    margin = getattr(_s, 'face_crop_margin', 0.0)
                except Exception:
                    margin = 0.0
                if margin > 0:
                    mw = int(margin * max(w,h))
                    x1 = max(0, x1 - mw)
                    y1 = max(0, y1 - mw)
                    x2 = min(w, x2 + mw)
                    y2 = min(h, y2 + mw)
                if x2 <= x1 or y2 <= y1:
                    continue
                face_crop = im.crop((x1, y1, x2, y2))
                face_crop.thumbnail((256,256))
                face_crop.convert('RGB').save(crop_path, 'JPEG', quality=85)
        # enqueue embedding tasks for faces lacking embeddings
        for face in faces:
            if not face.embedding_path:
                session.add(Task(type='face_embed', priority=135, payload_json={'face_id': face.id}))
        session.commit()
        try:
            import app.metrics as m
            m.faces_detected.inc(len(faces))
        except Exception:
            pass
        return faces

    def _handle_face_embed(self, session: Session, task: Task):
        face_id = task.payload_json.get('face_id') if task.payload_json else None
        if not face_id:
            raise ValueError('face_id missing in payload')
        face = session.get(FaceDetection, face_id)
        if not face:
            raise ValueError(f'FaceDetection {face_id} not found')
        if face.embedding_path:
            return  # already done
        crop_path = DERIVED_DIR / 'faces' / '256' / f'{face.id}.jpg'
        if not crop_path.exists():
            raise ValueError('face crop missing for embedding')
        from PIL import Image
        from .face_embedding_service import get_face_embedding_provider
        provider = get_face_embedding_provider()
        with Image.open(crop_path) as im:
            import time as _t
            t0_emb = _t.time()
            vec = provider.embed_face(im.convert('RGB'))
        try:  # pragma: no cover
            import app.metrics as m
            prov_name = type(provider).__name__.replace('FaceEmbeddingProvider','').replace('EmbeddingProvider','').lower()
            m.face_embedding_inference_seconds.labels(prov_name or 'unknown').observe(_t.time()-t0_emb)
        except Exception:
            pass
        emb_path = DERIVED_DIR / 'face_embeddings' / f'{face_id}.npy'
        np.save(emb_path, vec.astype('float32'))
        face.embedding_path = str(emb_path)
        session.commit()
        try:
            import app.metrics as m
            m.face_embeddings_generated.inc()
        except Exception:
            pass
        auto_cluster_enabled = os.getenv('FACE_AUTO_CLUSTER_ENABLED', 'false').lower() in ('1', 'true', 'yes')
        if auto_cluster_enabled:
            pending_cluster = session.query(Task).filter(Task.type=='person_cluster', Task.state=='pending').first()
            if not pending_cluster:
                unassigned_faces = session.query(FaceDetection).filter(FaceDetection.person_id==None, FaceDetection.embedding_path!=None).count()
                if unassigned_faces >= 5:
                    session.add(Task(type='person_cluster', priority=180, payload_json={}))
                    session.commit()
            # Possibly schedule a full recluster occasionally when number of persons grows
            persons_count = session.query(Person).count()
            if persons_count and persons_count % 25 == 0:
                existing_recluster = session.query(Task).filter(Task.type=='person_recluster', Task.state=='pending').first()
                if not existing_recluster:
                    session.add(Task(type='person_recluster', priority=250, payload_json={}))
                    session.commit()
        return str(emb_path)

    def _handle_person_cluster(self, session: Session, task: Task):
        # Incremental centroid clustering using cosine distance
        # Load existing persons and their centroids
        persons = session.query(Person).all()
        person_centroids = {}
        for p in persons:
            if p.embedding_path and os.path.exists(p.embedding_path):
                vec = np.load(p.embedding_path).astype('float32')
                # normalize
                n = np.linalg.norm(vec)
                if n > 0:
                    vec /= n
                person_centroids[p.id] = vec
        # Fetch unassigned faces with embeddings
        faces = session.query(FaceDetection).filter(
            FaceDetection.person_id == None,
            FaceDetection.embedding_path != None
        ).limit(500).all()
        if not faces:
            return 0
        new_persons_created = 0
        assignments = 0
        for face in faces:
            if not face.embedding_path or not os.path.exists(face.embedding_path):
                continue
            fvec = np.load(face.embedding_path).astype('float32')
            n = np.linalg.norm(fvec)
            if n > 0:
                fvec /= n
            # Find best existing person
            best_pid = None
            best_dist = 1e9
            for pid, cvec in person_centroids.items():
                dist = 1.0 - float(np.dot(fvec, cvec))
                if dist < best_dist:
                    best_dist = dist
                    best_pid = pid
            if best_pid is not None and best_dist <= FACE_CLUSTER_DIST_THRESHOLD:
                # assign to best person
                person = next(p for p in persons if p.id == best_pid)
                # update centroid (weighted average then renormalize)
                old_centroid = person_centroids[best_pid]
                new_centroid = (old_centroid * person.face_count + fvec) / (person.face_count + 1)
                n2 = np.linalg.norm(new_centroid)
                if n2 > 0:
                    new_centroid /= n2
                person_centroids[best_pid] = new_centroid
                # persist centroid update
                if person.embedding_path:
                    np.save(person.embedding_path, new_centroid.astype('float32'))
                else:
                    emb_path = DERIVED_DIR / 'person_embeddings' / f'{person.id}.npy'
                    np.save(emb_path, new_centroid.astype('float32'))
                    person.embedding_path = str(emb_path)
                person.face_count += 1
                face.person_id = person.id
                face.label_source = 'dnn'  # type: ignore[attr-defined]
                face.label_score = float(1.0 - best_dist)  # type: ignore[attr-defined]
                assignments += 1
            else:
                # create new person
                person = Person(face_count=1)
                session.add(person)
                session.flush()  # get id
                emb_path = DERIVED_DIR / 'person_embeddings' / f'{person.id}.npy'
                np.save(emb_path, fvec.astype('float32'))
                person.embedding_path = str(emb_path)
                person_centroids[person.id] = fvec
                face.person_id = person.id
                face.label_source = 'dnn'  # type: ignore[attr-defined]
                face.label_score = 1.0  # type: ignore[attr-defined]
                persons.append(person)
                new_persons_created += 1
                assignments += 1
        session.commit()
        return {'assigned_faces': assignments, 'new_persons': new_persons_created}

    def _handle_person_recluster(self, session: Session, task: Task):
        """Full recluster from scratch using current face embeddings.

        Strategy: fetch up to batch limit unassigned + assigned faces, compute embeddings, perform simple online reassignment.
        Existing persons are cleared (face_count reset) but preserved IDs to maintain references; could optionally merge small clusters.
        """
        limit = getattr(self.settings, 'face_recluster_batch_limit', 2000)
        # If cancel requested early, short circuit
        session.refresh(task)
        if task.cancel_requested:
            task.progress_current = 0
            task.progress_total = 0
            task.state = 'canceled'
            session.commit()
            return {'faces': 0, 'persons': session.query(Person).count(), 'canceled': True}

        faces = session.query(FaceDetection).filter(FaceDetection.embedding_path!=None).limit(limit).all()
        if not faces:
            return {'faces': 0, 'persons': 0}
        # load embeddings
        embs = []
        face_objs = []
        for f in faces:
            try:
                vec = np.load(f.embedding_path).astype('float32') if f.embedding_path else None
                if vec is None:
                    continue
                n = np.linalg.norm(vec)
                if n>0: vec /= n
                embs.append(vec)
                face_objs.append(f)
            except Exception:
                continue
        if not embs:
            return {'faces':0, 'persons':0}
        # reset persons mapping
        persons = session.query(Person).all()
        for p in persons:
            p.face_count = 0
        person_centroids: dict[int, np.ndarray] = {}
        # simple online clustering
        new_persons = 0
        # set total for progress
        task.progress_total = len(face_objs)
        session.commit()
        # optional artificial delay per face for testing (env var)
        per_face_sleep = float(os.getenv('PERSON_RECLUSTER_PER_FACE_SLEEP','0') or '0')
        for idx, (f, vec) in enumerate(zip(face_objs, embs), start=1):
            # cancellation check
            if task.cancel_requested:
                task.state = 'canceled'
                session.commit()
                return {'faces': idx-1, 'persons': len(persons), 'new_persons': new_persons, 'canceled': True}
            best_pid = None
            best_dist = 1e9
            for pid, cvec in person_centroids.items():
                dist = 1.0 - float(np.dot(vec, cvec))
                if dist < best_dist:
                    best_dist = dist
                    best_pid = pid
            if best_pid is not None and best_dist <= FACE_CLUSTER_DIST_THRESHOLD:
                # assign
                f.person_id = best_pid
                f.label_source = 'dnn'  # type: ignore[attr-defined]
                f.label_score = float(1.0 - best_dist)  # type: ignore[attr-defined]
                p = next(p for p in persons if p.id == best_pid)
                # update centroid
                new_c = (person_centroids[best_pid]*p.face_count + vec) / (p.face_count+1)
                n2 = np.linalg.norm(new_c)
                if n2>0: new_c /= n2
                person_centroids[best_pid] = new_c
                p.face_count +=1
            else:
                # create new person
                p = Person(face_count=1)
                session.add(p)
                session.flush()
                emb_path = DERIVED_DIR / 'person_embeddings' / f'{p.id}.npy'
                np.save(emb_path, vec.astype('float32'))
                p.embedding_path = str(emb_path)
                person_centroids[p.id] = vec
                f.person_id = p.id
                f.label_source = 'dnn'  # type: ignore[attr-defined]
                f.label_score = 1.0  # type: ignore[attr-defined]
                persons.append(p)
                new_persons +=1
            # update progress
            task.progress_current = idx
            if idx % 25 == 0 or idx == task.progress_total:
                session.commit()
            if per_face_sleep > 0:
                time.sleep(per_face_sleep)
        session.commit()
        return {'faces': len(face_objs), 'persons': len(persons), 'new_persons': new_persons}

    def _handle_person_label_propagate(self, session: Session, task: Task):
        """Propagate newly-manual labels to similar unassigned faces (DNN assignment).

        This is a targeted auto-assign pass:
        - references use only manual-labeled faces
        - candidates are only unassigned faces
        - assignment requires score + margin thresholds
        - only target person_ids are assignable
        """
        payload = task.payload_json or {}
        raw_ids = payload.get('person_ids') or []
        target_person_ids: set[int] = set()
        for v in raw_ids:
            try:
                target_person_ids.add(int(v))
            except Exception:
                continue
        if not target_person_ids:
            return {'assigned': 0, 'reason': 'no_target_person_ids'}

        score_threshold = float(payload.get('score_threshold', os.getenv('PERSON_LABEL_PROPAGATE_SCORE_THRESHOLD', '0.82')))
        margin = float(payload.get('margin', os.getenv('PERSON_LABEL_PROPAGATE_MARGIN', '0.015')))
        min_ref_faces = int(payload.get('min_ref_faces', os.getenv('PERSON_LABEL_PROPAGATE_MIN_REF_FACES', '2')))
        max_scan = int(payload.get('max_scan', os.getenv('PERSON_LABEL_PROPAGATE_MAX_SCAN', '0')))
        commit_every = int(payload.get('commit_every', 200))

        data_root = Path(os.getenv('VLM_DATA_ROOT', r'E:\VLM_DATA'))

        def _resolve_emb_path(ep: str) -> Path:
            p = Path(ep)
            if p.is_absolute():
                return p
            ep_norm = ep.replace("\\", "/")
            if ep_norm.lower().startswith("derived/"):
                return data_root / ep_norm
            return Path(ep)

        # Build manual reference centroids for all persons (for competition/margin),
        # while only allowing assignments to target persons.
        ref_rows = (
            session.query(FaceDetection.person_id, FaceDetection.embedding_path)
            .filter(FaceDetection.person_id != None)
            .filter(FaceDetection.embedding_path != None)
            .filter(FaceDetection.label_source == 'manual')
            .all()
        )
        by_person: dict[int, list[np.ndarray]] = {}
        for pid, ep in ref_rows:
            if pid is None or not ep:
                continue
            p = _resolve_emb_path(str(ep))
            if not p.exists():
                continue
            try:
                v = np.load(p).astype('float32')
                n = float(np.linalg.norm(v))
                if n > 0:
                    v = v / n
            except Exception:
                continue
            by_person.setdefault(int(pid), []).append(v)

        centroids: dict[int, np.ndarray] = {}
        for pid, vecs in by_person.items():
            if len(vecs) < min_ref_faces:
                continue
            c = np.mean(np.stack(vecs), axis=0).astype('float32')
            n = float(np.linalg.norm(c))
            if n > 0:
                c = c / n
            centroids[pid] = c

        target_with_ref = sorted(pid for pid in target_person_ids if pid in centroids)
        if not target_with_ref:
            return {'assigned': 0, 'reason': 'no_target_centroids', 'targets': sorted(target_person_ids)}

        q = (
            session.query(FaceDetection)
            .filter(FaceDetection.person_id == None)
            .filter(FaceDetection.embedding_path != None)
            .order_by(FaceDetection.id.asc())
        )
        if max_scan > 0:
            q = q.limit(max_scan)
        candidates = q.all()

        scanned = 0
        assigned = 0
        affected: set[int] = set()

        for face in candidates:
            scanned += 1
            ep = face.embedding_path
            if not ep:
                continue
            p = _resolve_emb_path(str(ep))
            if not p.exists():
                continue
            try:
                v = np.load(p).astype('float32')
                n = float(np.linalg.norm(v))
                if n > 0:
                    v = v / n
            except Exception:
                continue

            scores = sorted(
                [(float(np.dot(v, c)), pid) for pid, c in centroids.items()],
                reverse=True,
            )
            if not scores:
                continue
            best_score, best_pid = scores[0]
            second_score = scores[1][0] if len(scores) > 1 else -1.0
            gap = best_score - second_score

            if best_pid not in target_person_ids:
                continue
            if best_score < score_threshold or gap < margin:
                continue

            face.person_id = int(best_pid)
            face.label_source = 'dnn'  # type: ignore[attr-defined]
            face.label_score = float(best_score)  # type: ignore[attr-defined]
            assigned += 1
            affected.add(int(best_pid))

            if assigned % max(20, commit_every) == 0:
                session.commit()

        for pid in sorted(affected):
            cnt = (
                session.query(FaceDetection.id)
                .filter(FaceDetection.person_id == pid)
                .count()
            )
            p_obj = session.get(Person, pid)
            if p_obj is not None:
                p_obj.face_count = int(cnt)
        session.commit()
        return {
            'assigned': assigned,
            'scanned': scanned,
            'targets': sorted(target_person_ids),
            'targets_with_ref': target_with_ref,
            'score_threshold': score_threshold,
            'margin': margin,
            'min_ref_faces': min_ref_faces,
        }

    def _handle_dim_backfill(self, session: Session, task: Task):
        asset_id = task.payload_json.get('asset_id') if task.payload_json else None
        if not asset_id:
            return
        asset = session.get(Asset, asset_id)
        if not asset:
            return
        if asset.width and asset.height:
            return
        p = Path(asset.path)
        if not p.exists():
            return
        try:
            with Image.open(p) as im:
                upright = safe_exif_transpose(im)
                w, h = upright.size
            asset.width = w
            asset.height = h
            session.commit()
        except Exception:
            pass

    def _maybe_enqueue_dim_backfill(self, session: Session):
        now = time.time()
        if now - self._last_dim_backfill_scan < self._dim_backfill_interval:
            return
        self._last_dim_backfill_scan = now
        # find assets missing dimensions
        missing = session.query(Asset.id).filter(or_(Asset.width==None, Asset.height==None)).limit(50).all()
        if not missing:
            return
        # enqueue tasks
        for (aid,) in missing:
            session.add(Task(type='dim_backfill', priority=200, payload_json={'asset_id': aid}))
        session.commit()

    def _handle_phash(self, session: Session, task: Task):
        asset_id = task.payload_json.get('asset_id') if task.payload_json else None
        if not asset_id:
            return
        asset = session.get(Asset, asset_id)
        if not asset or asset.perceptual_hash:
            return
        p = Path(asset.path)
        if not p.exists():
            return
        try:
            with Image.open(p) as im:
                upright = safe_exif_transpose(im)
                ph = imagehash.phash(upright)
            asset.perceptual_hash = ph.__str__()
            session.commit()
        except Exception:
            pass

    # ---- Minimal Video Handlers (MVP stubs) ----
    def _handle_video_probe(self, session: Session, task: Task):
        # Ensure derived folders; probe duration/fps/GPS when available.
        payload = task.payload_json or {}
        asset_id = payload.get('asset_id')
        if not asset_id:
            return
        asset = session.get(Asset, asset_id)
        if not asset:
            return
        # create derived dirs
        (DERIVED_DIR / 'video_frames' / str(asset_id)).mkdir(parents=True, exist_ok=True)
        (DERIVED_DIR / 'video_embeddings').mkdir(parents=True, exist_ok=True)
        try:
            meta = probe_video_metadata(asset.path, timeout_sec=10)
            if meta.get('duration_sec') is not None:
                asset.duration_sec = float(meta['duration_sec'])
            if meta.get('fps') is not None:
                asset.fps = float(meta['fps'])
            if meta.get('gps_lat') is not None and meta.get('gps_lon') is not None:
                asset.gps_lat = float(meta['gps_lat'])
                asset.gps_lon = float(meta['gps_lon'])
        except Exception:
            pass
        session.commit()

    def _handle_video_keyframes(self, session: Session, task: Task):
        # Attempt to extract spaced frames with ffmpeg when available; else stub
        payload = task.payload_json or {}
        asset_id = payload.get('asset_id')
        if not asset_id:
            return
        src = None
        with self.session_factory() as s2:
            a = s2.get(Asset, asset_id)
            if a:
                src = a.path
        out_dir = DERIVED_DIR / 'video_frames' / str(asset_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        if not src or not os.path.exists(src):
            return
        interval = max(0.5, float(getattr(self.settings, 'video_keyframe_interval_sec', 2.0)))
        # Use ffmpeg -vf fps=1/interval to sample roughly one frame per interval
        try:
            import subprocess
            cmd = [
                'ffmpeg','-hide_banner','-loglevel','error','-y',
                '-i', src,
                '-vf', f"fps=1/{interval}",
                str(out_dir / 'frame_%05d.jpg')
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        except Exception:
            # fallback: marker file
            try:
                (out_dir / '_keyframes_stub.txt').write_text('keyframes not implemented (ffmpeg missing)')
            except Exception:
                pass

    def _handle_video_embed(self, session: Session, task: Task):
        # Compute pooled embedding over extracted frames if present; else zero-vector stub
        payload = task.payload_json or {}
        asset_id = payload.get('asset_id')
        if not asset_id:
            return
        frames_dir = DERIVED_DIR / 'video_frames' / str(asset_id)
        vecs = []
        if frames_dir.exists():
            try:
                from PIL import Image as _Im
                import glob
                frame_files = sorted(glob.glob(str(frames_dir / 'frame_*.jpg')))[:32]
                for fp in frame_files:
                    try:
                        with _Im.open(fp) as im:
                            v = EMBED_SERVICE.embed_image(fp) if EMBED_SERVICE else None
                            if v is None:
                                continue
                            vecs.append(v.astype('float32'))
                    except Exception:
                        continue
            except Exception:
                pass
        if vecs:
            import numpy as _np
            vec = _np.mean(_np.stack(vecs, axis=0), axis=0).astype('float32')
        else:
            vec = np.zeros((EMBED_DIM,), dtype='float32')
        emb_path = DERIVED_DIR / 'video_embeddings' / f'{asset_id}.npy'
        emb_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(emb_path, vec)
        # Add to dedicated video index if available
        try:
            import app.metrics as m
            m.embeddings_generated.inc()
        except Exception:
            pass
        try:
            if VIDEO_INDEX_SINGLETON is not None:
                VIDEO_INDEX_SINGLETON.add([asset_id], vec.reshape(1,-1))
        except Exception:
            pass

    def _handle_video_scene_detect(self, session: Session, task: Task):
        payload = task.payload_json or {}
        asset_id = payload.get('asset_id')
        if not asset_id:
            return
        asset = session.get(Asset, asset_id)
        if not asset or not os.path.exists(asset.path):
            return
        min_len = float(getattr(self.settings, 'video_scene_min_sec', 1.0))
        scenes: list[tuple[float,float]] = []
        # Try pyscenedetect (optional dep)
        try:
            from scenedetect import detect, ContentDetector  # type: ignore
            detected = detect(video_path=asset.path, detector=ContentDetector())
            # detected is list of Scene objects with start/end timecodes
            for sc in detected:
                try:
                    s = float(sc[0].get_seconds())
                    e = float(sc[1].get_seconds())
                    if e - s >= min_len:
                        scenes.append((s,e))
                except Exception:
                    continue
        except Exception:
            # Fallback: split into fixed windows
            dur = float(asset.duration_sec or 0)
            if dur <= 0:
                dur = 10.0
            win = max(min_len, 3.0)
            t = 0.0
            while t < dur:
                e = min(dur, t + win)
                if e - t >= min_len:
                    scenes.append((t,e))
                t = e
        # Store segments
        from .db import VideoSegment
        for s,e in scenes:
            seg = VideoSegment(asset_id=asset_id, start_sec=s, end_sec=e)
            session.add(seg)
        session.commit()
        # Enqueue per-segment embedding jobs
        for seg in session.query(VideoSegment).filter_by(asset_id=asset_id).all():
            session.add(Task(type='video_segment_embed', priority=95, payload_json={'segment_id': seg.id}))
        session.commit()

    def _handle_video_segment_embed(self, session: Session, task: Task):
        payload = task.payload_json or {}
        seg_id = payload.get('segment_id')
        if not seg_id:
            return
        from .db import VideoSegment
        seg = session.get(VideoSegment, seg_id)
        if not seg:
            return
        # Extract a representative frame near segment midpoint for embedding
        a = session.get(Asset, seg.asset_id)
        if not a or not os.path.exists(a.path):
            return
        mid = max(0.0, (seg.start_sec + seg.end_sec) / 2.0)
        out_dir = DERIVED_DIR / 'video_frames' / f"asset_{a.id}_segments"
        out_dir.mkdir(parents=True, exist_ok=True)
        kf_path = out_dir / f"seg_{seg.id}_mid.jpg"
        try:
            import subprocess
            # extract single frame at time 'mid'
            cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y','-ss', str(mid), '-i', a.path, '-frames:v','1', str(kf_path)]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            seg.keyframe_path = str(kf_path)
        except Exception:
            # If ffmpeg missing, skip image extraction
            pass
        # Embed representative image if available, else zero vector
        vec = np.zeros((EMBED_DIM,), dtype='float32')
        if seg.keyframe_path and os.path.exists(seg.keyframe_path):
            try:
                v = EMBED_SERVICE.embed_image(seg.keyframe_path) if EMBED_SERVICE else None
                if v is not None:
                    vec = v.astype('float32')
            except Exception:
                pass
        emb_path = DERIVED_DIR / 'video_embeddings' / f'seg_{seg.id}.npy'
        np.save(emb_path, vec)
        seg.embedding_path = str(emb_path)
        session.commit()
        # Add to segment index
        try:
            if VIDEO_SEG_INDEX_SINGLETON is not None:
                VIDEO_SEG_INDEX_SINGLETON.add([seg.id], vec.reshape(1,-1))
        except Exception:
            pass

    # ---- Retry Classification & Backoff ----
    def _classify_permanent(self, exc: Exception) -> bool:
        transient = (TimeoutError, ConnectionError, OSError)
        return not isinstance(exc, transient)

    def _compute_backoff(self, retry_count: int):
        base = self.settings.retry_backoff_base_seconds
        cap = self.settings.retry_backoff_cap_seconds
        raw = base * (2 ** (max(0, retry_count-1)))
        raw = min(raw, cap)
        jitter = raw * random.uniform(0.2, 0.6)
        from datetime import timedelta
        return timedelta(seconds=raw + jitter)


