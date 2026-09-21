"""Named library presets and explicit, reviewed asset transfers.

No startup provisioning, membership copying, media writes or Home publication.
Names are public product presets; authorization always uses stored memberships.
"""
import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, _integer, _query
from .promotion import PromotionPlanner, PromotionReview, REASSIGN_OPERATION, reassign_assets
from .provisioning import PlanRejected, _library
from .provisioning_apply import _identity, plan_digest
from .runtime import ExistingDatabase
from .service import AccessDenied, AccessService
from .transport import TransportError, _body, _runtime, credentials_from_request

router = APIRouter(route_class=LibraryRoute)
PRESETS = {
    'yanbo-work': ("Yanbo’s Work", '砚波的工作'),
    'documents': ('Documents', '文档'),
    'chuan-work': ("Chuan’s Work", '曹川的工作'),
    'scenery': ('Scenery', '风景'),
    'concerts': ('Concerts', '音乐会'),
}


def labels(library):
    en, zh = PRESETS.get(library, ('Family', '家庭') if library in {'family', 'family-a'} else (library, library))
    return dict(id=library, title=en, title_zh=zh)


def create_presets(access, actor):
    """Explicit operator command, called inside a write transaction.

    New libraries start with only the named operator as owner. Existing libraries
    are never claimed or changed. Repeating this command is safe for that owner.
    """
    db = access.db
    if not db.in_transaction or db.execute('''SELECT 1 FROM access_operators o
        JOIN access_accounts a ON a.id=o.account_id WHERE a.id=? AND a.state='active' ''', (actor,)).fetchone() is None:
        raise AccessDenied('Access denied')
    created = []
    for library in PRESETS:
        row = db.execute('SELECT bootstrap_operator,state FROM access_libraries WHERE id=?', (library,)).fetchone()
        if row is not None:
            member = db.execute('''SELECT 1 FROM access_memberships WHERE account_id=? AND library_id=?
                AND status='approved' AND role='owner' AND (expires_at IS NULL OR expires_at>?)''',
                (actor, library, access._now())).fetchone()
            if tuple(row) != (actor, 'active') or member is None:
                raise TransportError(409, 'Library already exists; review ownership')
            continue
        db.execute('INSERT INTO access_libraries(id,state,bootstrap_operator) VALUES (?,\'active\',?)', (library, actor))
        db.execute('''INSERT INTO access_memberships
            (account_id,library_id,status,role,revision,expires_at,originals,approved_by)
            VALUES (?,?,'approved','owner',1,NULL,0,?)''', (actor, library, actor))
        access._audit(actor, 'library.create', library)
        created.append(library)
    return dict(created=created, items=[labels(library) for library in PRESETS])


class LibraryOrganization:
    def __init__(self, runtime):
        self.runtime = runtime

    def _operator(self, access, token, library):
        member = access._member(token, library, owner=True)
        if access.db.execute('SELECT 1 FROM access_operators WHERE account_id=?', (member['account_id'],)).fetchone() is None:
            raise AccessDenied('Access denied')
        return member['account_id']

    def catalogue(self, token):
        with self.runtime.connection_factory() as db:
            deadline = time.monotonic() + 3
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            access = AccessService(db, clock=self.runtime.clock)
            with access._transaction():
                account = access._session(token)['account_id']
                operator = db.execute('SELECT 1 FROM access_operators WHERE account_id=?', (account,)).fetchone() is not None
                rows = db.execute('''SELECT m.library_id,m.role FROM access_memberships m
                    JOIN access_libraries l ON l.id=m.library_id
                    WHERE m.account_id=? AND m.status='approved' AND l.state='active'
                    AND (m.expires_at IS NULL OR m.expires_at>?) ORDER BY m.library_id LIMIT 101''',
                    (account, access._now())).fetchall()
                if len(rows) > 100:
                    raise TransportError(503, 'Library catalogue unavailable')
                items = []
                for library, role in rows:
                    count = db.execute('''SELECT count(*) FROM access_asset_libraries s JOIN assets a ON a.id=s.asset_id
                        WHERE s.library_id=? AND (a.status IS NULL OR a.status='active')''', (library,)).fetchone()[0]
                    items.append(dict(**labels(library), role=role, asset_count=count, can_manage=operator and role == 'owner'))
                return dict(items=items, can_create=operator)

    def destinations(self, token, source):
        with self.runtime.connection_factory() as db:
            access = AccessService(db, clock=self.runtime.clock)
            with access._transaction():
                member = access._member(token, source, owner=True)
                can_move = db.execute('SELECT 1 FROM access_operators WHERE account_id=?', (member['account_id'],)).fetchone() is not None
        if not can_move:
            return dict(can_move=False, items=[])
        return dict(can_move=True, items=[item for item in self.catalogue(token)['items']
                                         if item['id'] != source and item['can_manage']])

    def review(self, token, source, body):
        destination = _library(body['destination'])
        values = [_integer(value, 2**63-1) for value in body['asset_ids'].split(',')]
        if not 1 <= len(values) <= 50 or len(set(values)) != len(values) or destination == source:
            raise TransportError(400, 'Select up to 50 different assets and another library')
        factory = self.runtime.connection_factory
        if not isinstance(factory, ExistingDatabase):
            raise TransportError(503, 'Library moves unavailable')
        with ExistingDatabase(factory.path, read_only=True)() as db:
            deadline = time.monotonic() + 3
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            access = AccessService(db, clock=self.runtime.clock)
            with access._transaction():
                actor = self._operator(access, token, source)
                self._operator(access, token, destination)
                for asset in values:
                    if db.execute('SELECT library_id FROM access_asset_libraries WHERE asset_id=?', (asset,)).fetchone() != (source,):
                        raise AccessDenied('Access denied')
            envelope = PromotionPlanner(db, clock=access.clock).reassign(
                library_id=destination, operator_account_id=actor, asset_ids=values)
            expected = envelope['plan']['expected']
            if expected['source_libraries'] != [source]:
                raise TransportError(409, 'Selection changed; review again')
            with access._transaction():
                self._operator(access, token, source)
                self._operator(access, token, destination)
            return dict(plan=json.dumps(envelope, separators=(',', ':')), asset_count=len(values),
                story_count=expected['story_count'], affected_album_count=expected['source_album_count'],
                face_count=expected['face_count'], current_readers=expected['current_readers'],
                current_original_readers=expected['current_original_readers'],
                source_library=source, destination_library=destination)

    def confirm(self, token, source, raw):
        try:
            envelope = json.loads(raw)
            plan = envelope['plan']
            if (plan['operation'] != REASSIGN_OPERATION or plan['expected']['source_libraries'] != [source]
                    or not 1 <= len(plan['target']['asset_ids']) <= 50):
                raise ValueError()
            destination = _library(plan['target']['library_id'])
        except (ValueError, TypeError, KeyError, RecursionError):
            raise TransportError(400, 'Invalid review') from None
        factory = self.runtime.connection_factory
        if not isinstance(factory, ExistingDatabase):
            raise TransportError(503, 'Library moves unavailable')

        deadline = time.monotonic() + 3
        def authorize(access, checked):
            access.db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            actor = self._operator(access, token, source)
            self._operator(access, token, destination)
            if actor != checked['target']['operator_account_id']:
                raise AccessDenied('Access denied')

        review = PromotionReview(database=factory.path, database_identity=_identity(factory.path),
            plan_digest=plan_digest(envelope), authority_reference='web-library-move')
        result = reassign_assets(envelope, review=review, clock=self.runtime.clock,
                                 authorize=authorize, allow_replay=True)
        return dict(state='moved', asset_count=result['asset_count'], library_id=destination)


def _call(runtime, action, *args):
    try:
        return getattr(LibraryOrganization(runtime), action)(*args)
    except PlanRejected:
        raise TransportError(409, 'Asset or audience changed; review again') from None


@router.get('/library-catalogue')
async def catalogue(request: Request):
    token, _ = credentials_from_request(request)
    return JSONResponse(await run_in_threadpool(_call, _runtime(request), 'catalogue', token))


@router.get('/admin/library-transfers')
async def destinations(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'destinations', token, query['library']))


@router.post('/admin/library-transfers/review')
async def review(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, {'asset_ids', 'destination'})
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'review', token, query['library'], body))


@router.post('/admin/library-transfers/confirm')
async def confirm(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, {'plan'}, max_body=16384)
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'confirm', token, query['library'], body['plan']))
