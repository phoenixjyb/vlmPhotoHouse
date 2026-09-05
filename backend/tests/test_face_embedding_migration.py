from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


def _migration_config(backend_root: Path, database_path: Path) -> Config:
    config = Config(str(backend_root / 'alembic.ini'))
    config.set_main_option(
        'script_location', str(backend_root / 'migrations')
    )
    config.set_main_option(
        'sqlalchemy.url', f"sqlite:///{database_path.as_posix()}"
    )
    return config


def _migration_head(config: Config) -> str:
    return ScriptDirectory.from_config(config).get_current_head()


def test_fresh_database_migrates_to_versioned_face_embedding_schema(
    tmp_path: Path, monkeypatch
):
    backend_root = Path(__file__).resolve().parents[1]
    database_path = tmp_path / 'migration.sqlite'
    config = _migration_config(backend_root, database_path)
    monkeypatch.setenv('DATABASE_URL', f"sqlite:///{database_path.as_posix()}")

    command.upgrade(config, 'head')

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        schema = inspect(engine)
        assert {
            'album_assets',
            'albums',
            'face_embedding_artifacts',
            'person_embedding_artifacts',
        } <= set(schema.get_table_names())
        face_columns = {
            column['name'] for column in schema.get_columns('face_detections')
        }
        assert {'landmarks_json', 'landmark_model'} <= face_columns
        with engine.connect() as connection:
            version = connection.execute(
                text('SELECT version_num FROM alembic_version')
            ).scalar_one()
        assert version == _migration_head(config)
    finally:
        engine.dispose()


def test_migration_handles_live_style_assignment_table_ahead_of_stamp(
    tmp_path: Path, monkeypatch
):
    from app.db import FaceAssignmentEvent

    backend_root = Path(__file__).resolve().parents[1]
    database_path = tmp_path / 'live-style.sqlite'
    config = _migration_config(backend_root, database_path)
    monkeypatch.setenv('DATABASE_URL', f"sqlite:///{database_path.as_posix()}")

    command.upgrade(config, '9b1e7d2a5c6f')
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        FaceAssignmentEvent.__table__.create(engine)
    finally:
        engine.dispose()

    command.upgrade(config, 'head')

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        schema = inspect(engine)
        assert 'face_embedding_artifacts' in schema.get_table_names()
        with engine.connect() as connection:
            version = connection.execute(
                text('SELECT version_num FROM alembic_version')
            ).scalar_one()
        assert version == _migration_head(config)
    finally:
        engine.dispose()
