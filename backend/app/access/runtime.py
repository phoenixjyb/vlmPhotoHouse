"""Explicit existing-SQLite adapter; no environment discovery or import-time I/O.

Deployment wiring must deliberately construct RuntimeConfiguration. Importing the
default app never imports this module or enables these connections. This module
never migrates, bootstraps, maps assets, opens listeners or starts workers.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import stat
import time

from .media import MediaRuntime
from .transport import AccessRuntime

REQUIRED_REVISION = 'b6e3f9a5c721'
REQUIRED_TABLES = frozenset({
    'assets', 'captions', 'face_detections', 'access_accounts', 'access_sessions',
    'access_operators', 'access_libraries', 'access_memberships', 'access_invitations',
    'access_asset_libraries', 'access_audit', 'access_admission_key', 'access_attempts',
    'access_kdf_slot', 'access_provisioning_receipts',
})


class RuntimeUnavailable(RuntimeError):
    """Generic configuration/storage refusal; never includes a path or SQL value."""


@dataclass(frozen=True)
class ExistingDatabase:
    path: Path
    timeout: float = 3.0
    read_only: bool = False

    def __post_init__(self):
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise ValueError('An explicit absolute database Path is required')
        if type(self.read_only) is not bool:
            raise ValueError('Explicit read-only flag required')
        if type(self.timeout) not in (int, float) or not 0 < self.timeout <= 10:
            raise ValueError('Database timeout must be between zero and ten seconds')

    @contextmanager
    def __call__(self):
        connection = None
        try:
            # SQLite mode=rw is essential: a typo must not create an empty DB.
            # Require a directly selected regular file; no symlink discovery.
            before = self.path.lstat()
            if not stat.S_ISREG(before.st_mode) or self.path.resolve(strict=True) != self.path:
                raise RuntimeUnavailable('Access unavailable')
            connection = sqlite3.connect(self.path.as_uri() + ('?mode=ro' if self.read_only else '?mode=rw'), uri=True, timeout=self.timeout)
            after = self.path.lstat()
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise RuntimeUnavailable('Access unavailable')
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            if self.read_only:
                connection.execute('PRAGMA query_only=ON')
            if connection.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
                raise RuntimeUnavailable('Access unavailable')
            versions = connection.execute('SELECT version_num FROM alembic_version').fetchall()
            if versions != [(REQUIRED_REVISION,)]:
                raise RuntimeUnavailable('Access unavailable')
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not REQUIRED_TABLES <= tables:
                raise RuntimeUnavailable('Access unavailable')
            key = connection.execute('SELECT typeof(secret),length(secret) FROM access_admission_key WHERE id=1').fetchone()
            if key != ('blob', 32):
                raise RuntimeUnavailable('Access unavailable')
        except (OSError, sqlite3.Error, ValueError, RuntimeUnavailable):
            if connection is not None:
                connection.close()
            raise RuntimeUnavailable('Access unavailable') from None
        try:
            yield connection
        finally:
            # Includes successful callers that forgot to commit and failed requests.
            # The domain layer owns commits; the adapter never commits on their behalf.
            if connection.in_transaction:
                connection.rollback()
            connection.close()


@dataclass(frozen=True)
class RuntimeConfiguration:
    database: Path
    web_origin: str
    original_roots: tuple[Path, ...]
    derived_root: Path

    def build_app(self, *, clock=time.time):
        """Build only; storage is opened lazily in the request's worker thread.

        No environment variables, .env, existing model settings, implicit roots,
        proxy trust or production credentials are consulted. Missing/wrong storage
        returns generic 503 from protected routes. The public code shell remains.
        """
        database = ExistingDatabase(self.database)
        access = AccessRuntime(database, self.web_origin, clock=clock)
        media = MediaRuntime(self.original_roots, self.derived_root)
        from ..main import create_app
        return create_app(access_runtime=access, media_runtime=media)
