from __future__ import annotations

import os
import typer
from typing import List, Optional
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from . import db
from .config import get_settings
from . import ingest as ingest_mod

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
    from .db import Asset, Embedding, Caption
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
            # Missing image embedding
            sub_emb = session.query(Embedding.asset_id).filter(Embedding.modality == 'image')
            missing_embed = session.query(_f.count(Asset.id)).filter(Asset.path.like(like)).filter(~Asset.id.in_(sub_emb)).scalar() or 0
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


@app.command("warmup")
def warmup(
    do_face: bool = typer.Option(True, help="Warm up face embedding provider"),
    do_caption: bool = typer.Option(True, help="Warm up caption provider"),
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
    if not ok:
        raise typer.Exit(1)

if __name__ == '__main__':
    # Invoke the CLI after all command functions have been registered
    app()
