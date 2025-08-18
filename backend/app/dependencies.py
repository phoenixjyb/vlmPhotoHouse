"""
Shared dependencies for the application.
"""
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine, inspect
from .db import Base
from .config import get_settings
from typing import Generator
import os

# Lazily-initialized engine/session that track the current DATABASE_URL
engine = None
SessionLocal = None
_BOUND_URL = None
_DB_READY = False

def _rebind_if_needed():
    """Ensure engine and SessionLocal are bound to the current DATABASE_URL.

    Tests override env (DATABASE_URL) between runs; this keeps the dependency in sync
    without requiring a process restart.
    """
    global engine, SessionLocal, _BOUND_URL
    settings = get_settings()  # respects cache_clear from tests
    target_url = settings.database_url
    if engine is None or SessionLocal is None or str(getattr(engine, 'url', '')) != str(target_url):
        try:
            # Dispose old engine if present
            if engine is not None:
                try:
                    engine.dispose()
                except Exception:
                    pass
        finally:
            pass
        engine_new = create_engine(target_url, future=True, echo=False)
        if SessionLocal is not None:
            try:
                SessionLocal.configure(bind=engine_new)  # type: ignore[attr-defined]
            except Exception:
                SessionLocal = sessionmaker(bind=engine_new, autoflush=False, autocommit=False, future=True)
        else:
            SessionLocal = sessionmaker(bind=engine_new, autoflush=False, autocommit=False, future=True)
        engine = engine_new
        _BOUND_URL = str(target_url)

def ensure_db():
    global _DB_READY
    # Always ensure bindings are up-to-date before checking schema
    _rebind_if_needed()
    try:
        insp = inspect(engine)
        if not insp.has_table('assets'):
            Base.metadata.create_all(bind=engine)
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
        # Fallback for Asset new video columns
        if insp.has_table('assets'):
            acols = {c['name'] for c in insp.get_columns('assets')}
            with engine.begin() as conn:
                if 'duration_sec' not in acols:
                    try:
                        conn.exec_driver_sql('ALTER TABLE assets ADD COLUMN duration_sec FLOAT')
                    except Exception:
                        pass
                if 'fps' not in acols:
                    try:
                        conn.exec_driver_sql('ALTER TABLE assets ADD COLUMN fps FLOAT')
                    except Exception:
                        pass
        # Create video_segments table if missing (SQLite)
        if not insp.has_table('video_segments'):
            try:
                Base.metadata.tables['video_segments'].create(bind=engine)  # type: ignore
            except Exception:
                pass
        _DB_READY = True
    except Exception as e:
        print(f"Database initialization error: {e}")
        raise

# Database dependency
def get_db() -> Generator[Session, None, None]:
    ensure_db()
    with SessionLocal() as session:  # type: ignore[misc]
        yield session

# Shared path constants
DERIVED_PATH = os.getenv('DERIVED_PATH', './derived')
