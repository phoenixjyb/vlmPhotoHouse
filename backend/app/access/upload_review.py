"""Explicit operator/owner inbox for single-photo, sealed upload approval.

Pending bytes stay outside normal media roots. An admin can see uploads only from
current members of the selected library; system operator status alone grants no
family access. No anonymous TV publication, original download, or job retry.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import time
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, _integer, _query
from .promotion import (PROMOTE_OPERATION, PromotionPlanner, PromotionReview,
                        _operator, promote_and_assign)
from .provisioning import PlanRejected
from .provisioning_apply import _identity, plan_digest
from .runtime import ExistingDatabase
from .service import AccessDenied, AccessService
from .transport import TransportError, _body, _runtime, credentials_from_request
from .upload import UploadRuntime
from .resumable import MAX_IMAGE_BYTES, MAX_VIDEO_BYTES
from ..home_feed import Refused
from ..photo_delivery import PhotoCache, source_pin

router = APIRouter(route_class=LibraryRoute)
SOURCE = ''' FROM access_uploads u JOIN assets a ON a.id=u.asset_id
    JOIN access_accounts p ON p.id=u.account_id
    JOIN access_memberships m ON m.account_id=p.id AND m.library_id=?
    LEFT JOIN access_asset_libraries scope ON scope.asset_id=a.id
    WHERE p.state='active' AND m.status='approved'
    AND (m.expires_at IS NULL OR m.expires_at>?)
    AND (a.status IS NULL OR a.status='active')'''
PENDING = " AND u.state='incoming' AND scope.asset_id IS NULL"


@dataclass(frozen=True)
class UploadReviewRuntime:
    upload: UploadRuntime
    photo_cache: object = None

    def __post_init__(self):
        # Multiple original roots require an explicit future destination policy.
        if (not isinstance(self.upload, UploadRuntime)
                or not isinstance(self.upload.access.connection_factory, ExistingDatabase)
                or len(self.upload.original_roots) != 1):
            raise ValueError('One explicit upload destination and database required')

    @property
    def database(self):
        return self.upload.access.connection_factory.path

    def _service(self, db):
        return AccessService(db, clock=self.upload.access.clock)

    def _owner(self, access, token, library, *, operator=True):
        member = access._member(token, library, owner=True)
        if operator:
            try:
                _operator(access.db, member['account_id'], library, access._now())
            except PlanRejected:
                raise AccessDenied('Access denied') from None
        return member['account_id']

    def _item(self, access, library, asset, *, allow_assigned=False):
        row = access.db.execute('''SELECT a.path,u.incoming_label,u.batch,u.sha256,u.bytes,
            a.mime,a.hash_sha256,a.file_size,u.state,scope.library_id''' + SOURCE + ' AND a.id=?',
            (library, access._now(), asset)).fetchone()
        if row is None or not (row[8:] == ('incoming', None) or
                (allow_assigned and row[8:] == ('assigned', library))):
            raise AccessDenied('Access denied')
        if (row[3] != row[6] or row[4] != row[7] or not 0 < row[4] <= (MAX_VIDEO_BYTES if row[5] and row[5].startswith('video/') else MAX_IMAGE_BYTES)
                or row[5] not in {'image/jpeg', 'image/png','video/mp4','video/quicktime'}):
            raise TransportError(409, 'Upload changed; review again')
        return row

    def _pending_path(self, row):
        suffix = {'image/jpeg':'.jpg','image/png':'.png','video/mp4':'.mp4','video/quicktime':'.mov'}[row[5]]
        root = self.upload.incoming_root
        path = Path(row[0])
        if (not row[1] or Path(row[1]).name != row[1] or row[1] in {'.', '..'}
                or '/' in row[1] or '\\' in row[1]
                or re.fullmatch('[0-9a-f]{32}', row[2]) is None
                or re.fullmatch('[0-9a-f]{64}', row[3]) is None
                or path != root / row[1] / row[2] / (row[3] + suffix)
                or not path.is_relative_to(root) or '..' in path.parts):
            raise TransportError(409, 'Upload changed; review again')
        return path

    def list(self, token, library, page):
        with ExistingDatabase(self.database, read_only=True)() as db:
            deadline = time.monotonic() + 3
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            access = self._service(db)
            with access._transaction():
                actor = self._owner(access, token, library, operator=False)
                permitted = db.execute('SELECT 1 FROM access_operators WHERE account_id=?', (actor,)).fetchone() is not None
                result = dict(library_id=library, page=page, page_size=10, total=0,
                              can_review=permitted, items=[])
                if not permitted:
                    return result
                args = (library, access._now())
                result['total'] = db.execute('SELECT count(*)' + SOURCE + PENDING, args).fetchone()[0]
                rows = db.execute('''SELECT a.id,substr(p.display_name,1,160),u.created_at,
                    u.bytes,a.width,a.height,a.mime''' + SOURCE + PENDING +
                    ' ORDER BY u.id DESC LIMIT 10 OFFSET ?', (*args, (page-1)*10)).fetchall()
                result['items'] = [dict(id=str(r[0]), uploader=r[1] or '',
                    created_at=datetime.fromtimestamp(r[2], timezone.utc).isoformat(),
                    bytes=r[3], width=r[4], height=r[5],kind='video' if r[6].startswith('video/') else 'image',
                    preview_url=f'/admin/uploads/{r[0]}/preview?' + urlencode({'library': library})) for r in rows]
                return result

    def review(self, token, library, asset):
        with ExistingDatabase(self.database, read_only=True)() as db:
            access = self._service(db)
            with access._transaction():
                actor = self._owner(access, token, library)
                self._item(access, library, asset)
            # Planner owns its own snapshot and seals all asset and audience revisions.
            envelope = PromotionPlanner(db, clock=access.clock).promote(
                library_id=library, operator_account_id=actor, asset_ids=[asset])
            with access._transaction():
                self._owner(access, token, library)
                self._item(access, library, asset)
            expected = envelope['plan']['expected']
            return dict(asset_id=str(asset), library_id=library,
                plan=json.dumps(envelope, separators=(',', ':')),
                current_readers=expected['current_readers'],
                current_original_readers=expected['current_original_readers'])

    def approve(self, token, library, asset, raw):
        try:
            envelope = json.loads(raw)
            plan = envelope['plan']
            if (plan['operation'] != PROMOTE_OPERATION or
                    set(plan['target']) != {'library_id', 'operator_account_id', 'asset_ids'} or
                    plan['target']['library_id'] != library or plan['target']['asset_ids'] != [str(asset)]):
                raise ValueError()
        except (ValueError, TypeError, KeyError, RecursionError):
            raise TransportError(400, 'Invalid review') from None

        def authorize(access, checked):
            actor = self._owner(access, token, library)
            if actor != checked['target']['operator_account_id']:
                raise AccessDenied('Access denied')
            row = self._item(access, library, asset, allow_assigned=True)
            if row[8] == 'incoming':
                self._pending_path(row)

        review = PromotionReview(database=self.database, database_identity=_identity(self.database),
            plan_digest=plan_digest(envelope), authority_reference='web-upload-review',
            incoming_root=self.upload.incoming_root, originals_root=self.upload.original_roots[0])
        promote_and_assign(envelope, review=review, clock=self.upload.access.clock,
                           authorize=authorize, allow_replay=True)
        return dict(asset_id=str(asset), library_id=library, state='assigned')

    def preview(self, token, library, asset):
        with ExistingDatabase(self.database, read_only=True)() as db:
            access = self._service(db)
            with access._transaction():
                self._owner(access, token, library)
                row = self._item(access, library, asset)
                path = self._pending_path(row)
        if row[5].startswith('video/'):
            raise TransportError(404, 'Video preview pending preparation')
        if not isinstance(self.photo_cache, PhotoCache):
            raise TransportError(503, 'Preview unavailable')
        try:
            pin = source_pin(path, (self.upload.incoming_root,))
            if pin[2] != row[4]:
                raise TransportError(409, 'Upload changed; review again')
            raw = self.photo_cache.render(path, (self.upload.incoming_root,), pin, 'grid')
            # Decoding is outside SQLite; authorize again after the bounded worker completes.
            with ExistingDatabase(self.database, read_only=True)() as db:
                access = self._service(db)
                with access._transaction():
                    self._owner(access, token, library)
                    fresh = self._item(access, library, asset)
                    if fresh != row:
                        raise TransportError(409, 'Upload changed; review again')
                    source_pin(path, (self.upload.incoming_root,), pin)
            return raw
        except Refused as error:
            raise TransportError(error.status, 'Preview unavailable') from None


def _review_runtime(request):
    _runtime(request, allow_query=True)
    runtime = getattr(request.app.state, 'upload_review_runtime', None)
    if not isinstance(runtime, UploadReviewRuntime):
        raise TransportError(503, 'Upload review unavailable')
    return runtime


def _call(runtime, action, *args):
    try:
        return getattr(runtime, action)(*args)
    except PlanRejected:
        raise TransportError(409, 'Upload or audience changed; review again') from None


@router.get('/admin/uploads')
async def upload_inbox(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page'})
    result = await run_in_threadpool(_call, _review_runtime(request), 'list', token,
        query['library'], _integer(query.get('page', '1'), 100000))
    return JSONResponse(result)


@router.get('/admin/uploads/{asset_id}/preview')
async def upload_preview(asset_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    raw = await run_in_threadpool(_call, _review_runtime(request), 'preview', token,
        query['library'], _integer(asset_id, 2**63-1))
    return Response(raw, media_type='image/jpeg')


@router.post('/admin/uploads/{asset_id}/review')
async def review_upload(asset_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    await _body(request, set())
    result = await run_in_threadpool(_call, _review_runtime(request), 'review', token,
        query['library'], _integer(asset_id, 2**63-1))
    return JSONResponse(result)


@router.post('/admin/uploads/{asset_id}/approve')
async def approve_upload(asset_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, {'plan'})
    result = await run_in_threadpool(_call, _review_runtime(request), 'approve', token,
        query['library'], _integer(asset_id, 2**63-1), body['plan'])
    return JSONResponse(result)
