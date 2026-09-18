"""Member-written captions, only where a photo has none.

The need is measured, not assumed: **3,203 of 27,842** active assets carry no caption, and **556**
caption tasks failed **permanently** on policy validation (283 English policy, 201 Chinese policy,
41 format, 24 word-count). The model produces text the policy rejects, so a retry yields the same
result and those photos stay undescribed forever. Nothing else in the protected surface lets the
family describe them.

Deliberately narrow:

* **Only where the asset has no current caption.** This cannot override a working AI description;
  it fills a gap. Replacing or removing an existing caption is a separate decision and stays
  unbuilt, so nothing here can take a description away.
* **`user_edited=1`**, which is the mechanism the pipeline already respects. Both the generation
  path and the refresh path return an existing user edit rather than overwriting it
  (`backend/app/tasks.py`, `scripts/refresh_captions.py`). Without that flag a later worker run
  could silently replace what a member wrote.
* **Any approved member**, matching the owner's upload decision. The alternative — contributor or
  owner, which is what `story.write` requires — is currently **unreachable**: an invitation
  creates a viewer and no route changes a role, so a contributor-gated write could never be used
  at all.
* **Attributed through the audit row**, not a new column. The `captions` table has no author
  field, and adding one would cost a migration for something the audit already records.

No delete, no regenerate, and no variant selection: the read already orders `user_edited` first,
so a written caption is the one a member sees.
"""
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, SOURCE, _integer, _query
from .service import AccessDenied, AccessService, Conflict
from .transport import TransportError, _body, _runtime, credentials_from_request

router = APIRouter(route_class=LibraryRoute)
CONTENT = {'text'}
BODY_BYTES = 8192
# Bounded so one row cannot dominate the caption response, which caps itself at 8192 characters
# per row and a total body budget. A description longer than this is not a description.
MAX_TEXT = 1024


class Captions:
    def __init__(self, access):
        self.access, self.db = access, access.db

    def write(self, token, library, asset_id, body):
        """Add a caption to an asset that has none, and return it."""
        text = body.get('text')
        if not isinstance(text, str):
            raise TransportError(400, 'Invalid caption')
        text = text.strip()
        # Control characters would corrupt the stored row and any later export; a caption is one
        # short human sentence, so newlines and tabs are refused rather than normalised.
        if not text or len(text) > MAX_TEXT or any(ord(c) < 32 for c in text):
            raise TransportError(400, 'Invalid caption')
        with self.access._transaction(write=True):
            member = self.access._require(token, library, 'caption.write')
            if self.db.execute('SELECT a.id' + SOURCE + ' AND a.id=?',
                               (library, asset_id)).fetchone() is None:
                raise AccessDenied('Access denied')
            # Refuse rather than replace: the whole point of this slice is to fill a gap, and a
            # silent overwrite of a working description is exactly what it must not do.
            if self.db.execute('''SELECT 1 FROM captions c JOIN assets a ON a.id=c.asset_id
                    JOIN access_asset_libraries scope ON scope.asset_id=a.id
                    WHERE scope.library_id=? AND a.id=? AND c.superseded=0 LIMIT 1''',
                    (library, asset_id)).fetchone() is not None:
                raise Conflict('This photo already has a description')
            cursor = self.db.execute('''INSERT INTO captions(asset_id,text,model,user_edited,superseded)
                VALUES(?,?,'member',1,0)''', (asset_id, text))
            caption_id = cursor.lastrowid
            self.access._audit(member['account_id'], 'caption.write', library)
            row = self.db.execute('SELECT id,text,user_edited,created_at,updated_at FROM captions'
                                  ' WHERE id=?', (caption_id,)).fetchone()
            return {'library_id': library, 'asset_id': str(asset_id),
                    'caption': {'id': str(row[0]), 'text': row[1], 'truncated': False,
                                'user_edited': bool(row[2]), 'created_at': row[3],
                                'updated_at': row[4]}}


def _call(runtime, action, *args, **kwargs):
    with runtime.connection_factory() as db:
        deadline = time.monotonic() + 3
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        try:
            return getattr(Captions(AccessService(db, clock=runtime.clock)), action)(*args, **kwargs)
        finally:
            db.set_progress_handler(None, 0)


@router.post('/assets/{asset_id}/captions')
async def write_caption(asset_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, CONTENT, max_body=BODY_BYTES)
    result = await run_in_threadpool(_call, _runtime(request, allow_query=True), 'write', token,
                                     query['library'], _integer(asset_id, 2**63 - 1), body)
    return JSONResponse(result, status_code=201)
