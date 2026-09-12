"""Durable, pre-KDF admission for the shared account transport.

Uses the existing database. One durable KDF slot across connections/processes;
there is deliberately no timeout that could overlap a still-running expensive KDF.
A process crash leaves admission closed until reviewed offline recovery.
"""
from contextlib import contextmanager
import hashlib
import hmac
import ipaddress
import secrets

from .credentials import phone_login
from .service import AccessService


STATEMENTS = (
    """CREATE TABLE access_admission_key (
        id INTEGER PRIMARY KEY CHECK(id=1), secret BLOB NOT NULL CHECK(length(secret)=32)
    )""",
    "INSERT INTO access_admission_key VALUES (1, randomblob(32))",
    """CREATE TABLE access_attempts (
        bucket TEXT PRIMARY KEY NOT NULL, expires_at INTEGER NOT NULL,
        attempts INTEGER NOT NULL CHECK(attempts > 0)
    )""",
    """CREATE TABLE access_kdf_slot (
        id INTEGER PRIMARY KEY CHECK(id=1), claim TEXT NOT NULL
    )""",
)


class AdmissionDenied(Exception):
    """Generic retry response, independent of account existence."""


def apply_schema(execute):
    for statement in STATEMENTS:
        execute(statement)


class Admission:
    WINDOW_SECONDS = 600
    GLOBAL_LIMIT = 60
    SOURCE_LIMIT = 20
    ACCOUNT_LIMIT = 6

    def __init__(self, service: AccessService):
        self.service = service

    def _buckets(self, source, phone):
        address = ipaddress.ip_address(source)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        try:
            canonical = phone_login(phone)
        except ValueError:
            canonical = '<invalid>'
        row = self.service.db.execute('SELECT secret FROM access_admission_key WHERE id=1').fetchone()
        if not row or not isinstance(row[0], bytes) or len(row[0]) != 32:
            raise AdmissionDenied()
        digest = lambda value: hmac.new(row[0], value.encode('utf-8'), hashlib.sha256).hexdigest()
        return [('global', self.GLOBAL_LIMIT),
                (digest('source:' + str(address)), self.SOURCE_LIMIT),
                (digest('phone:' + canonical), self.ACCOUNT_LIMIT)]

    @contextmanager
    def attempt(self, source: str, phone: str):
        """Count successful and failed attempts; share login/registration budgets.

        All counter changes commit even on denial. A single request cannot extend
        an existing window or reset another dimension. Expired keys are pruned
        only while reserving admission, so the global cap bounds table growth.
        """
        service = self.service
        claim = secrets.token_hex(16)
        allowed = True
        with service._transaction(write=True):
            now = service._now()
            buckets = self._buckets(source, phone)
            service.db.execute('DELETE FROM access_attempts WHERE expires_at<=?', (now,))
            for key, limit in buckets:
                row = service.db.execute('SELECT attempts FROM access_attempts WHERE bucket=?', (key,)).fetchone()
                if row and row[0] >= limit:
                    allowed = False
                    break
                service.db.execute('''INSERT INTO access_attempts VALUES (?,?,1)
                    ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1''',
                    (key, now + self.WINDOW_SECONDS))
            if allowed:
                result = service.db.execute('INSERT OR IGNORE INTO access_kdf_slot VALUES (1,?)', (claim,))
                allowed = result.rowcount == 1
        if not allowed:
            raise AdmissionDenied()
        try:
            yield
        finally:
            # No automatic stale-claim stealing: that would defeat the memory cap.
            with service._transaction(write=True):
                service.db.execute('DELETE FROM access_kdf_slot WHERE id=1 AND claim=?', (claim,))
