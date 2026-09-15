"""Owner-only, library-scoped people review and conservative name editing.

No face reassignment, merge, embedding update, media write or legacy API import.
Unmapped/orphan people require an explicit future ownership/import workflow.
"""
import hashlib
import hmac
import json
import re
import time
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, _integer, _query
from .service import AccessDenied, AccessService
from .transport import TransportError, _body, _runtime, credentials_from_request

router = APIRouter(route_class=LibraryRoute)
SCOPED = ''' FROM face_detections f JOIN assets a ON a.id=f.asset_id
    JOIN access_asset_libraries l ON l.asset_id=a.id
    WHERE l.library_id=? AND (a.status IS NULL OR a.status='active')'''


class People:
    def __init__(self, access):
        self.access, self.db = access, access.db

    def _row(self, person):
        return self.db.execute('''SELECT id,substr(coalesce(display_name,''),1,128),
            updated_at,length(coalesce(display_name,'')) FROM persons WHERE id=?''', (person,)).fetchone()

    def _revision(self, row, library):
        key = self.db.execute('SELECT secret FROM access_admission_key WHERE id=1').fetchone()[0]
        last = self.db.execute('SELECT coalesce(max(id),0) FROM access_audit WHERE library_id=? AND action=?',
                               (library, 'person.rename.' + str(row[0]))).fetchone()[0]
        return hmac.new(key, b'PhotoHouse person name v1\0' + json.dumps([library, row, last]).encode(), hashlib.sha256).hexdigest()

    def _exclusive(self, person, library):
        # Person names are legacy global records. Editing a shared/unmapped person's
        # name would affect another audience, even if this owner sees one face.
        return self.db.execute('''SELECT 1 FROM face_detections f
            LEFT JOIN access_asset_libraries l ON l.asset_id=f.asset_id
            WHERE f.person_id=? AND (l.library_id IS NULL OR l.library_id!=?) LIMIT 1''',
            (person, library)).fetchone() is None

    def _person(self, person, library):
        if self.db.execute('SELECT 1' + SCOPED + ' AND f.person_id=? LIMIT 1', (library, person)).fetchone() is None:
            raise AccessDenied('Access denied')
        row = self._row(person)
        if row is None:
            raise AccessDenied('Access denied')
        return row

    def _present(self, row, library, count):
        return {'id': str(row[0]), 'display_name': row[1], 'name_truncated': row[3] > 128,
                'face_count': count, 'revision': self._revision(row, library),
                'can_rename': self._exclusive(row[0], library)}

    def list(self, token, library, page, query):
        if len(query) > 128 or any(ord(c) < 32 for c in query):
            raise TransportError(400, 'Invalid search')
        pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        with self.access._transaction():
            self.access._require(token, library, 'library.people.manage')
            sql = '''SELECT p.id,substr(coalesce(p.display_name,''),1,128),p.updated_at,
                length(coalesce(p.display_name,'')),count(*)
                FROM persons p JOIN face_detections f ON f.person_id=p.id
                JOIN assets a ON a.id=f.asset_id JOIN access_asset_libraries l ON l.asset_id=a.id
                WHERE l.library_id=? AND (a.status IS NULL OR a.status='active')
                AND coalesce(p.display_name,'') LIKE ? ESCAPE '\\' GROUP BY p.id'''
            total = self.db.execute('SELECT count(*) FROM (' + sql + ')', (library, pattern)).fetchone()[0]
            rows = self.db.execute(sql + ' ORDER BY coalesce(p.display_name,\'\') COLLATE NOCASE,p.id LIMIT 25 OFFSET ?',
                                   (library, pattern, (page-1)*25)).fetchall()
            return {'library_id': library, 'page': page, 'page_size': 25, 'total': total,
                    'items': [self._present(row[:4], library, row[4]) for row in rows]}

    def faces(self, token, library, person, page):
        with self.access._transaction():
            self.access._require(token, library, 'library.people.manage')
            self._person(person, library)
            total = self.db.execute('SELECT count(*)' + SCOPED + ' AND f.person_id=?', (library, person)).fetchone()[0]
            rows = self.db.execute('SELECT f.id,f.asset_id' + SCOPED +
                ' AND f.person_id=? ORDER BY f.id LIMIT 25 OFFSET ?', (library, person, (page-1)*25)).fetchall()
            return {'library_id': library, 'person_id': str(person), 'page': page, 'page_size': 25, 'total': total,
                    'items': [{'id': str(face), 'asset_id': str(asset),
                               'crop_url': f'/faces/{face}/crop?' + urlencode({'library': library})}
                              for face, asset in rows]}

    def rename(self, token, library, person, body):
        name, revision = body['display_name'], body['revision']
        if (not name.strip() or name != name.strip() or len(name) > 128
                or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in name)
                or not re.fullmatch('[0-9a-f]{64}', revision)):
            raise TransportError(400, 'Invalid name or revision')
        with self.access._transaction(write=True):
            member = self.access._require(token, library, 'library.people.manage')
            row = self._person(person, library)
            if not self._exclusive(person, library):
                raise AccessDenied('Access denied')
            if not hmac.compare_digest(revision, self._revision(row, library)):
                raise TransportError(409, 'Person changed; refresh before saving')
            self.db.execute('UPDATE persons SET display_name=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (name, person))
            # Record identity, not the private name. Reusing target_account for a
            # person ID would misrepresent the account audit schema.
            self.access._audit(member['account_id'], 'person.rename.' + str(person), library)
            count = self.db.execute('SELECT count(*)' + SCOPED + ' AND f.person_id=?', (library, person)).fetchone()[0]
            return self._present(self._row(person), library, count)


def _call(runtime, action, *args):
    with runtime.connection_factory() as db:
        deadline = time.monotonic() + 3
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        try:
            return getattr(People(AccessService(db, clock=runtime.clock)), action)(*args)
        finally:
            db.set_progress_handler(None, 0)


@router.get('/admin/people')
async def people(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page', 'q'})
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'list', token,
        query['library'], _integer(query.get('page', '1'), 100000), query.get('q', '')))


@router.get('/admin/people/{person_id}/faces')
async def faces(person_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page'})
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'faces', token,
        query['library'], _integer(person_id, 2**63-1), _integer(query.get('page', '1'), 100000)))


@router.put('/admin/people/{person_id}')
async def rename(person_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, {'display_name', 'revision'})
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'rename', token,
        query['library'], _integer(person_id, 2**63-1), body))
