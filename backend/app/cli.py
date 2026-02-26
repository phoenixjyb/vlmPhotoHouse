from __future__ import annotations

import os
import typer
from typing import List, Optional
from sqlalchemy import create_engine, func, or_
from sqlalchemy.orm import sessionmaker

from . import db
from .config import get_settings
from . import ingest as ingest_mod
from .face_assignment_audit import record_face_assignment_event

app = typer.Typer(add_completion=False, help="VLM Photo Engine CLI (dev)")


def _session_factory():
    settings = get_settings()
    engine = create_engine(settings.database_url, future=True, echo=False)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, SessionLocal


@app.command("init-db")
def init_db() -> None:
    """Create database tables (no Alembic)."""
    engine, _ = _session_factory()
    db.Base.metadata.create_all(bind=engine)
    typer.echo("DB initialized (create_all)")


@app.command("ingest-scan")
def ingest_scan(paths: List[str] = typer.Argument(..., help="Directories to scan")) -> None:
    """Scan directories and populate assets (hash + EXIF)."""
    engine, SessionLocal = _session_factory()
    db.Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        result = ingest_mod.ingest_paths(session, paths)
        typer.echo(f"Ingest complete: {result}")


@app.command("ingest-status")
def ingest_status(
    paths: List[str] = typer.Argument(..., help="Directories to summarize (progress by prefix)"),
    scan_fs: bool = typer.Option(False, "--scan-fs", help="Also count files on disk (fast; only new files are hashed on ingest)"),
    preview_limit: int = typer.Option(10, min=0, help="Show up to N sample files not yet ingested (filesystem preview)"),
) -> None:
    """Summarize ingestion/progress for one or more folders.

    Reports counts for assets under each path prefix and how many are missing embeddings/captions.
    """
    from pathlib import Path as _Path
    from sqlalchemy import func as _f
    from .db import Asset, Embedding, Caption, Task
    settings = get_settings()
    _, SessionLocal = _session_factory()
    with SessionLocal() as session:
        # Allowed extensions (mirror ingest)
        allowed_ext = set(ingest_mod.SUPPORTED_IMAGE_EXT)
        if getattr(settings, 'video_enabled', False):
            try:
                vids = [e.strip().lower() for e in settings.video_extensions.split(',') if e.strip()]
                allowed_ext.update(vids)
            except Exception:
                pass
        for root in paths:
            prefix = str(_Path(root).resolve())
            like = prefix + '%'
            total_assets = session.query(_f.count(Asset.id)).filter(Asset.path.like(like)).scalar() or 0
            # Missing embeddings:
            # - image assets: missing modality='image' embedding row
            # - video assets: missing completed video_embed task
            sub_img_emb = session.query(Embedding.asset_id).filter(Embedding.modality == 'image')
            missing_img_embed = (
                session.query(_f.count(Asset.id))
                .filter(Asset.path.like(like))
                .filter(Asset.mime.like('image/%'))
                .filter(~Asset.id.in_(sub_img_emb))
                .scalar()
                or 0
            )
            video_asset_ids = {
                aid
                for (aid,) in session.query(Asset.id)
                .filter(Asset.path.like(like))
                .filter(Asset.mime.like('video/%'))
                .all()
            }
            done_video_embed_ids: set[int] = set()
            if video_asset_ids:
                rows = (
                    session.query(Task.payload_json)
                    .filter(Task.type == 'video_embed')
                    .filter(Task.state.in_(['done', 'finished']))
                    .all()
                )
                for (payload,) in rows:
                    if isinstance(payload, dict):
                        vid = payload.get('asset_id')
                        if isinstance(vid, int) and vid in video_asset_ids:
                            done_video_embed_ids.add(vid)
            missing_video_embed = max(0, len(video_asset_ids) - len(done_video_embed_ids))
            missing_embed = missing_img_embed + missing_video_embed
            # Missing caption
            sub_cap = session.query(Caption.asset_id)
            missing_caption = session.query(_f.count(Asset.id)).filter(Asset.path.like(like)).filter(~Asset.id.in_(sub_cap)).scalar() or 0
            fs_files = None
            sample_new: list[str] = []
            if scan_fs:
                try:
                    fs_files = 0
                    for p in _Path(prefix).rglob('*'):
                        if p.is_file() and p.suffix.lower() in allowed_ext:
                            fs_files += 1
                            if len(sample_new) < preview_limit:
                                # Only show preview of not-yet-ingested candidates
                                # Avoid hashing; rely on path uniqueness
                                exists = session.query(Asset.id).filter(Asset.path == str(p.resolve())).first()
                                if not exists:
                                    sample_new.append(str(p.resolve()))
                except Exception:
                    pass
            typer.echo(f"\n[{prefix}]")
            typer.echo(f"  assets_in_db:       {total_assets}")
            typer.echo(f"  missing_embedding:  {missing_embed}")
            typer.echo(f"  missing_img_embed:  {missing_img_embed}")
            typer.echo(f"  missing_vid_embed:  {missing_video_embed}")
            typer.echo(f"  missing_caption:    {missing_caption}")
            if fs_files is not None:
                to_ingest = max(0, fs_files - total_assets)
                typer.echo(f"  files_on_disk:      {fs_files}")
                typer.echo(f"  not_ingested(yet):  {to_ingest}")
                try:
                    pct = 0.0 if fs_files == 0 else (total_assets / fs_files) * 100.0
                    typer.echo(f"  ingested_pct:       {pct:.1f}%")
                except Exception:
                    pass
                if sample_new:
                    typer.echo("  sample_new:")
                    for s in sample_new:
                        typer.echo(f"    - {s}")


@app.command("ingest-watch")
def ingest_watch(
    paths: List[str] = typer.Argument(..., help="Directories to poll for new files"),
    interval: float = typer.Option(30.0, help="Polling interval in seconds"),
) -> None:
    """Continuously poll and ingest new files.

    Safe to run repeatedly; existing assets are skipped by path before hashing.
    """
    import time as _time
    engine, SessionLocal = _session_factory()
    db.Base.metadata.create_all(bind=engine)
    typer.echo(f"Polling every {interval:.1f}s. Press Ctrl+C to stop.")
    try:
        cumulative = 0
        while True:
            start = _time.time()
            with SessionLocal() as session:
                result = ingest_mod.ingest_paths(session, paths)
                cumulative += int(result.get('new_assets', 0))
                typer.echo(
                    f"[{_time.strftime('%H:%M:%S')}] new_assets={result['new_assets']} "
                    f"skipped={result['skipped']} elapsed={result['elapsed_sec']}s total_ingested={cumulative}"
                )
            sleep_left = max(0.0, interval - (_time.time() - start))
            _time.sleep(sleep_left)
    except KeyboardInterrupt:
        typer.echo("Stopped.")


@app.command("gps-backfill")
def gps_backfill(
    root: Optional[str] = typer.Option(None, help="Optional root path filter (e.g. E:\\01_INCOMING)"),
    limit: int = typer.Option(0, min=0, help="Max assets to scan (0 = all matching assets)"),
    force: bool = typer.Option(False, help="Recompute even when GPS already exists"),
    include_images: bool = typer.Option(True, help="Process image assets"),
    include_videos: bool = typer.Option(True, help="Process video assets"),
    ffprobe_timeout: int = typer.Option(12, min=1, max=60, help="ffprobe timeout per video in seconds"),
    commit_every: int = typer.Option(100, min=1, max=2000, help="Commit cadence"),
) -> None:
    """Backfill GPS latitude/longitude from image EXIF and video metadata tags."""
    from pathlib import Path as _Path
    from .db import Asset
    from .gps_utils import read_image_gps, probe_video_metadata

    settings = get_settings()
    _, SessionLocal = _session_factory()

    video_exts: set[str] = set()
    try:
        video_exts = {e.strip().lower() for e in settings.video_extensions.split(',') if e.strip()}
    except Exception:
        video_exts = {'.mp4', '.mov', '.mkv', '.avi', '.m4v', '.webm'}

    with SessionLocal() as session:
        q = session.query(Asset).order_by(Asset.id.asc())
        if root:
            prefix = str(_Path(root).resolve())
            q = q.filter(Asset.path.like(prefix + '%'))
        if not force:
            q = q.filter((Asset.gps_lat == None) | (Asset.gps_lon == None))

        scanned = 0
        skipped_missing_file = 0
        skipped_type = 0
        updated = 0
        image_updates = 0
        video_updates = 0

        for asset in q:
            if limit and scanned >= limit:
                break
            scanned += 1

            p = _Path(asset.path)
            if not p.exists():
                skipped_missing_file += 1
                continue

            mime = (asset.mime or '').lower()
            ext = p.suffix.lower()
            is_image = mime.startswith('image/') or ext in ingest_mod.SUPPORTED_IMAGE_EXT
            is_video = mime.startswith('video/') or ext in video_exts

            lat = lon = None
            if is_image and include_images:
                gps = read_image_gps(p)
                if gps is not None:
                    lat, lon = gps
            elif is_video and include_videos:
                meta = probe_video_metadata(p, timeout_sec=ffprobe_timeout)
                if meta.get('gps_lat') is not None and meta.get('gps_lon') is not None:
                    lat = float(meta['gps_lat'])
                    lon = float(meta['gps_lon'])
            else:
                skipped_type += 1
                continue

            if lat is not None and lon is not None:
                asset.gps_lat = lat
                asset.gps_lon = lon
                updated += 1
                if is_image:
                    image_updates += 1
                elif is_video:
                    video_updates += 1

            if scanned % commit_every == 0:
                session.commit()
                typer.echo(
                    f"progress scanned={scanned} updated={updated} "
                    f"(images={image_updates}, videos={video_updates}) "
                    f"missing_file={skipped_missing_file}"
                )

        session.commit()
        typer.echo("gps-backfill done")
        typer.echo(
            f"scanned={scanned} updated={updated} "
            f"image_updates={image_updates} video_updates={video_updates} "
            f"skipped_missing_file={skipped_missing_file} skipped_type={skipped_type}"
        )


@app.command("faces-redetect-enqueue")
def faces_redetect_enqueue(
    root: Optional[str] = typer.Option(None, help="Optional asset path prefix filter (e.g. E:\\01_INCOMING)"),
    limit: int = typer.Option(0, min=0, help="Max tasks to enqueue (0 = all matching assets)"),
    only_without_faces: bool = typer.Option(False, help="Only enqueue assets currently with zero face detections"),
    skip_if_pending: bool = typer.Option(True, help="Skip assets that already have pending/running face task"),
    priority: int = typer.Option(118, min=1, max=1000, help="Task priority for enqueued face tasks"),
    dedupe_iou: float = typer.Option(0.60, min=0.0, max=1.0, help="IoU threshold used by task to avoid duplicate boxes"),
    commit_every: int = typer.Option(500, min=50, max=5000, help="Commit cadence"),
) -> None:
    """Enqueue force redetect face tasks for image assets.

    Uses force_redetect + supplement_only mode so existing labeled faces are preserved,
    and only newly discovered non-overlapping detections are added.
    """
    from pathlib import Path as _Path
    from .db import Asset, FaceDetection, Task

    _, SessionLocal = _session_factory()
    with SessionLocal() as session:
        q = session.query(Asset.id, Asset.path).filter(Asset.mime.like('image/%')).order_by(Asset.id.asc())
        if root:
            prefix = str(_Path(root).resolve())
            q = q.filter(Asset.path.like(prefix + '%'))

        scanned = 0
        enqueued = 0
        skipped_has_faces = 0
        skipped_pending = 0

        for asset_id, _path in q:
            if limit and enqueued >= limit:
                break
            scanned += 1

            if only_without_faces:
                has_face = session.query(FaceDetection.id).filter(FaceDetection.asset_id == asset_id).first()
                if has_face:
                    skipped_has_faces += 1
                    continue

            if skip_if_pending:
                existing_task = (
                    session.query(Task.id)
                    .filter(Task.type == 'face')
                    .filter(Task.state.in_(['pending', 'running']))
                    .filter(Task.payload_json['asset_id'].as_integer() == asset_id)
                    .first()
                )
                if existing_task:
                    skipped_pending += 1
                    continue

            payload = {
                'asset_id': int(asset_id),
                'force_redetect': True,
                'supplement_only': True,
                'dedupe_iou': float(dedupe_iou),
            }
            session.add(Task(type='face', priority=priority, payload_json=payload))
            enqueued += 1

            if enqueued % commit_every == 0:
                session.commit()
                typer.echo(
                    f"progress scanned={scanned} enqueued={enqueued} "
                    f"skipped_pending={skipped_pending} skipped_has_faces={skipped_has_faces}"
                )

        session.commit()
        typer.echo("faces-redetect-enqueue done")
        typer.echo(
            f"scanned={scanned} enqueued={enqueued} "
            f"skipped_pending={skipped_pending} skipped_has_faces={skipped_has_faces} "
            f"limit={limit} root={root or '(all)'} only_without_faces={only_without_faces}"
        )


@app.command("faces-auto-assign")
def faces_auto_assign(
    score_threshold: float = typer.Option(0.95, min=0.0, max=1.0, help="Minimum cosine score to accept assignment"),
    margin: float = typer.Option(0.01, min=0.0, max=1.0, help="Min gap between top-1 and top-2 score"),
    min_ref_faces: int = typer.Option(10, min=2, help="Minimum labeled faces per person to build a centroid"),
    assign_all: bool = typer.Option(False, help="Assign every evaluated unassigned face to top-1 candidate (ignores threshold/margin)"),
    reference_manual_only: bool = typer.Option(True, help="Use only manually labeled faces as centroid reference"),
    include_dnn_assigned: bool = typer.Option(False, help="Also re-evaluate currently DNN-labeled faces (manual labels are never touched)"),
    root: Optional[str] = typer.Option(None, help="Optional asset path prefix filter"),
    limit: int = typer.Option(0, min=0, help="Max unassigned faces to evaluate (0 = all)"),
    name: Optional[List[str]] = typer.Option(None, "--name", help="Restrict target people names (repeat option)"),
    apply: bool = typer.Option(False, help="Persist assignments (default is dry-run)"),
    commit_every: int = typer.Option(200, min=20, max=2000, help="Commit cadence when --apply is enabled"),
) -> None:
    """Auto-assign unassigned faces to named persons using embedding centroid matching."""
    from pathlib import Path as _Path
    import numpy as _np
    from collections import Counter as _Counter, defaultdict as _dd
    from .db import Person, FaceDetection, Asset

    _, SessionLocal = _session_factory()

    data_root = _Path(os.getenv("VLM_DATA_ROOT", r"E:\VLM_DATA"))

    def _resolve_emb_path(ep: str) -> _Path:
        p = _Path(ep)
        if p.is_absolute():
            return p
        ep_norm = ep.replace("\\", "/")
        if ep_norm.lower().startswith("derived/"):
            return data_root / ep_norm
        return _Path(ep)

    target_names = {n.strip().lower() for n in (name or []) if n and n.strip()}

    with SessionLocal() as session:
        # Build reference vectors from already-assigned named faces.
        ref_q = (
            session.query(Person.id, Person.display_name, FaceDetection.embedding_path)
            .join(FaceDetection, FaceDetection.person_id == Person.id)
            .filter(Person.display_name != None)
            .filter(func.trim(Person.display_name) != "")
            .filter(FaceDetection.embedding_path != None)
        )
        if reference_manual_only:
            ref_q = ref_q.filter(FaceDetection.label_source == 'manual')
        ref_rows = ref_q.all()

        by_person: dict[tuple[int, str], list[_np.ndarray]] = _dd(list)
        missing_ref_emb = 0
        for pid, pname, ep in ref_rows:
            if not ep:
                continue
            name_norm = (pname or "").strip()
            if not name_norm:
                continue
            if target_names and name_norm.lower() not in target_names:
                continue
            p = _resolve_emb_path(str(ep))
            if not p.exists():
                missing_ref_emb += 1
                continue
            try:
                v = _np.asarray(_np.load(p), dtype="float32").reshape(-1)
                if v.size == 0:
                    continue
                n = float(_np.linalg.norm(v))
                if n > 0:
                    v = v / n
                by_person[(int(pid), name_norm)].append(v)
            except Exception:
                continue

        centroids: list[tuple[int, str, int, int, _np.ndarray]] = []
        for (pid, pname), vecs in by_person.items():
            if len(vecs) < min_ref_faces:
                continue
            dims = _Counter(int(v.shape[0]) for v in vecs if v.ndim == 1 and v.size > 0)
            if not dims:
                continue
            target_dim, _ = dims.most_common(1)[0]
            vecs_same_dim = [v for v in vecs if int(v.shape[0]) == target_dim]
            if len(vecs_same_dim) < min_ref_faces:
                continue
            c = _np.mean(_np.stack(vecs_same_dim), axis=0).astype("float32")
            n = float(_np.linalg.norm(c))
            if n > 0:
                c = c / n
            centroids.append((pid, pname, len(vecs_same_dim), target_dim, c))

        if not centroids:
            typer.echo(
                f"No eligible reference persons (min_ref_faces={min_ref_faces}, name_filter={sorted(target_names) if target_names else 'none'})"
            )
            return

        # Query candidate faces
        q = (
            session.query(
                FaceDetection.id,
                FaceDetection.embedding_path,
                Asset.path,
                FaceDetection.person_id,
                FaceDetection.label_source,
            )
            .join(Asset, Asset.id == FaceDetection.asset_id)
            .filter(FaceDetection.embedding_path != None)
            .order_by(FaceDetection.id.asc())
        )
        if include_dnn_assigned:
            q = q.filter(or_(FaceDetection.person_id == None, FaceDetection.label_source == 'dnn'))
        else:
            q = q.filter(FaceDetection.person_id == None)
        if root:
            prefix = str(_Path(root).resolve())
            q = q.filter(Asset.path.like(prefix + "%"))
        rows = q.all()
        if limit and limit > 0:
            rows = rows[:limit]

        scanned = 0
        matched = 0
        changed = 0
        missing_face_emb = 0
        affected: set[int] = set()
        per_person: dict[str, int] = _dd(int)
        preview: list[tuple[int, int, str, float, float]] = []

        for fid, ep, _asset_path, current_person_id, current_label_source in rows:
            scanned += 1
            p = _resolve_emb_path(str(ep))
            if not p.exists():
                missing_face_emb += 1
                continue
            try:
                v = _np.asarray(_np.load(p), dtype="float32").reshape(-1)
                if v.size == 0:
                    continue
                n = float(_np.linalg.norm(v))
                if n > 0:
                    v = v / n
            except Exception:
                continue
            eligible = [(pid, pname, c) for pid, pname, _nref, dim, c in centroids if int(v.shape[0]) == int(dim)]
            if not eligible:
                continue
            scores = sorted(
                [(float(_np.dot(v, c)), pid, pname) for pid, pname, c in eligible],
                reverse=True,
            )
            if not scores:
                continue
            best_score, best_pid, best_name = scores[0]
            second_score = scores[1][0] if len(scores) > 1 else -1.0
            gap = best_score - second_score
            if not assign_all and (best_score < score_threshold or gap < margin):
                continue
            current_pid_int = int(current_person_id) if current_person_id is not None else None
            new_pid_int = int(best_pid)
            # For full-batch refresh mode, skip no-op candidates that would keep same DNN label.
            if include_dnn_assigned and current_label_source == 'dnn' and current_pid_int == new_pid_int:
                continue
            matched += 1
            per_person[best_name] += 1
            affected.add(new_pid_int)
            if current_pid_int is not None:
                affected.add(current_pid_int)
            if len(preview) < 25:
                preview.append((int(fid), new_pid_int, best_name, float(best_score), float(gap)))
            if apply:
                face = session.get(FaceDetection, int(fid))
                if face is not None and (face.person_id is None or getattr(face, 'label_source', None) == 'dnn'):
                    old_person_id = int(face.person_id) if face.person_id is not None else None
                    old_label_source = getattr(face, 'label_source', None)
                    old_label_score = getattr(face, 'label_score', None)
                    face.person_id = new_pid_int
                    face.label_source = 'dnn'
                    face.label_score = float(best_score)
                    if record_face_assignment_event(
                        session,
                        face=face,
                        source='dnn',
                        reason='cli.faces-auto-assign',
                        actor='cli',
                        old_person_id=old_person_id,
                        new_person_id=new_pid_int,
                        old_label_source=old_label_source,
                        new_label_source='dnn',
                        old_label_score=float(old_label_score) if old_label_score is not None else None,
                        new_label_score=float(best_score),
                    ):
                        changed += 1
                if matched % commit_every == 0:
                    session.commit()

        if apply:
            # Recompute counts for touched persons
            # SessionLocal uses autoflush=False; flush person_id updates before counting.
            session.flush()
            for pid in sorted(affected):
                cnt = (
                    session.query(func.count(FaceDetection.id))
                    .filter(FaceDetection.person_id == pid)
                    .scalar()
                    or 0
                )
                p = session.get(Person, pid)
                if p is not None:
                    p.face_count = int(cnt)
            session.commit()

        mode = "APPLY" if apply else "DRY-RUN"
        typer.echo(f"faces-auto-assign ({mode})")
        typer.echo(
            f"scanned={scanned} matched={matched} changed={changed if apply else 'n/a'} "
            f"missing_face_emb={missing_face_emb} missing_ref_emb={missing_ref_emb} "
            f"score_threshold={score_threshold:.3f} margin={margin:.3f} min_ref_faces={min_ref_faces} "
            f"assign_all={assign_all} reference_manual_only={reference_manual_only} "
            f"include_dnn_assigned={include_dnn_assigned}"
        )
        typer.echo(f"reference_persons={[(pid, name, nref, dim) for pid, name, nref, dim, _ in centroids]}")
        typer.echo(f"matched_per_person={dict(sorted(per_person.items()))}")
        if preview:
            typer.echo("preview (face_id -> person):")
            for fid, pid, pname, s, g in preview:
                typer.echo(f"  {fid} -> {pid} ({pname}) score={s:.4f} gap={g:.4f}")


@app.command("list-dead")
def list_dead(page: int = 1, page_size: int = 50) -> None:
    """List dead-letter tasks."""
    _, SessionLocal = _session_factory()
    from .db import Task
    with SessionLocal() as session:
        q = session.query(Task).filter(Task.state == 'dead')
        total = q.count()
        items = q.order_by(Task.id.desc()).offset((page-1)*page_size).limit(page_size).all()
        typer.echo(f"total={total}")
        for t in items:
            typer.echo(f"id={t.id} type={t.type} retry={t.retry_count} err={t.last_error}")


@app.command("requeue")
def requeue(task_id: int) -> None:
    """Requeue a dead/failed/canceled task."""
    _, SessionLocal = _session_factory()
    from .db import Task
    with SessionLocal() as session:
        task = session.get(Task, task_id)
        if not task:
            typer.echo("Task not found", err=True)
            raise typer.Exit(1)
        if task.state not in ('dead', 'failed', 'canceled'):
            typer.echo(f"Cannot requeue from state {task.state}", err=True)
            raise typer.Exit(2)
        task.state = 'pending'
        task.retry_count = 0
        task.started_at = None
        task.finished_at = None
        task.last_error = None
        task.scheduled_at = func.now()
        session.commit()
        typer.echo(f"Requeued task {task.id}")


@app.command("ping")
def ping() -> None:
    """Simple heartbeat to verify CLI wiring."""
    typer.echo("cli-ok")

@app.command("captions-clean-stubs")
def captions_clean_stubs(
    root: Optional[str] = typer.Option(None, help="Optional asset path prefix filter (e.g. E:\\01_INCOMING)"),
    limit: int = typer.Option(0, min=0, help="Max assets to scan (0 = all matching assets)"),
    enqueue_missing: bool = typer.Option(True, help="Enqueue caption regeneration when no non-stub caption remains"),
    force_regen: bool = typer.Option(True, help="Enqueue caption tasks with force=true"),
    profile: str = typer.Option('balanced', help="Caption profile hint for newly enqueued tasks"),
    apply: bool = typer.Option(True, help="Apply changes (set false for dry-run)"),
    commit_every: int = typer.Option(300, min=50, max=5000, help="Commit cadence"),
) -> None:
    """Remove non-edited stub captions and backfill missing real captions."""
    from pathlib import Path as _Path
    from .db import Asset, Caption, Task

    def _is_stub_caption(c: Caption) -> bool:
        if bool(c.user_edited):
            return False
        model = (c.model or '').strip().lower()
        if model.startswith('stub'):
            return True
        if model in ('unknown',):
            txt = (c.text or '').strip().lower()
            if txt in ('photo', 'image'):
                return True
        return False

    _, SessionLocal = _session_factory()
    with SessionLocal() as session:
        q = session.query(Asset.id, Asset.path).order_by(Asset.id.asc())
        if root:
            prefix = str(_Path(root).resolve())
            q = q.filter(Asset.path.like(prefix + '%'))

        scanned = 0
        removed_stub = 0
        enqueued = 0
        assets_with_stub = 0
        assets_now_missing_real = 0
        pending_skips = 0

        for asset_id, _path in q:
            if limit and scanned >= limit:
                break
            scanned += 1

            caps = session.query(Caption).filter(Caption.asset_id == asset_id).order_by(Caption.created_at.asc()).all()
            if not caps:
                has_real = False
                stub_caps = []
            else:
                stub_caps = [c for c in caps if _is_stub_caption(c)]
                has_real = any((not _is_stub_caption(c)) for c in caps)

            if stub_caps:
                assets_with_stub += 1
                if apply:
                    for c in stub_caps:
                        session.delete(c)
                removed_stub += len(stub_caps)

            # After deletion, there may be no caption left or only deleted stubs.
            if (not has_real) and enqueue_missing:
                assets_now_missing_real += 1
                existing_task = (
                    session.query(Task.id)
                    .filter(Task.type == 'caption')
                    .filter(Task.state.in_(['pending', 'running']))
                    .filter(Task.payload_json['asset_id'].as_integer() == asset_id)
                    .first()
                )
                if existing_task:
                    pending_skips += 1
                else:
                    if apply:
                        payload = {'asset_id': int(asset_id), 'force': bool(force_regen), 'profile': profile}
                        session.add(Task(type='caption', priority=110, payload_json=payload))
                    enqueued += 1

            if apply and scanned % commit_every == 0:
                session.commit()
                typer.echo(
                    f"progress scanned={scanned} removed_stub={removed_stub} enqueued={enqueued} "
                    f"assets_with_stub={assets_with_stub} missing_real={assets_now_missing_real}"
                )

        if apply:
            # keep summary fields accurate for touched assets
            # lightweight full recompute is acceptable for offline cleanup runs
            for (aid,) in session.query(Asset.id).all():
                cnt = session.query(func.count(Caption.id)).filter(Caption.asset_id == aid, Caption.superseded == False).scalar() or 0
                a = session.get(Asset, int(aid))
                if a is not None:
                    a.caption_variant_count = int(cnt)
                    a.caption_processed = bool(cnt > 0)
            session.commit()

        mode = "APPLY" if apply else "DRY-RUN"
        typer.echo(f"captions-clean-stubs ({mode})")
        typer.echo(
            f"scanned={scanned} assets_with_stub={assets_with_stub} removed_stub={removed_stub} "
            f"assets_missing_real={assets_now_missing_real} enqueued={enqueued} pending_skips={pending_skips} "
            f"root={root or '(all)'} limit={limit} force_regen={force_regen}"
        )

@app.command("captions-backfill")
def captions_backfill(
    profile: str = typer.Option('balanced', help="Caption profile hint (fast|balanced|quality) recorded only; current providers handled via env"),
    max_variants: int = typer.Option(3, help="Desired variant target per asset (won't overwrite user_edited)"),
    limit: int = typer.Option(500, help="Max assets to enqueue this run"),
    force: bool = typer.Option(False, help="Force enqueue even if variants already at/above target (respects user_edited preservation)"),
) -> None:
    """Enqueue caption tasks for assets missing captions or below variant target.

    This does NOT generate immediately; it schedules tasks respecting existing
    user-edited captions and variant caps. Newly added status fields on assets
    will be updated by task handler (future enhancement).
    """
    from .db import Asset, Caption, Task
    engine, SessionLocal = _session_factory()
    with SessionLocal() as session:
        q = session.query(Asset.id).order_by(Asset.id.asc())
        enqueued = 0
        scanned = 0
        for (asset_id,) in q:
            if enqueued >= limit:
                break
            scanned += 1
            caps = session.query(Caption).filter(Caption.asset_id==asset_id).order_by(Caption.created_at.asc()).all()
            user_edited_count = sum(1 for c in caps if c.user_edited)
            
            # Skip if we have enough variants AND not forcing
            if not force and len(caps) >= max_variants:
                continue
                
            # When forcing, skip only if there are user-edited captions (preserve user work)
            if force and user_edited_count > 0:
                continue
                
            # Avoid duplicate pending caption task
            existing_task = session.query(Task).filter(Task.type=='caption', Task.state.in_(['pending','running']), Task.payload_json['asset_id'].as_integer()==asset_id).first()
            if existing_task:
                continue
            payload = {'asset_id': asset_id, 'force': force, 'profile': profile}
            session.add(Task(type='caption', priority=110, payload_json=payload))
            enqueued += 1
        session.commit()
        typer.echo(f"scanned={scanned} enqueued={enqueued} limit={limit} target_variants={max_variants} profile={profile}")


@app.command("captions-tags-backfill")
def captions_tags_backfill(
    root: Optional[str] = typer.Option(None, help="Optional asset path prefix filter (e.g. E:\\01_INCOMING)"),
    limit: int = typer.Option(0, min=0, help="Max assets to scan (0 = all matching assets)"),
    max_tags: int = typer.Option(8, min=1, max=32, help="Max derived tags per asset"),
    source_model_contains: Optional[str] = typer.Option("qwen", help="Caption model substring filter (default: qwen)"),
    tag_type: str = typer.Option("caption-auto", help="Type label used for newly-created tags"),
    apply: bool = typer.Option(True, help="Apply changes (set false for dry-run)"),
    commit_every: int = typer.Option(200, min=20, max=5000, help="Commit cadence"),
) -> None:
    """Derive tags from captions and upsert them into asset_tags."""
    from pathlib import Path as _Path
    from .dependencies import ensure_db
    from .db import Asset, Caption
    from .tagging import extract_caption_tag_candidates, upsert_asset_tags

    ensure_db()

    src_filter = (source_model_contains or "").strip().lower()
    bad_texts = {
        "caption service unavailable",
        "caption service connection failed",
        "caption generation error",
        "caption generation failed",
    }

    _, SessionLocal = _session_factory()
    with SessionLocal() as session:
        q = session.query(Asset.id, Asset.path).order_by(Asset.id.asc())
        if root:
            prefix = str(_Path(root).resolve())
            q = q.filter(Asset.path.like(prefix + "%"))

        scanned = 0
        matched_caption = 0
        no_caption = 0
        no_tags = 0
        assets_updated = 0
        links_added = 0

        for asset_id, _path in q:
            if limit and scanned >= limit:
                break
            scanned += 1

            caps = (
                session.query(Caption)
                .filter(Caption.asset_id == asset_id)
                .order_by(Caption.user_edited.desc(), Caption.created_at.desc(), Caption.id.desc())
                .all()
            )
            if not caps:
                no_caption += 1
                continue

            source_cap = None
            for c in caps:
                txt = (c.text or "").strip()
                mdl = (c.model or "").strip().lower()
                if not txt:
                    continue
                if txt.lower() in bad_texts:
                    continue
                if "stub" in mdl:
                    continue
                if src_filter and src_filter not in mdl:
                    continue
                source_cap = c
                break

            if source_cap is None:
                no_caption += 1
                continue

            matched_caption += 1
            derived_candidates = extract_caption_tag_candidates(source_cap.text or "", max_tags=max_tags)
            if not derived_candidates:
                no_tags += 1
                continue

            derived = [str(x.get("name") or "").strip() for x in derived_candidates]
            derived = [x for x in derived if x]
            if not derived:
                no_tags += 1
                continue
            name_types = {
                str(x.get("name") or "").strip(): str(x.get("type") or tag_type).strip()
                for x in derived_candidates
                if str(x.get("name") or "").strip()
            }
            score_by_name = {
                str(x.get("name") or "").strip(): float(x.get("score") or 0.0)
                for x in derived_candidates
                if str(x.get("name") or "").strip()
            }
            if apply:
                added = upsert_asset_tags(
                    session,
                    asset_id=int(asset_id),
                    names=derived,
                    tag_type=tag_type,
                    name_types=name_types,
                    source='cap',
                    source_model=source_cap.model,
                    score_by_name=score_by_name,
                )
                if added:
                    assets_updated += 1
                    links_added += len(added)
            else:
                assets_updated += 1
                links_added += len(derived)

            if apply and scanned % commit_every == 0:
                session.commit()
                typer.echo(
                    f"progress scanned={scanned} matched_caption={matched_caption} "
                    f"assets_updated={assets_updated} links_added={links_added}"
                )

        if apply:
            session.commit()

        mode = "APPLY" if apply else "DRY-RUN"
        typer.echo(f"captions-tags-backfill ({mode})")
        typer.echo(
            f"scanned={scanned} matched_caption={matched_caption} no_caption={no_caption} "
            f"no_tags={no_tags} assets_updated={assets_updated} links_added={links_added} "
            f"max_tags={max_tags} tag_type={tag_type} "
            f"source_model_contains={source_model_contains or '(any)'} root={root or '(all)'} limit={limit}"
        )


@app.command("image-tags-backfill")
def image_tags_backfill(
    root: Optional[str] = typer.Option(None, help="Optional asset path prefix filter (e.g. E:\\01_INCOMING)"),
    limit: int = typer.Option(0, min=0, help="Max assets to scan (0 = all matching assets)"),
    max_tags: int = typer.Option(8, min=1, max=32, help="Max derived tags per asset"),
    only_missing_img: bool = typer.Option(True, help="Skip assets already containing img/cap+img tag links"),
    apply: bool = typer.Option(True, help="Apply changes (set false for dry-run)"),
    commit_every: int = typer.Option(200, min=20, max=5000, help="Commit cadence"),
) -> None:
    """Enqueue image-tag tasks (RAM++ HTTP path) for matching image assets."""
    from pathlib import Path as _Path
    from .dependencies import ensure_db
    from .db import Asset, AssetTag, Task

    ensure_db()

    _, SessionLocal = _session_factory()
    with SessionLocal() as session:
        q = session.query(Asset.id, Asset.path, Asset.mime).order_by(Asset.id.asc())
        if root:
            prefix = str(_Path(root).resolve())
            q = q.filter(Asset.path.like(prefix + "%"))

        scanned = 0
        skipped_video = 0
        skipped_has_img = 0
        skipped_pending = 0
        enqueued = 0

        for asset_id, _path, mime in q:
            if limit and scanned >= limit:
                break
            scanned += 1
            mm = str(mime or "").lower()
            if mm.startswith("video/"):
                skipped_video += 1
                continue

            if only_missing_img:
                has_img = (
                    session.query(AssetTag.id)
                    .filter(AssetTag.asset_id == asset_id, AssetTag.source.in_(["img", "cap+img"]))
                    .first()
                )
                if has_img:
                    skipped_has_img += 1
                    continue

            existing_task = session.query(Task).filter(
                Task.type == 'image_tag',
                Task.state.in_(['pending', 'running']),
                Task.payload_json['asset_id'].as_integer() == asset_id,
            ).first()
            if existing_task:
                skipped_pending += 1
                continue

            if apply:
                session.add(
                    Task(
                        type='image_tag',
                        priority=115,
                        payload_json={'asset_id': int(asset_id), 'max_tags': int(max_tags)},
                    )
                )
            enqueued += 1

            if apply and scanned % commit_every == 0:
                session.commit()
                typer.echo(
                    f"progress scanned={scanned} enqueued={enqueued} skipped_has_img={skipped_has_img}"
                )

        if apply:
            session.commit()

        mode = "APPLY" if apply else "DRY-RUN"
        typer.echo(f"image-tags-backfill ({mode})")
        typer.echo(
            f"scanned={scanned} enqueued={enqueued} skipped_video={skipped_video} "
            f"skipped_has_img={skipped_has_img} skipped_pending={skipped_pending} "
            f"max_tags={max_tags} only_missing_img={only_missing_img} root={root or '(all)'} limit={limit}"
        )


@app.command("captions-backfill-zh")
def captions_backfill_zh(
    root: Optional[str] = typer.Option(None, help="Optional asset path prefix filter (e.g. E:\\01_INCOMING)"),
    limit: int = typer.Option(0, min=0, help="Max assets to scan (0 = all matching assets)"),
    source_model_contains: Optional[str] = typer.Option(None, help="Optional model substring filter for source captions"),
    source_lang: str = typer.Option("en", help="Source language tag"),
    target_lang: str = typer.Option("zh-CN", help="Target language tag"),
    translation_service_url: Optional[str] = typer.Option(None, help="Caption service base URL, defaults to CAPTION_SERVICE_URL"),
    overwrite_existing_zh: bool = typer.Option(False, help="Overwrite existing generated zh variants"),
    apply: bool = typer.Option(True, help="Apply changes (set false for dry-run)"),
    commit_every: int = typer.Option(100, min=20, max=2000, help="Commit cadence"),
    timeout_sec: float = typer.Option(90.0, min=10.0, max=300.0, help="Per-translation request timeout"),
) -> None:
    """Backfill Chinese caption variants by translating existing captions via local caption service."""
    from pathlib import Path as _Path
    import httpx
    from .db import Asset, Caption

    settings = get_settings()
    base_url = (
        translation_service_url
        or os.getenv("CAPTION_SERVICE_URL")
        or getattr(settings, "caption_service_url", "http://127.0.0.1:8102")
        or "http://127.0.0.1:8102"
    ).rstrip("/")
    src_filter = (source_model_contains or "").strip().lower()
    bad_texts = {
        "caption service unavailable",
        "caption service connection failed",
        "caption generation error",
        "caption generation failed",
    }

    def _is_zh_model(model: str) -> bool:
        m = (model or "").strip().lower()
        return ("|zh" in m) or ("-zh" in m) or ("_zh" in m) or ("zh-cn" in m) or ("zh_cn" in m)

    _, SessionLocal = _session_factory()
    with SessionLocal() as session:
        q = session.query(Asset.id, Asset.path).order_by(Asset.id.asc())
        if root:
            prefix = str(_Path(root).resolve())
            q = q.filter(Asset.path.like(prefix + "%"))

        scanned = 0
        has_source = 0
        translated = 0
        skipped_has_zh = 0
        skipped_no_source = 0
        failed = 0
        touched_assets: set[int] = set()

        with httpx.Client(timeout=timeout_sec, trust_env=False) as client:
            for asset_id, _path in q:
                if limit and scanned >= limit:
                    break
                scanned += 1

                caps = (
                    session.query(Caption)
                    .filter(Caption.asset_id == asset_id)
                    .order_by(Caption.created_at.desc(), Caption.id.desc())
                    .all()
                )
                if not caps:
                    skipped_no_source += 1
                    continue

                if (not overwrite_existing_zh) and any(_is_zh_model(c.model or "") for c in caps):
                    skipped_has_zh += 1
                    continue

                source_cap = None
                for c in caps:
                    txt = (c.text or "").strip()
                    mdl = (c.model or "").strip()
                    if not txt:
                        continue
                    if txt.lower() in bad_texts:
                        continue
                    if _is_zh_model(mdl):
                        continue
                    if src_filter and src_filter not in mdl.lower():
                        continue
                    source_cap = c
                    break

                if source_cap is None:
                    skipped_no_source += 1
                    continue
                has_source += 1

                if not apply:
                    translated += 1
                    continue

                try:
                    payload = {
                        "text": source_cap.text,
                        "source_lang": source_lang,
                        "target_lang": target_lang,
                        "style": "caption",
                    }
                    resp = client.post(f"{base_url}/translate", json=payload)
                    if resp.status_code != 200:
                        failed += 1
                        continue
                    body = resp.json()
                    zh = (body.get("translation") or "").strip()
                    if not zh:
                        failed += 1
                        continue
                    model_name = f"{(source_cap.model or 'caption')}|zh-cn"
                    session.add(
                        Caption(
                            asset_id=int(asset_id),
                            text=zh,
                            model=model_name,
                            user_edited=False,
                            quality_tier="translated",
                            model_version="zh-v1",
                        )
                    )
                    touched_assets.add(int(asset_id))
                    translated += 1
                except Exception:
                    failed += 1

                if apply and translated % commit_every == 0:
                    session.commit()
                    typer.echo(
                        f"progress scanned={scanned} translated={translated} failed={failed} "
                        f"skipped_has_zh={skipped_has_zh} skipped_no_source={skipped_no_source}"
                    )

        if apply:
            for aid in touched_assets:
                cnt = (
                    session.query(func.count(Caption.id))
                    .filter(Caption.asset_id == aid, Caption.superseded == False)  # noqa: E712
                    .scalar()
                    or 0
                )
                a = session.get(Asset, aid)
                if a is not None:
                    a.caption_variant_count = int(cnt)
                    a.caption_processed = bool(cnt > 0)
            session.commit()

        mode = "APPLY" if apply else "DRY-RUN"
        typer.echo(f"captions-backfill-zh ({mode})")
        typer.echo(
            f"scanned={scanned} has_source={has_source} translated={translated} failed={failed} "
            f"skipped_has_zh={skipped_has_zh} skipped_no_source={skipped_no_source} "
            f"target_lang={target_lang} source_lang={source_lang} base_url={base_url} "
            f"root={root or '(all)'} limit={limit}"
        )


@app.command("captions-prune-model")
def captions_prune_model(
    model_contains: str = typer.Option("blip2", help="Case-insensitive substring match against captions.model"),
    keep_user_edited: bool = typer.Option(True, "--keep-user-edited/--include-user-edited", help="Preserve user-edited captions"),
    require_replacement: bool = typer.Option(True, "--require-replacement/--allow-empty-after-delete", help="Delete only when asset has at least one non-matching caption"),
    apply: bool = typer.Option(True, "--apply/--dry-run", help="Apply deletion (or dry-run)"),
    commit_every: int = typer.Option(500, min=50, max=5000, help="Commit cadence"),
) -> None:
    """Delete caption variants by model name pattern (e.g. remove all BLIP2 outputs)."""
    from .db import Asset, Caption

    needle = (model_contains or "").strip().lower()
    if not needle:
        typer.echo("model_contains cannot be empty", err=True)
        raise typer.Exit(2)

    like_pattern = f"%{needle}%"
    _, SessionLocal = _session_factory()
    with SessionLocal() as session:
        q = session.query(Caption.id).filter(func.lower(Caption.model).like(like_pattern))
        if keep_user_edited:
            q = q.filter(Caption.user_edited == False)  # noqa: E712
        candidate_ids = [int(cid) for (cid,) in q.all()]

        scanned = 0
        deleted = 0
        skipped_missing_replacement = 0
        touched_assets: set[int] = set()

        for cap_id in candidate_ids:
            scanned += 1
            cap = session.get(Caption, cap_id)
            if cap is None:
                continue

            if require_replacement:
                replacement = (
                    session.query(Caption.id)
                    .filter(Caption.asset_id == cap.asset_id)
                    .filter(Caption.id != cap.id)
                    .filter(~func.lower(Caption.model).like(like_pattern))
                    .first()
                )
                if replacement is None:
                    skipped_missing_replacement += 1
                    continue

            touched_assets.add(int(cap.asset_id))
            if apply:
                session.delete(cap)
            deleted += 1

            if apply and deleted % commit_every == 0:
                session.commit()
                typer.echo(
                    f"progress scanned={scanned} deleted={deleted} "
                    f"skipped_missing_replacement={skipped_missing_replacement}"
                )

        if apply:
            # Recompute caption status fields for touched assets.
            for aid in touched_assets:
                cnt = (
                    session.query(func.count(Caption.id))
                    .filter(Caption.asset_id == aid, Caption.superseded == False)  # noqa: E712
                    .scalar()
                    or 0
                )
                asset = session.get(Asset, aid)
                if asset is not None:
                    asset.caption_variant_count = int(cnt)
                    asset.caption_processed = bool(cnt > 0)
            session.commit()

        mode = "APPLY" if apply else "DRY-RUN"
        typer.echo(f"captions-prune-model ({mode})")
        typer.echo(
            f"model_contains='{needle}' scanned={scanned} deleted={deleted} "
            f"skipped_missing_replacement={skipped_missing_replacement} "
            f"keep_user_edited={keep_user_edited} require_replacement={require_replacement}"
        )


# (Defer CLI invocation to the very end of file after all commands are registered)
import os, sys
import typer
from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from .config import get_settings
from sqlalchemy import create_engine, inspect
from .tasks import INDEX_SINGLETON, EMBED_DIM
from .vector_index import load_index_from_embeddings
from .main import SessionLocal

# Reuse the same Typer app defined above; do not reassign.

@app.command()
def migrate(action: str = typer.Argument('upgrade', help='upgrade|downgrade|stamp'), target: str = typer.Argument('head')):
    """Run alembic migrations programmatically."""
    settings = get_settings()
    cfg_path = os.path.join(os.path.dirname(__file__), '..', 'alembic.ini')
    alembic_cfg = AlembicConfig(cfg_path)
    alembic_cfg.set_main_option('script_location', settings.alembic_script_location)
    alembic_cfg.set_main_option('sqlalchemy.url', settings.database_url)
    if action == 'upgrade':
        alembic_command.upgrade(alembic_cfg, target)
    elif action == 'downgrade':
        alembic_command.downgrade(alembic_cfg, target)
    elif action == 'stamp':
        alembic_command.stamp(alembic_cfg, target)
    else:
        raise typer.BadParameter('Unsupported action')

@app.command()
def revision(message: str = typer.Option(..., '--message', '-m', help='Revision message'), autogenerate: bool = typer.Option(True, help='Autogenerate from models'), head: str = typer.Option('head', help='Base head to branch from')):
    """Create a new Alembic revision file."""
    settings = get_settings()
    cfg_path = os.path.join(os.path.dirname(__file__), '..', 'alembic.ini')
    alembic_cfg = AlembicConfig(cfg_path)
    alembic_cfg.set_main_option('script_location', settings.alembic_script_location)
    alembic_cfg.set_main_option('sqlalchemy.url', settings.database_url)
    alembic_command.revision(alembic_cfg, message=message, autogenerate=autogenerate, head=head)
    typer.echo('Revision created.')

@app.command()
def stamp_existing(head: str = typer.Option('head', help='Revision to stamp as current')):
    """Stamp an existing (pre-Alembic) database with the given revision if not already versioned."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    cfg_path = os.path.join(os.path.dirname(__file__), '..', 'alembic.ini')
    alembic_cfg = AlembicConfig(cfg_path)
    alembic_cfg.set_main_option('script_location', settings.alembic_script_location)
    alembic_cfg.set_main_option('sqlalchemy.url', settings.database_url)
    if 'alembic_version' in tables:
        typer.echo('alembic_version table already present; no action taken.')
        return
    if not tables:
        typer.echo('Database empty; nothing to stamp.')
        return
    alembic_command.stamp(alembic_cfg, head)
    typer.echo(f'Stamped existing schema as {head}.')

## NOTE: Keep the CLI invocation at the very end so all @app.command functions are registered

@app.command()
def rebuild_index(limit: int = typer.Option(None, help='Max embeddings to load (default settings.MAX_INDEX_LOAD)')):
    """Rebuild in-memory vector index from stored embedding files."""
    settings = get_settings()
    from .tasks import INDEX_SINGLETON as IDX  # ensure initialized elsewhere
    if IDX is None:
        typer.secho('Index not initialized (create TaskExecutor first).', fg=typer.colors.RED)
        raise typer.Exit(1)
    IDX.clear()
    loaded = load_index_from_embeddings(SessionLocal, IDX, limit=limit or settings.max_index_load)
    typer.secho(f'Rebuilt index with {loaded} embeddings (dim={EMBED_DIM}).', fg=typer.colors.GREEN)
    
@app.command()
def recluster_persons():
    """Enqueue a full face/person recluster task."""
    from .db import Task
    from .main import SessionLocal as _SessionLocal
    with _SessionLocal() as session:
        existing = session.query(Task).filter(Task.type=='person_recluster', Task.state=='pending').first()
        if existing:
            typer.echo("Recluster already pending (task id %s)" % existing.id)
            return
        t = Task(type='person_recluster', priority=300, payload_json={})
        session.add(t)
        session.commit()
        typer.echo(f"Enqueued person_recluster task {t.id}")

@app.command()
def rebuild_video_indices() -> None:
    """Rebuild both video-level and segment-level in-memory indices from derived embeddings."""
    import numpy as np
    from glob import glob
    from pathlib import Path as _Path
    settings = get_settings()
    from . import tasks as tasks_mod
    # Ensure index singletons exist
    if getattr(tasks_mod, 'VIDEO_INDEX_SINGLETON', None) is None:
        tasks_mod.VIDEO_INDEX_SINGLETON = tasks_mod.InMemoryVectorIndex(tasks_mod.EMBED_DIM)
    if getattr(tasks_mod, 'VIDEO_SEG_INDEX_SINGLETON', None) is None:
        tasks_mod.VIDEO_SEG_INDEX_SINGLETON = tasks_mod.InMemoryVectorIndex(tasks_mod.EMBED_DIM)
    # Clear both
    tasks_mod.VIDEO_INDEX_SINGLETON.clear()
    tasks_mod.VIDEO_SEG_INDEX_SINGLETON.clear()
    # Load video-level embeddings
    vid_ids, vid_vecs = [], []
    for fp in glob(str(_Path(settings.derived_path) / 'video_embeddings' / '*.npy')):
        p = _Path(fp)
        if p.stem.startswith('seg_'):
            continue
        try:
            vid_ids.append(int(p.stem))
            vid_vecs.append(np.load(fp).astype('float32'))
        except Exception:
            continue
    if vid_ids:
        tasks_mod.VIDEO_INDEX_SINGLETON.add(vid_ids, np.stack(vid_vecs))
    # Load segment-level embeddings
    seg_ids, seg_vecs = [], []
    for fp in glob(str(_Path(settings.derived_path) / 'video_embeddings' / 'seg_*.npy')):
        p = _Path(fp)
        try:
            seg_ids.append(int(p.stem.split('_',1)[1]))
            seg_vecs.append(np.load(fp).astype('float32'))
        except Exception:
            continue
    if seg_ids:
        tasks_mod.VIDEO_SEG_INDEX_SINGLETON.add(seg_ids, np.stack(seg_vecs))
    typer.echo(f"video_index loaded={len(vid_ids)}; segment_index loaded={len(seg_ids)}")


@app.command()
def validate_lvface() -> None:
    """Validate LVFace configuration and attempt a minimal embedding inference."""
    from .config import get_settings
    from pathlib import Path as _Path
    import numpy as _np
    from PIL import Image as _Image
    from .face_embedding_service import StubFaceEmbeddingProvider  # type: ignore
    s = get_settings()
    # Show config (avoid printing MODEL_PATH when external dir is used)
    typer.echo(f"LVFACE_EXTERNAL_DIR={s.lvface_external_dir or '(none)'}")
    typer.echo(f"LVFACE_PYTHON_EXE={s.lvface_python_exe or os.getenv('LVFACE_PYTHON_EXE','') or '(auto)'}")
    if s.lvface_external_dir:
        typer.echo(f"LVFACE_MODEL_NAME={s.lvface_model_name}")
    else:
        typer.echo(f"LVFACE_MODEL_PATH={s.lvface_model_path}")
    # Basic file checks
    if s.lvface_external_dir:
        ext = _Path(s.lvface_external_dir)
        py = ext / ('.venv/Scripts/python.exe' if os.name=='nt' else '.venv/bin/python')
        inf = ext / 'inference.py'
        mdl = ext / 'models' / s.lvface_model_name
        typer.echo(f"external_dir exists: {ext.exists()}")
        typer.echo(f"python exists: {py.exists()}")
        typer.echo(f"inference.py exists: {inf.exists()}")
        typer.echo(f"model exists: {mdl.exists()}")
    else:
        typer.echo(f"builtin onnx model exists: {_Path(s.lvface_model_path).exists()}")
    # Try provider init and one dummy inference
    try:
        os.environ['FACE_EMBED_PROVIDER'] = 'lvface'
        # Clear cached settings and provider so env var takes effect
        try:
            from .config import get_settings as _gs
            _gs.cache_clear()  # type: ignore[attr-defined]
        except Exception:
            pass
        from .face_embedding_service import get_face_embedding_provider
        try:
            get_face_embedding_provider.cache_clear()  # type: ignore[attr-defined]
        except Exception:
            pass
        prov = get_face_embedding_provider()
        # Create a tiny dummy face crop (gray)
        img = _Image.new('RGB', (112,112), color=(128,128,128))
        vec = prov.embed_face(img)
        provider_cls = prov.__class__.__name__
        norm = float(_np.linalg.norm(vec))
        # Detect fallback
        if isinstance(prov, StubFaceEmbeddingProvider):
            typer.secho(
                f"LVFace validation fell back to stub provider (no real LVFace loaded). dim={vec.shape[0]} norm={norm:.3f}",
                fg=typer.colors.YELLOW
            )
            # Provide actionable tip
            if not s.lvface_external_dir and not _Path(s.lvface_model_path).exists():
                typer.echo(
                    "Hint: Provide an ONNX at LVFACE_MODEL_PATH or use an external LVFace via LVFACE_EXTERNAL_DIR.\n"
                    "Dev option: generate a dummy model with 'python tools/generate_dummy_lvface_model.py --out models/lvface.onnx --dim "
                    f"{s.face_embed_dim}'."
                )
            raise typer.Exit(2)
        else:
            # Distinguish builtin vs external
            mode = 'external-subprocess' if provider_cls == 'LVFaceSubprocessProvider' else 'builtin-onnx'
            typer.secho(
                f"LVFace provider OK ({mode}). Embedding dim={vec.shape[0]} norm={norm:.3f}",
                fg=typer.colors.GREEN
            )
    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(f"LVFace validation failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command()
def validate_caption() -> None:
    """Validate external caption setup and attempt a minimal caption generation."""
    from .caption_validation import get_caption_config_summary, validate_caption_external_setup
    from .config import get_settings
    from PIL import Image as _Image
    from .caption_service import StubCaptionProvider  # type: ignore
    s = get_settings()
    # Print summary
    summary = get_caption_config_summary()
    typer.echo(f"Caption config: {summary}")
    # Validate external if configured
    if s.caption_external_dir:
        try:
            validate_caption_external_setup()
            typer.secho("External caption setup validated.", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"Caption external validation failed: {e}", fg=typer.colors.RED)
            raise typer.Exit(1)
    # Try provider init and one dummy caption
    try:
        from .caption_service import get_caption_provider
        prov = get_caption_provider()
        img = _Image.new('RGB', (640, 360), color=(180, 200, 220))
        cap = prov.generate_caption(img)
        preview = (cap or '').strip()
        if len(preview) > 120:
            preview = preview[:117] + '...'
        if isinstance(prov, StubCaptionProvider) and summary.get('provider') != 'stub':
            typer.secho(
                f"Caption validation fell back to stub provider (requested '{summary.get('provider')}').",
                fg=typer.colors.YELLOW
            )
            raise typer.Exit(2)
        typer.secho(f"Caption provider OK. Model={prov.get_model_name()} Caption='{preview}'", fg=typer.colors.GREEN)
    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(f"Caption validation failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command()
def validate_image_tag(strict: bool = typer.Option(False, help="Exit non-zero if provider resolution fails")) -> None:
    """Validate image tag provider wiring (RAM++ HTTP path)."""
    from .config import get_settings
    s = get_settings()
    typer.echo(
        f"Image-tag config: provider={getattr(s, 'image_tag_provider', 'stub')} "
        f"url={getattr(s, 'image_tag_service_url', '')} "
        f"model={getattr(s, 'image_tag_model', '')} "
        f"auto_enable={bool(getattr(s, 'image_tag_auto_enable', False))}"
    )
    try:
        from .image_tag_service import get_image_tag_provider
        prov = get_image_tag_provider()
        typer.secho(f"Image-tag provider OK: model={prov.get_model_name()}", fg=typer.colors.GREEN)
    except Exception as e:
        msg = f"Image-tag provider validation failed: {e}"
        if strict:
            typer.secho(msg, fg=typer.colors.RED)
            raise typer.Exit(1)
        typer.secho(msg, fg=typer.colors.YELLOW)


@app.command("warmup")
def warmup(
    do_face: bool = typer.Option(True, help="Warm up face embedding provider"),
    do_caption: bool = typer.Option(True, help="Warm up caption provider"),
    do_image_tag: bool = typer.Option(False, help="Warm up image tagging provider"),
    repeats: int = typer.Option(1, min=1, max=3, help="How many dummy inferences to run per provider"),
):
    """Warm up configured providers (loads models and runs a tiny inference)."""
    import time as _time
    from PIL import Image as _Image
    import numpy as _np
    ok = True
    if do_face:
        try:
            from .face_embedding_service import get_face_embedding_provider as _get_face
            prov = _get_face()
            img = _Image.new('RGB', (112,112), color=(128,128,128))
            t0 = _time.time()
            last_norm = 0.0
            for _ in range(repeats):
                vec = prov.embed_face(img)
                last_norm = float(_np.linalg.norm(vec))
            t1 = _time.time()
            typer.secho(f"Face warmup OK: provider={prov.__class__.__name__} dim={vec.shape[0]} time={(t1-t0):.2f}s norm={last_norm:.3f}", fg=typer.colors.GREEN)
        except Exception as e:
            ok = False
            typer.secho(f"Face warmup failed: {e}", fg=typer.colors.RED)
    if do_caption:
        try:
            from .caption_service import get_caption_provider as _get_cap
            prov = _get_cap()
            img = _Image.new('RGB', (640, 360), color=(180, 200, 220))
            t0 = _time.time()
            last_cap = ''
            for _ in range(repeats):
                last_cap = prov.generate_caption(img)
            t1 = _time.time()
            preview = (last_cap or '').strip()
            if len(preview) > 100:
                preview = preview[:97] + '...'
            typer.secho(f"Caption warmup OK: provider={prov.get_model_name()} time={(t1-t0):.2f}s caption='{preview}'", fg=typer.colors.GREEN)
        except Exception as e:
            ok = False
            typer.secho(f"Caption warmup failed: {e}", fg=typer.colors.RED)
    if do_image_tag:
        try:
            from .image_tag_service import get_image_tag_provider as _get_img_tag
            prov = _get_img_tag()
            img = _Image.new('RGB', (640, 360), color=(170, 190, 210))
            t0 = _time.time()
            last_tags = []
            for _ in range(repeats):
                last_tags = prov.generate_tags(img, max_tags=8)
            t1 = _time.time()
            preview = ', '.join(str(x.get('name') or '') for x in last_tags[:5] if isinstance(x, dict))
            typer.secho(
                f"Image-tag warmup OK: provider={prov.get_model_name()} time={(t1-t0):.2f}s tags='{preview}'",
                fg=typer.colors.GREEN,
            )
        except Exception as e:
            ok = False
            typer.secho(f"Image-tag warmup failed: {e}", fg=typer.colors.RED)
    if not ok:
        raise typer.Exit(1)

if __name__ == '__main__':
    # Invoke the CLI after all command functions have been registered
    app()
