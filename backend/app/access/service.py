"""First-party phone-as-username/password and manually delivered invitations.

Dormant until HTTP/worker integration is reviewed. No SMS, WeChat, OAuth server,
email delivery, model, filesystem media access, settings or database-opening API.
The connection must be to the existing PhotoHouse SQLite database. HTTP admission,
TLS, cookies/CSRF and password recovery are separate, mandatory delivery gates.
"""
from contextlib import contextmanager
import math
import secrets
import sqlite3
import time
import uuid

from .credentials import (DUMMY_HASH, hash_password, invitation_code, invitation_digest,
                          phone_login, session_digest, verify_password)


class AccessDenied(Exception):
    """Non-enumerating denial; HTTP adapters must not reveal the underlying reason."""


class Conflict(Exception):
    """Authorized owner must refresh stale membership state before retrying."""


class AccessService:
    SESSION_SECONDS = 86400

    def __init__(self, connection: sqlite3.Connection, *, clock=time.time):
        if connection.in_transaction:
            raise ValueError('AccessService requires a connection without a pending transaction')
        if connection.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
            raise ValueError('SQLite foreign_keys must be enabled by the connection owner')
        self.db = connection
        self.clock = clock

    def _now(self):
        value = self.clock()
        if not math.isfinite(value):
            raise AccessDenied('Access denied')
        return int(value)

    @contextmanager
    def _transaction(self, *, write=False):
        if self.db.in_transaction:
            raise ValueError('AccessService must own its transaction')
        self.db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def _one(self, sql, args=()):
        cursor = self.db.execute(sql, args)
        row = cursor.fetchone()
        return dict(zip((c[0] for c in cursor.description), row)) if row is not None else None

    def _session(self, token):
        try:
            digest = session_digest(token)
        except ValueError:
            raise AccessDenied('Access denied') from None
        row = self._one('''SELECT s.*, a.state, a.phone_login FROM access_sessions s
            JOIN access_accounts a ON a.id=s.account_id WHERE s.digest=?''', (digest,))
        if not row or row['revoked'] or row['state'] != 'active' or row['expires_at'] <= self._now():
            raise AccessDenied('Access denied')
        return row

    def _member(self, token, library_id, *, owner=False, expected_revision=None):
        session = self._session(token)
        row = self._one('''SELECT m.* FROM access_memberships m
            JOIN access_libraries l ON l.id=m.library_id
            WHERE m.account_id=? AND m.library_id=? AND l.state='active' ''',
            (session['account_id'], library_id))
        if (not row or row['status'] != 'approved'
                or (row['expires_at'] is not None and row['expires_at'] <= self._now())
                or (owner and row['role'] != 'owner')):
            raise AccessDenied('Access denied')
        if expected_revision is not None and row['revision'] != expected_revision:
            raise AccessDenied('Access denied')
        return row

    def _audit(self, account_id, action, library_id=None, target=None):
        self.db.execute('''INSERT INTO access_audit
            (actor_account,action,library_id,target_account,occurred_at) VALUES (?,?,?,?,?)''',
            (account_id, action, library_id, target, self._now()))

    def _new_session(self, account_id):
        token = secrets.token_urlsafe(32)
        self.db.execute('INSERT INTO access_sessions(digest,account_id,expires_at) VALUES (?,?,?)',
                        (session_digest(token), account_id, self._now() + self.SESSION_SECONDS))
        return token  # Return once to the transport; never persist/log the raw token.

    def login(self, phone: str, password: str):
        try:
            canonical = phone_login(phone)
        except ValueError:
            canonical = ''
        with self._transaction():
            account = self._one('SELECT * FROM access_accounts WHERE phone_login=?', (canonical,))
        valid = verify_password(password, account['password_hash'] if account else DUMMY_HASH)
        if not valid or not account or account['state'] != 'active':
            raise AccessDenied('Access denied')
        with self._transaction(write=True):
            # A disable/password change concurrent with hashing must invalidate login.
            current = self._one("SELECT * FROM access_accounts WHERE id=? AND state='active'", (account['id'],))
            if not current or current['password_hash'] != account['password_hash']:
                raise AccessDenied('Access denied')
            token = self._new_session(account['id'])
            self._audit(account['id'], 'login')
            return token

    def invite(self, owner_token: str, library_id: str, phone: str, *, lifetime=86400):
        """Owner creates a phone-bound code before registration and sends it manually."""
        canonical = phone_login(phone)
        if type(lifetime) is not int or not 1 <= lifetime <= 7 * 86400:
            raise ValueError('Invitation lifetime must be 1..604800 seconds')
        code = invitation_code()
        with self._transaction(write=True):
            owner = self._member(owner_token, library_id, owner=True)
            target = self._one('SELECT * FROM access_accounts WHERE phone_login=?', (canonical,))
            if target and target['state'] != 'active':
                raise AccessDenied('Access denied')
            member = self._one('SELECT * FROM access_memberships WHERE account_id=? AND library_id=?',
                               (target['id'], library_id)) if target else None
            if member and member['status'] == 'approved':
                raise Conflict('Account already has approved membership')
            # Reissuing replaces every older unused code for this phone/library.
            self.db.execute('''UPDATE access_invitations SET cancelled=1
                WHERE library_id=? AND target_phone=? AND consumed=0''', (library_id, canonical))
            self.db.execute('''INSERT INTO access_invitations
                (digest,library_id,target_phone,target_account,inviter_account,inviter_revision,target_revision,expires_at)
                VALUES (?,?,?,?,?,?,?,?)''', (invitation_digest(code), library_id, canonical,
                target['id'] if target else None, owner['account_id'], owner['revision'],
                member['revision'] if member else 0, self._now() + lifetime))
            self._audit(owner['account_id'], 'invite', library_id, target['id'] if target else None)
        return code

    def cancel_invitation(self, owner_token: str, library_id: str, code: str):
        try:
            digest = invitation_digest(code)
        except ValueError:
            raise AccessDenied('Access denied') from None
        with self._transaction(write=True):
            owner = self._member(owner_token, library_id, owner=True)
            self.db.execute('UPDATE access_invitations SET cancelled=1 WHERE digest=? AND library_id=?',
                            (digest, library_id))
            self._audit(owner['account_id'], 'cancel_invitation', library_id)

    def _invitation(self, canonical, digest):
        invite = self._one('SELECT * FROM access_invitations WHERE digest=? AND target_phone=?',
                           (digest, canonical))
        if not invite or invite['consumed'] or invite['cancelled'] or invite['expires_at'] <= self._now():
            raise AccessDenied('Access denied')
        owner = self._one('''SELECT m.*, a.state AS account_state, l.state AS library_state
            FROM access_memberships m JOIN access_accounts a ON a.id=m.account_id
            JOIN access_libraries l ON l.id=m.library_id WHERE m.account_id=? AND m.library_id=?''',
            (invite['inviter_account'], invite['library_id']))
        if (not owner or owner['account_state'] != 'active' or owner['library_state'] != 'active'
                or owner['status'] != 'approved' or owner['role'] != 'owner'
                or owner['revision'] != invite['inviter_revision']
                or (owner['expires_at'] is not None and owner['expires_at'] <= self._now())):
            raise AccessDenied('Access denied')
        return invite

    def _activate(self, account_id, invite):
        if invite['target_account'] is not None and invite['target_account'] != account_id:
            raise AccessDenied('Access denied')
        member = self._one('SELECT * FROM access_memberships WHERE account_id=? AND library_id=?',
                           (account_id, invite['library_id']))
        if (member['revision'] if member else 0) != invite['target_revision']:
            raise AccessDenied('Access denied')
        if member and (member['role'] == 'owner' or member['status'] == 'approved'):
            raise AccessDenied('Access denied')
        self.db.execute('''INSERT INTO access_memberships
            (account_id,library_id,status,role,revision,approved_by) VALUES (?,?,'approved','viewer',1,?)
            ON CONFLICT(account_id,library_id) DO UPDATE SET status='approved',role='viewer',
            revision=revision+1,approved_by=excluded.approved_by,originals=0,expires_at=NULL''',
            (account_id, invite['library_id'], invite['inviter_account']))
        self.db.execute('UPDATE access_invitations SET consumed=1 WHERE digest=?', (invite['digest'],))
        self._audit(account_id, 'accept_invitation', invite['library_id'], account_id)

    def register(self, phone: str, password: str, code: str):
        """Atomically create account + approved viewer membership + consume code.

        No account is created without a valid owner invitation. Existing-account
        invitations require login and accept_invitation; never reset a password.
        """
        try:
            canonical, digest = phone_login(phone), invitation_digest(code)
        except ValueError:
            raise AccessDenied('Access denied') from None
        with self._transaction():
            self._invitation(canonical, digest)
            if self._one('SELECT id FROM access_accounts WHERE phone_login=?', (canonical,)):
                raise AccessDenied('Access denied')
        encoded = hash_password(password)  # Expensive work outside the write lock.
        with self._transaction(write=True):
            invite = self._invitation(canonical, digest)  # Expiry/revocation/replay checked again.
            if self._one('SELECT id FROM access_accounts WHERE phone_login=?', (canonical,)):
                raise AccessDenied('Access denied')
            account_id = str(uuid.uuid4())
            self.db.execute('INSERT INTO access_accounts(id,phone_login,password_hash) VALUES (?,?,?)',
                            (account_id, canonical, encoded))
            self._activate(account_id, invite)
            return self._new_session(account_id)

    def accept_invitation(self, token: str, code: str):
        try:
            digest = invitation_digest(code)
        except ValueError:
            raise AccessDenied('Access denied') from None
        with self._transaction(write=True):
            session = self._session(token)
            invite = self._invitation(session['phone_login'], digest)
            self._activate(session['account_id'], invite)

    def profile(self, token: str):
        with self._transaction():
            session = self._session(token)
            rows = self.db.execute('''SELECT m.library_id,m.status,m.role,m.revision,m.expires_at,m.originals,
                (m.status='approved' AND l.state='active' AND (m.expires_at IS NULL OR m.expires_at>?)) AS available
                FROM access_memberships m JOIN access_libraries l ON l.id=m.library_id
                WHERE m.account_id=? ORDER BY m.library_id''', (self._now(), session['account_id']))
            memberships = [dict(zip(('library_id','status','role','revision','expires_at','originals','available'), r))
                           for r in rows]
            for member in memberships:
                member['available'] = bool(member['available'])
            return {'account_id': session['account_id'], 'phone_login': session['phone_login'],
                    'memberships': memberships}

    def decide_membership(self, owner_token: str, library_id: str, target_account: str, *,
                          expected_revision: int, status: str, originals=False, expires_at=None):
        if status not in {'approved', 'rejected', 'revoked'} or type(originals) is not bool:
            raise ValueError('Unsupported membership decision')
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError('Explicit membership revision required')
        if expires_at is not None and (type(expires_at) is not int or expires_at <= self._now()):
            raise ValueError('Invalid membership expiry')
        with self._transaction(write=True):
            owner = self._member(owner_token, library_id, owner=True)
            target = self._one('SELECT * FROM access_memberships WHERE account_id=? AND library_id=?',
                               (target_account, library_id))
            # Owner transfer/recovery is a separate operation. This cannot remove the last owner.
            if not target or target['role'] == 'owner':
                raise AccessDenied('Access denied')
            if target['revision'] != expected_revision:
                raise Conflict('Membership changed')
            self.db.execute('''UPDATE access_memberships SET status=?,originals=?,expires_at=?,
                approved_by=?,revision=revision+1 WHERE account_id=? AND library_id=?''',
                (status, int(originals) if status == 'approved' else 0, expires_at,
                 owner['account_id'], target_account, library_id))
            self._audit(owner['account_id'], 'membership.' + status, library_id, target_account)

    def logout(self, token: str):
        try:
            digest = session_digest(token)
        except ValueError:
            return
        with self._transaction(write=True):
            self.db.execute('UPDATE access_sessions SET revoked=1 WHERE digest=?', (digest,))

    def _require(self, token, library_id, capability, expected_revision=None):
        member = self._member(token, library_id, expected_revision=expected_revision)
        if capability == 'library.read':
            return member
        if capability == 'media.original.read' and member['originals']:
            return member
        if capability == 'library.members.manage' and member['role'] == 'owner':
            return member
        # Upload/curation/destruction/voice grants remain disabled in the first release.
        raise AccessDenied('Access denied')

    def require(self, token: str, library_id: str, capability: str, *, expected_revision=None):
        with self._transaction():
            return self._require(token, library_id, capability, expected_revision)['revision']

    def require_operator(self, token: str):
        with self._transaction():
            session = self._session(token)
            if not self._one('SELECT account_id FROM access_operators WHERE account_id=?', (session['account_id'],)):
                raise AccessDenied('Access denied')

    def asset_metadata(self, token: str, library_id: str, asset_id: int, *, original=False, expected_revision=None):
        with self._transaction():
            self._require(token, library_id, 'media.original.read' if original else 'library.read', expected_revision)
            row = self._one('''SELECT a.id, a.path FROM assets a JOIN access_asset_libraries scope ON scope.asset_id=a.id
                WHERE scope.library_id=? AND a.id=? AND (a.status IS NULL OR a.status='active')''',
                (library_id, asset_id))
            if not row:
                raise AccessDenied('Access denied')
            return row  # Internal only; the HTTP layer must not expose filesystem paths.

    def list_asset_ids(self, token: str, library_id: str, *, limit=50, offset=0):
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
            raise ValueError('Invalid pagination')
        with self._transaction():
            self._require(token, library_id, 'library.read')
            source = ''' FROM assets a JOIN access_asset_libraries scope ON scope.asset_id=a.id
                WHERE scope.library_id=? AND (a.status IS NULL OR a.status='active')'''
            total = self.db.execute('SELECT COUNT(*)' + source, (library_id,)).fetchone()[0]
            ids = [row[0] for row in self.db.execute('SELECT a.id' + source + ' ORDER BY a.id LIMIT ? OFFSET ?',
                                                    (library_id, limit, offset))]
            return {'total': total, 'asset_ids': ids}
