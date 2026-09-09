"""Additive SQLite access schema in PhotoHouse's existing database.

Explicit migration only: no engine, settings, legacy backfill or startup fallback.
Caller owns the transaction and enables foreign keys. Phone login is not SMS verified.
"""

STATEMENTS = (
    """CREATE TABLE access_accounts (
        id TEXT PRIMARY KEY NOT NULL,
        phone_login TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','disabled'))
    )""",
    """CREATE TABLE access_sessions (
        digest TEXT PRIMARY KEY NOT NULL,
        account_id TEXT NOT NULL REFERENCES access_accounts(id),
        expires_at INTEGER NOT NULL,
        revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0,1))
    )""",
    """CREATE TABLE access_operators (
        account_id TEXT PRIMARY KEY NOT NULL REFERENCES access_accounts(id)
    )""",
    """CREATE TABLE access_libraries (
        id TEXT PRIMARY KEY NOT NULL,
        state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','closed')),
        bootstrap_operator TEXT NOT NULL REFERENCES access_accounts(id)
    )""",
    """CREATE TABLE access_memberships (
        account_id TEXT NOT NULL REFERENCES access_accounts(id),
        library_id TEXT NOT NULL REFERENCES access_libraries(id),
        status TEXT NOT NULL CHECK(status IN ('requested','approved','rejected','revoked')),
        role TEXT NOT NULL CHECK(role IN ('viewer','contributor','owner')),
        revision INTEGER NOT NULL CHECK(revision > 0),
        expires_at INTEGER,
        originals INTEGER NOT NULL DEFAULT 0 CHECK(originals IN (0,1)),
        approved_by TEXT REFERENCES access_accounts(id),
        PRIMARY KEY(account_id, library_id),
        CHECK(status != 'approved' OR approved_by IS NOT NULL)
    )""",
    """CREATE TABLE access_invitations (
        digest TEXT PRIMARY KEY NOT NULL,
        library_id TEXT NOT NULL REFERENCES access_libraries(id),
        target_phone TEXT NOT NULL,
        target_account TEXT REFERENCES access_accounts(id),
        inviter_account TEXT NOT NULL REFERENCES access_accounts(id),
        inviter_revision INTEGER NOT NULL,
        target_revision INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        consumed INTEGER NOT NULL DEFAULT 0 CHECK(consumed IN (0,1)),
        cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1))
    )""",
    "CREATE INDEX ix_access_invitation_target ON access_invitations(library_id, target_phone)",
    """CREATE TABLE access_asset_libraries (
        asset_id INTEGER PRIMARY KEY REFERENCES assets(id),
        library_id TEXT NOT NULL REFERENCES access_libraries(id)
    )""",
    "CREATE INDEX ix_access_assets_library ON access_asset_libraries(library_id, asset_id)",
    """CREATE TABLE access_audit (
        id INTEGER PRIMARY KEY,
        actor_account TEXT NOT NULL REFERENCES access_accounts(id),
        action TEXT NOT NULL,
        library_id TEXT REFERENCES access_libraries(id),
        target_account TEXT REFERENCES access_accounts(id),
        occurred_at INTEGER NOT NULL
    )""",
)


def apply_schema(execute):
    """Apply the reviewed statements within the caller's explicit transaction."""
    for statement in STATEMENTS:
        execute(statement)
