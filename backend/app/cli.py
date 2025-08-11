import os, sys
import typer
from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from .config import get_settings
from sqlalchemy import create_engine, inspect
from .tasks import INDEX_SINGLETON, EMBED_DIM
from .vector_index import load_index_from_embeddings
from .main import SessionLocal

app = typer.Typer(add_completion=False)

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

if __name__ == '__main__':
    app()

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
