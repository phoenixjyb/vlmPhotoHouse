"""Family-authored text, separate from inference, scoped in the authorization transaction.

No model, filesystem, configuration or legacy handler imports. Search is literal,
bounded SQLite text search (including short Chinese queries), not semantic search.
"""
import hashlib
import json
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, SOURCE, _asset, _integer, _query
from .service import AccessDenied, AccessService
from .transport import TransportError, _body, _runtime, credentials_from_request

router = APIRouter(route_class=LibraryRoute)
CONTENT = {'title', 'text', 'language', 'byline'}
PAGE_SIZE = 5
TEXT_BYTES = 64 * 1024
# JSON may escape a one-byte character as six bytes. Keep complete 64 KiB text
# admissible without changing account/caption budgets. History includes a current
# story plus five revisions; six maximally escaped records fit within 3 MiB.
BODY_BYTES = 512 * 1024
RESPONSE_BYTES = 3 * 1024 * 1024


def _response(result, *, status_code=200):
    response = JSONResponse(result, status_code=status_code)
    if len(response.body) > RESPONSE_BYTES:
        raise TransportError(503, 'Story response unavailable')
    return response


def _uuid(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise TransportError(400, 'Invalid identifier') from None
    return value


def _content(body):
    for name, limit in (('title', 512), ('text', TEXT_BYTES), ('byline', 256)):
        value = body[name]
        if not isinstance(value, str) or len(value.encode('utf-8')) > limit or '\x00' in value:
            raise TransportError(422, 'Text exceeds the storage limit or contains invalid characters; nothing was saved')
    if not body['text'].strip() or body['language'] not in {'en', 'zh', 'mixed', 'und'}:
        raise TransportError(422, 'A story and a supported language are required')
    return {key: body[key] for key in sorted(CONTENT)}


class Stories:
    def __init__(self, access):
        self.access = access
        self.db = access.db

    def _parent(self, token, library, asset_id, *, write=False):
        member = self.access._require(token, library, 'story.write' if write else 'library.read')
        if self.db.execute('SELECT a.id' + SOURCE + ' AND a.id=?', (library, asset_id)).fetchone() is None:
            raise AccessDenied('Access denied')
        return member

    def _story(self, token, library, story_id, *, edit=False):
        # Authorize library first, and enforce BOTH child and parent scope.
        member = self.access._require(token, library, 'story.write' if edit else 'library.read')
        row = self.access._one('SELECT * FROM access_stories WHERE id=? AND library_id=?', (story_id, library))
        if row is None:
            raise AccessDenied('Access denied')
        self._parent(token, library, row['asset_id'], write=edit)
        if edit and member['role'] != 'owner' and row['author_id'] != member['account_id']:
            raise AccessDenied('Access denied')
        return row, member

    @staticmethod
    def _present(row, member):
        can_edit = member['role'] == 'owner' or (member['role'] == 'contributor' and row['author_id'] == member['account_id'])
        return {**{k: row[k] for k in ('id', 'title', 'text', 'language', 'byline', 'author_id',
                                     'revision', 'created_at', 'updated_at')},
                'asset_id': str(row['asset_id']), 'deleted': bool(row['deleted']),
                'can_edit': can_edit, 'can_view_history': can_edit, 'source': 'family'}

    def list(self, token, library, asset_id, page):
        with self.access._transaction():
            member = self._parent(token, library, asset_id)
            cursor = self.db.execute('''SELECT * FROM access_stories
                WHERE library_id=? AND asset_id=? AND deleted=0 ORDER BY created_at,id LIMIT ? OFFSET ?''',
                (library, asset_id, PAGE_SIZE + 1, (page-1)*PAGE_SIZE))
            rows = [dict(zip((c[0] for c in cursor.description), row)) for row in cursor]
            return {'asset_id': str(asset_id), 'library_id': library, 'page': page,
                    'can_create': member['role'] in {'owner', 'contributor'}, 'has_more': len(rows) > PAGE_SIZE,
                    'items': [self._present(row, member) for row in rows[:PAGE_SIZE]]}

    def history(self, token, library, story_id, page):
        with self.access._transaction():
            row, member = self._story(token, library, story_id, edit=True)
            cursor = self.db.execute('''SELECT revision,title,text,language,byline,editor_id,occurred_at,deleted
                FROM access_story_revisions WHERE story_id=? ORDER BY revision DESC LIMIT ? OFFSET ?''',
                (story_id, PAGE_SIZE+1, (page-1)*PAGE_SIZE))
            rows = [dict(zip((c[0] for c in cursor.description), r)) for r in cursor]
            return {'story': self._present(row, member), 'page': page,
                    'has_more': len(rows) > PAGE_SIZE, 'items': rows[:PAGE_SIZE]}

    def save(self, token, library, body, *, asset_id=None, story_id=None, delete=False):
        mutation = _uuid(body['mutation_id'])
        creating = asset_id is not None
        revision = 0 if creating else _integer(body['revision'], 2**63-2)
        content = None if delete else _content(body)
        digest = hashlib.sha256(json.dumps([library, asset_id, story_id, revision, delete, content],
                                          ensure_ascii=True, sort_keys=True).encode()).hexdigest()
        with self.access._transaction(write=True):
            if creating:
                member = self._parent(token, library, asset_id, write=True)
                row = None
            else:
                row, member = self._story(token, library, story_id, edit=True)
                asset_id = row['asset_id']
            actor = member['account_id']
            receipt = self.access._one('''SELECT story_id,request_digest FROM access_story_revisions
                WHERE editor_id=? AND mutation_id=?''', (actor, mutation))
            if receipt:
                if receipt['request_digest'] != digest:
                    raise TransportError(409, 'This save identifier was already used; reload before saving')
                current, member = self._story(token, library, receipt['story_id'], edit=True)
                return self._present(current, member)
            if not creating and (row['revision'] != revision or row['deleted']):
                raise TransportError(409, 'This story changed; keep your draft and reload before saving')
            now = self.access._now()
            if creating:
                story_id = str(uuid.uuid4())
                self.db.execute('''INSERT INTO access_stories
                    (id,asset_id,library_id,author_id,revision,title,text,language,byline,created_at,updated_at,deleted)
                    VALUES (?,?,?,?,1,?,?,?,?,?,?,0)''',
                    (story_id, asset_id, library, actor, content['title'], content['text'],
                     content['language'], content['byline'], now, now))
            else:
                if delete:
                    content = {key: row[key] for key in CONTENT}
                self.db.execute('''UPDATE access_stories SET revision=?,title=?,text=?,language=?,byline=?,updated_at=?,deleted=?
                    WHERE id=?''', (revision+1, content['title'], content['text'], content['language'],
                                   content['byline'], now, int(delete), story_id))
            self.db.execute('''INSERT INTO access_story_revisions
                (story_id,revision,editor_id,mutation_id,request_digest,title,text,language,byline,occurred_at,deleted)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (story_id, revision+1, actor, mutation, digest, content['title'], content['text'],
                 content['language'], content['byline'], now, int(delete)))
            self.access._audit(actor, 'story.delete' if delete else 'story.create' if creating else 'story.edit', library)
            return self._present(self.access._one('SELECT * FROM access_stories WHERE id=?', (story_id,)), member)

    def search(self, token, library, body):
        query = body['text'].strip()
        if not 1 <= len(query) <= 160 or '\x00' in query or body['source'] not in {'all', 'family', 'ai'} or body['media'] not in {'all', 'image', 'video'}:
            raise TransportError(422, 'Enter a search of 1–160 characters and valid filters')
        page = _integer(body['page'], 100000)
        pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        with self.access._transaction():
            self.access._require(token, library, 'library.read')
            # Scope every source before ranking/pagination. No TV projection or history.
            sql = '''WITH matches AS (
                SELECT a.id,a.mime,a.width,a.height,a.duration_sec,a.taken_at,s.id AS match_id,
                    'family' AS source, s.title || char(10) || s.text AS content, 2 AS priority
                FROM access_stories s JOIN assets a ON a.id=s.asset_id
                JOIN access_asset_libraries l ON l.asset_id=a.id
                WHERE l.library_id=:library AND s.library_id=l.library_id AND s.deleted=0
                AND (a.status IS NULL OR a.status='active') AND :source!='ai'
                AND (s.title LIKE :pattern ESCAPE '\\' OR s.text LIKE :pattern ESCAPE '\\')
                UNION ALL
                SELECT a.id,a.mime,a.width,a.height,a.duration_sec,a.taken_at,CAST(c.id AS TEXT),
                    CASE WHEN c.user_edited=1 THEN 'legacy_family' ELSE 'ai' END,c.text,
                    CASE WHEN c.user_edited=1 THEN 2 ELSE 1 END
                FROM captions c JOIN assets a ON a.id=c.asset_id
                JOIN access_asset_libraries l ON l.asset_id=a.id
                WHERE l.library_id=:library AND c.superseded=0 AND (a.status IS NULL OR a.status='active')
                AND (:source='all' OR (:source='ai' AND c.user_edited=0) OR (:source='family' AND c.user_edited=1))
                AND c.text LIKE :pattern ESCAPE '\\'
            ), ranked AS (
                SELECT *,row_number() OVER(PARTITION BY id ORDER BY priority DESC,match_id) AS n
                FROM matches WHERE :media='all' OR (:media='video' AND mime LIKE 'video/%')
                OR (:media='image' AND mime LIKE 'image/%')
            ) '''
            params = dict(library=library, source=body['source'], media=body['media'], pattern=pattern,
                          query=query, offset=(page-1)*24)
            deadline = time.monotonic() + 2
            self.db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            try:
                total = self.db.execute(sql + 'SELECT count(*) FROM ranked WHERE n=1', params).fetchone()[0]
                rows = self.db.execute(sql + '''SELECT id,mime,width,height,duration_sec,taken_at,source,match_id,
                    substr(content,max(1,instr(lower(content),lower(:query))-60),240)
                    FROM ranked WHERE n=1 ORDER BY priority DESC,taken_at DESC,id DESC LIMIT 24 OFFSET :offset''', params).fetchall()
            finally:
                self.db.set_progress_handler(None, 0)
            return {'library_id': library, 'page': page, 'page_size': 24, 'total': total,
                    'items': [{**_asset(row[:6], library), 'match': {'source': row[6], 'id': row[7], 'excerpt': row[8]}} for row in rows]}


def _call(runtime, action, *args, **kwargs):
    with runtime.connection_factory() as db:
        return getattr(Stories(AccessService(db, clock=runtime.clock)), action)(*args, **kwargs)


@router.get('/assets/{asset_id}/stories')
async def list_stories(asset_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page'})
    return _response(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'list', token,
        query['library'], _integer(asset_id, 2**63-1), _integer(query.get('page', '1'), 100000)))


@router.post('/assets/{asset_id}/stories')
async def create_story(asset_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, CONTENT | {'mutation_id'}, max_body=BODY_BYTES)
    return _response(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'save', token,
        query['library'], body, asset_id=_integer(asset_id, 2**63-1)), status_code=201)


@router.put('/stories/{story_id}')
async def update_story(story_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, CONTENT | {'mutation_id', 'revision'}, max_body=BODY_BYTES)
    return _response(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'save', token,
        query['library'], body, story_id=_uuid(story_id)))


@router.delete('/stories/{story_id}')
async def delete_story(story_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, {'mutation_id', 'revision'})
    return _response(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'save', token,
        query['library'], body, story_id=_uuid(story_id), delete=True))


@router.get('/stories/{story_id}/history')
async def story_history(story_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page'})
    return _response(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'history', token,
        query['library'], _uuid(story_id), _integer(query.get('page', '1'), 100000)))


@router.post('/library/search')
async def search_stories(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, {'text', 'source', 'media', 'page'})
    return _response(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'search', token, query['library'], body))
