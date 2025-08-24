import os, tempfile, shutil, sys
# Ensure backend directory (parent of this tests folder) is on sys.path so 'app' package resolves after relocations
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)
import pytest
from fastapi.testclient import TestClient
from app.config import get_settings

# Early environment guard BEFORE importing application modules that may rely on optional deps.
if os.getenv('DISABLE_ENV_GUARD','false').lower() not in ('1','true','yes'):
    exe = sys.executable
    if os.sep + '.venv' + os.sep not in exe:
        raise RuntimeError(f"Interpreter {exe} does not look like project .venv (expected path containing /.venv/). Set DISABLE_ENV_GUARD=1 to bypass.")
    try:
        import multipart  # type: ignore
    except Exception as e:
        raise RuntimeError(f"python-multipart not importable at test startup: {e}")

@pytest.fixture(scope='session')
def temp_env_root():
    d = tempfile.mkdtemp(prefix='vlmtest_')
    originals = os.path.join(d, 'originals')
    derived = os.path.join(d, 'derived')
    os.makedirs(originals, exist_ok=True)
    os.makedirs(derived, exist_ok=True)
    yield {'root': d, 'originals': originals, 'derived': derived}
    shutil.rmtree(d, ignore_errors=True)

@pytest.fixture(autouse=True)
def override_settings(temp_env_root, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{temp_env_root["root"]}/test.sqlite')
    monkeypatch.setenv('ORIGINALS_PATH', temp_env_root['originals'])
    monkeypatch.setenv('DERIVED_PATH', temp_env_root['derived'])
    # Use fallback ensure_db column addition logic instead of full Alembic migrations
    monkeypatch.setenv('AUTO_MIGRATE', 'false')
    monkeypatch.setenv('ENABLE_INLINE_WORKER', 'false')
    monkeypatch.setenv('RUN_MODE', 'tests')
    # clear cache
    from functools import lru_cache
    get_settings.cache_clear()  # type: ignore
    # Reinitialize executor/engine to pick up DATABASE_URL override and create tables
    from app.main import reinit_executor_for_tests, init_db
    reinit_executor_for_tests()
    init_db()
    yield
    get_settings.cache_clear()  # type: ignore

@pytest.fixture()
def client():
    # Import app lazily after environment guard
    from app.main import app
    # Use context manager to ensure cleanup of connections/resources
    with TestClient(app) as c:
        yield c


# Optional global skip: set SKIP_ALL_TESTS=true to skip the entire suite cleanly (exit code 0).
def pytest_collection_modifyitems(config, items):
    skip_all = os.getenv('SKIP_ALL_TESTS', 'false').lower() in ('1', 'true', 'yes')
    if not skip_all:
        return
    skip_marker = pytest.mark.skip(reason="Skipping all tests because SKIP_ALL_TESTS=true")
    for item in items:
        item.add_marker(skip_marker)
