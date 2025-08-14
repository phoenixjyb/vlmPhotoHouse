import os, json, time, random, numpy as np
import threading
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, text, update
from .db import Task, Asset, Embedding, Caption, FaceDetection, Person
from .vector_index import InMemoryVectorIndex, FaissVectorIndex, EmbeddingService
from .config import get_settings
from pathlib import Path
from PIL import Image
import imagehash
from datetime import datetime, timedelta
from . import metrics as metrics_mod

EMBED_DIM = 512  # default; may be updated after loading real model
DERIVED_DIR = Path(os.getenv('DERIVED_PATH','./derived'))
( DERIVED_DIR / 'embeddings').mkdir(parents=True, exist_ok=True)
( DERIVED_DIR / 'thumbnails' / '256').mkdir(parents=True, exist_ok=True)
( DERIVED_DIR / 'thumbnails' / '1024').mkdir(parents=True, exist_ok=True)
( DERIVED_DIR / 'faces' / '256').mkdir(parents=True, exist_ok=True)
( DERIVED_DIR / 'face_embeddings').mkdir(parents=True, exist_ok=True)
( DERIVED_DIR / 'person_embeddings').mkdir(parents=True, exist_ok=True)
THUMB_SIZES = [256, 1024]
FACE_CLUSTER_DIST_THRESHOLD = 0.35  # default; overridden by settings

INDEX_SINGLETON: InMemoryVectorIndex | None = None
EMBED_SERVICE: EmbeddingService | None = None

class TaskExecutor:
    def __init__(self, session_factory, settings):
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
        global INDEX_SINGLETON, EMBED_SERVICE, EMBED_DIM, FACE_CLUSTER_DIST_THRESHOLD
        if EMBED_SERVICE is None:
            EMBED_SERVICE = EmbeddingService(self.settings.embed_model_image, self.settings.embed_model_text, EMBED_DIM, getattr(self.settings,'embed_device','cpu'))
            if EMBED_SERVICE.dim != EMBED_DIM:
                EMBED_DIM = EMBED_SERVICE.dim
        if INDEX_SINGLETON is None:
            if self.settings.vector_index_backend == 'faiss':
                INDEX_SINGLETON = FaissVectorIndex(EMBED_DIM, getattr(self.settings,'vector_index_path',None))  # type: ignore
            else:
                INDEX_SINGLETON = InMemoryVectorIndex(EMBED_DIM)
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
                elif task.type == 'person_recluster':
                    result = self._handle_person_recluster(session, task)
                    # persist summary into payload_json for status
                    try:
                        payload = task.payload_json or {}
                        payload['summary'] = result
                        task.payload_json = payload
                    except Exception:
                        pass
                elif task.type == 'dim_backfill':
                    self._handle_dim_backfill(session, task)
                elif task.type == 'phash':
                    self._handle_phash(session, task)
                elif task.type == 'fail_transient':
                    # Simulated transient failure for tests
                    raise OSError('Simulated transient failure')
                else:
                    raise ValueError(f'Unknown task type {task.type}')
                # Only mark done if not canceled mid-execution
                if task.state == 'running':
                    task.state = 'done'
                    task.finished_at = datetime.utcnow()
                # metrics: duration and processed counter
                try:
                    if task.started_at and task.finished_at:
                        metrics_mod.task_duration.labels(task.type).observe((task.finished_at - task.started_at).total_seconds())
                    metrics_mod.tasks_processed.labels(task.type, task.state).inc()
                except Exception:
                    pass
                session.commit()
                # metrics: duration & processed
                try:
                    duration = (task.finished_at - task.started_at).total_seconds() if task.finished_at and task.started_at else (time.time()-start_time)
                    metrics_mod.task_duration.labels(task.type).observe(duration)
                    metrics_mod.tasks_processed.labels(task.type, task.state).inc()
                except Exception:
                    pass
            except Exception as e:
                task.retry_count +=1
                task.last_error = str(e)
                is_permanent = self._classify_permanent(e)
                if task.retry_count >= self.settings.max_task_retries or is_permanent:
                    # move to dead-letter queue (distinct from generic failed)
                    task.state='dead'
                    task.finished_at = datetime.utcnow()
                else:
                    delay = self._compute_backoff(task.retry_count)
                    task.scheduled_at = datetime.utcnow() + delay
                    task.state='pending'
                session.commit()
                try:
                    metrics_mod.tasks_retried.labels(task.type).inc()
                    if task.state in ('failed', 'canceled', 'dead'):
                        metrics_mod.tasks_processed.labels(task.type, task.state).inc()
                except Exception:
                    pass
            return True

    def _compute_backoff(self, retry_count: int):
        """Compute jittered exponential backoff as timedelta.

        Uses base^retries capped, with +/- jitter fraction (default 25%).
        """
        s = self.settings
        base = getattr(s, 'retry_backoff_base_seconds', 2.0)
        cap = getattr(s, 'retry_backoff_cap_seconds', 300.0)
        jitter_fraction = getattr(s, 'retry_backoff_jitter', 0.25)
        if base <= 0:
            return timedelta(seconds=0)
        raw = base * (2 ** (max(0, retry_count-1)))
        raw = min(raw, cap)
        jitter = raw * random.uniform(-jitter_fraction, jitter_fraction) if raw > 0 else 0
        return timedelta(seconds=max(0.0, raw + jitter))

    def start_workers(self, n: int):
        if self._workers:
            return
        self._stop_event.clear()
        def loop():
            while not self._stop_event.is_set():
                worked = self.run_once()
                time.sleep(self.settings.worker_poll_interval if not worked else 0.01)
        for _ in range(max(1, n)):
            t = threading.Thread(target=loop, daemon=True)
            t.start()
            self._workers.append(t)

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
                im.thumbnail((size, size))
                im.convert('RGB').save(out_path, 'JPEG', quality=85)

    def _handle_caption(self, session: Session, task: Task):
        asset_id = task.payload_json['asset_id']
        asset = session.get(Asset, asset_id)
        if not asset:
            raise ValueError('asset missing')
        # Simple heuristic stub caption: based on filename tokens
        filename = Path(asset.path).name
        base = os.path.splitext(filename)[0]
        tokens = [t for t in base.replace('-', ' ').replace('_',' ').split() if t]
        if not tokens:
            text = 'Photo'
        else:
            text = ' '.join(tokens[:8])
        existing = session.get(Caption, asset_id)
        if existing:
            return
        cap = Caption(asset_id=asset_id, text=text, model='stub-blip2', user_edited=False)
        session.add(cap)
        session.commit()
        return cap

    def _handle_face(self, session: Session, task: Task):
        payload = task.payload_json or {}
        asset_id = payload.get('asset_id')
        asset = session.get(Asset, asset_id)
        if not asset:
            raise ValueError(f'Asset {asset_id} not found for face task')
        src = Path(asset.path)
        if not src.exists():
            raise FileNotFoundError(src)
        faces = session.query(FaceDetection).filter(FaceDetection.asset_id==asset.id).all()
        if not faces:
            # Run detection provider
            try:
                from .face_detection_service import get_face_detection_provider
                provider = get_face_detection_provider()
                from PIL import Image as _Im
                import time as _t
                t0_det = _t.time()
                with _Im.open(src) as im_det:
                    dets = provider.detect(im_det.convert('RGB'))
                try:  # pragma: no cover
                    import app.metrics as m
                    prov_name = type(provider).__name__.replace('DetectionProvider','').lower()
                    m.face_detection_inference_seconds.labels(prov_name or 'unknown').observe(_t.time()-t0_det)
                except Exception:
                    pass
            except Exception:
                # Fallback: single centered box
                from PIL import Image as _Im
                with _Im.open(src) as im_det:
                    w,h = im_det.size
                dets = []
                size = min(w,h)*0.4
                dets.append(type('DF',(),{'x':(w-size)/2,'y':(h-size)/2,'w':size,'h':size})())
            for d in dets:
                face = FaceDetection(asset_id=asset.id, bbox_x=float(d.x), bbox_y=float(d.y), bbox_w=float(d.w), bbox_h=float(d.h), embedding_path=None)
                session.add(face)
            session.flush()
            faces = session.query(FaceDetection).filter(FaceDetection.asset_id==asset.id).all()
        # Generate / ensure crops
        out_dir = DERIVED_DIR / 'faces' / '256'
        with Image.open(src) as im:
            w, h = im.size
            for face in faces:
                crop_path = out_dir / f"{face.id}.jpg"
                if crop_path.exists():
                    continue
                x1 = int(max(0, face.bbox_x))
                y1 = int(max(0, face.bbox_y))
                x2 = int(min(w, face.bbox_x + face.bbox_w))
                y2 = int(min(h, face.bbox_y + face.bbox_h))
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
        pending_cluster = session.query(Task).filter(Task.type=='person_cluster', Task.state=='pending').first()
        if not pending_cluster:
            unassigned_faces = session.query(FaceDetection).filter(FaceDetection.person_id==None, FaceDetection.embedding_path!=None).count()
            if unassigned_faces >=5:
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
                w, h = im.size
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
                ph = imagehash.phash(im)
            asset.perceptual_hash = ph.__str__()
            session.commit()
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


