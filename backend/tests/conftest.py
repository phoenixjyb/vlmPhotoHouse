import os, tempfile, shutil
import pytest
from fastapi.testclient import TestClient
from app.main import app, settings
from app.config import get_settings

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
    monkeypatch.setenv('AUTO_MIGRATE', 'true')
    monkeypatch.setenv('ENABLE_INLINE_WORKER', 'false')
    # clear cache
    from functools import lru_cache
    get_settings.cache_clear()  # type: ignore
    yield
    get_settings.cache_clear()  # type: ignore

@pytest.fixture()
def client():
    return TestClient(app)


# Optional global skip: set SKIP_ALL_TESTS=true to skip the entire suite cleanly (exit code 0).
def pytest_collection_modifyitems(config, items):
    skip_all = os.getenv('SKIP_ALL_TESTS', 'false').lower() in ('1', 'true', 'yes')
    if not skip_all:
        return
    skip_marker = pytest.mark.skip(reason="Skipping all tests because SKIP_ALL_TESTS=true")
    for item in items:
        item.add_marker(skip_marker)
