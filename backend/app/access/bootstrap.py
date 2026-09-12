"""Offline operator-only owner bootstrap. Never expose as an HTTP signup action."""
import uuid

from .credentials import hash_password, phone_login
from .service import AccessService, Conflict


def bootstrap_owner(connection, *, phone: str, password: str, library_id: str):
    """An operator with direct DB authority explicitly selects the first owner.

    Creates a NEW owner account and library, only once for that phone/library.
    No originals or existing rows are assigned. No default phone/password/owner.
    Returns account ID only; user logs in normally to obtain a session.
    """
    if not isinstance(library_id, str) or not library_id.strip():
        raise ValueError('Explicit library ID required')
    canonical, encoded = phone_login(phone), hash_password(password)
    service = AccessService(connection)
    with service._transaction(write=True):
        if service._one('SELECT id FROM access_libraries WHERE id=?', (library_id,)) or service._one(
                'SELECT id FROM access_accounts WHERE phone_login=?', (canonical,)):
            raise Conflict('Owner/library already bootstrapped; use reviewed recovery')
        account_id = str(uuid.uuid4())
        connection.execute('INSERT INTO access_accounts(id,phone_login,password_hash) VALUES (?,?,?)',
                           (account_id, canonical, encoded))
        connection.execute('INSERT INTO access_operators(account_id) VALUES (?)', (account_id,))
        connection.execute('INSERT INTO access_libraries(id,bootstrap_operator) VALUES (?,?)', (library_id, account_id))
        connection.execute('''INSERT INTO access_memberships(account_id,library_id,status,role,revision,approved_by)
            VALUES (?,?,'approved','owner',1,?)''', (account_id, library_id, account_id))
        service._audit(account_id, 'bootstrap_owner', library_id, account_id)
        return account_id
