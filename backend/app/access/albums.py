"""Library-owned album drafts. No legacy routes, filesystem writes or publishing."""
import hashlib
import hmac
import json
import re
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .library import LibraryRoute, _query, _integer
from .service import AccessService, AccessDenied
from .transport import _body, _runtime, credentials_from_request, TransportError

router = APIRouter(route_class=LibraryRoute)
FIELDS = {'title','title_zh','description','theme','asset_ids','cover_asset_id'}
THEMES = {'birthday','trip','growing_up','grandparents','year_in_review','seasonal','custom'}


def content(body):
    for key, limit in (('title',160),('title_zh',160),('description',1000)):
        value = body[key]
        if len(value)>limit or any(0xD800<=ord(c)<=0xDFFF or (ord(c)<32 and c not in '\n\t') for c in value):
            raise TransportError(400,'Invalid album text')
    if not body['title'].strip() or body['theme'] not in THEMES:
        raise TransportError(400,'Invalid album')
    ids = [_integer(value,2**63-1) for value in body['asset_ids'].split(',')] if body['asset_ids'] else []
    if len(ids)>60 or len(ids)!=len(set(ids)):
        raise TransportError(400,'Invalid album selection')
    cover = _integer(body['cover_asset_id'],2**63-1) if body['cover_asset_id'] else None
    if cover is not None and cover not in ids:
        raise TransportError(400,'Cover must be selected')
    return ids, cover if cover is not None else (ids[0] if ids else None)


class Albums:
    def __init__(self, access):
        self.access,self.db = access,access.db

    def _row_any(self, album, library):
        """The album row regardless of status, validated, for the archive/restore pair.

        `_row` refuses anything that is not `draft`, and that refusal is what hides an archived
        album from every read — so restoring one cannot go through `_row`. Both paths share this
        fetch so they cannot drift apart.
        """
        row = self.db.execute('''SELECT a.id,substr(a.title,1,160),substr(a.title_zh,1,160),substr(a.description,1,1000),
            substr(a.theme,1,32),a.cover_asset_id,owned.revision,a.status,
            length(a.title),length(a.title_zh),length(a.description) FROM albums a JOIN access_album_libraries owned ON owned.album_id=a.id
            WHERE a.id=? AND owned.library_id=?''',(album,library)).fetchone()
        if row is None:
            return None
        if any((length or 0)>limit for length,limit in zip(row[8:],(160,160,1000))) or row[4] not in THEMES:
            raise TransportError(503,'Album unavailable')
        return row

    def _row(self, album, library):
        row = self._row_any(album, library)
        if row is None or row[7]!='draft':
            raise AccessDenied('Access denied')
        return row[:8]

    def _revision(self, row, library):
        ids = self.db.execute('SELECT asset_id,position FROM album_assets WHERE album_id=? ORDER BY position,id LIMIT 61',(row[0],)).fetchall()
        if len(ids)>60: raise TransportError(503,'Album unavailable')
        key = self.db.execute('SELECT secret FROM access_admission_key WHERE id=1').fetchone()[0]
        return hmac.new(key,json.dumps([library,row,ids]).encode(),hashlib.sha256).hexdigest()

    def _present(self,row,library):
        # A moved/deleted asset is excluded, including its ID and cover reference.
        ids = [str(r[0]) for r in self.db.execute('''SELECT aa.asset_id FROM album_assets aa
            JOIN assets a ON a.id=aa.asset_id JOIN access_asset_libraries s ON s.asset_id=a.id
            WHERE aa.album_id=? AND s.library_id=? AND (a.status IS NULL OR a.status='active')
            ORDER BY aa.position,aa.id LIMIT 61''',(row[0],library))]
        if len(ids)>60:
            raise TransportError(503,'Album unavailable')
        count=self.db.execute('SELECT count(*) FROM album_assets WHERE album_id=?',(row[0],)).fetchone()[0]
        return {'id':str(row[0]),'title':row[1],'title_zh':row[2] or '', 'description':row[3] or '',
                'theme':row[4],'asset_ids':ids,'cover_asset_id':str(row[5]) if str(row[5]) in ids else (ids[0] if ids else ''),
                'revision':self._revision(row,library),'needs_review':count!=len(ids)}

    def list(self,token,library,page):
        with self.access._transaction():
            member=self.access._require(token,library,'library.read')
            total=self.db.execute("""SELECT count(*) FROM albums a JOIN access_album_libraries o ON o.album_id=a.id
                WHERE o.library_id=? AND a.status='draft'""",(library,)).fetchone()[0]
            rows=self.db.execute("""SELECT a.id FROM albums a JOIN access_album_libraries o ON o.album_id=a.id
                WHERE o.library_id=? AND a.status='draft' ORDER BY a.id DESC LIMIT 10 OFFSET ?""",(library,(page-1)*10)).fetchall()
            return {'items':[self._present(self._row(row[0],library),library) for row in rows],
                    'page':page,'total':total,'page_size':10,'can_manage':member['role']=='owner'}

    def _assets(self, ids, library):
        for asset in ids:
            if self.db.execute('''SELECT 1 FROM assets a JOIN access_asset_libraries s ON s.asset_id=a.id
                WHERE a.id=? AND s.library_id=? AND (a.status IS NULL OR a.status='active')''',(asset,library)).fetchone() is None:
                raise AccessDenied('Access denied')

    def save(self,token,library,album,body):
        ids,cover=content(body)
        if album is None:
            try:
                if str(uuid.UUID(body['mutation_id'])) != body['mutation_id']: raise ValueError()
            except ValueError: raise TransportError(400,'Invalid mutation')
        elif not re.fullmatch('[0-9a-f]{64}',body['revision']):
            raise TransportError(400,'Invalid revision')
        with self.access._transaction(write=True):
            member=self.access._require(token,library,'library.albums.manage')
            self._assets(ids,library)
            digest=hashlib.sha256(json.dumps({key:body[key] for key in sorted(FIELDS)}).encode()).hexdigest()
            if album is None:
                prior=self.db.execute('SELECT album_id,library_id,creator_id,creation_digest FROM access_album_libraries WHERE mutation_id=?',(body['mutation_id'],)).fetchone()
                if prior:
                    if prior[1:]!=(library,member['account_id'],digest): raise TransportError(409,'Mutation conflict')
                    return self._present(self._row(prior[0],library),library)
                album=self.db.execute("""INSERT INTO albums(title,title_zh,description,theme,status,cover_asset_id)
                    VALUES(?,?,?,?,'draft',?)""",(body['title'],body['title_zh'],body['description'],body['theme'],cover)).lastrowid
                self.db.execute('''INSERT INTO access_album_libraries(album_id,library_id,creator_id,revision,mutation_id,creation_digest)
                    VALUES(?,?,?,1,?,?)''',(album,library,member['account_id'],body['mutation_id'],digest))
            else:
                row=self._row(album,library)
                if not hmac.compare_digest(body['revision'],self._revision(row,library)) or row[6]>=2**63-1:
                    raise TransportError(409,'Album changed; review again')
                self.db.execute('''UPDATE albums SET title=?,title_zh=?,description=?,theme=?,cover_asset_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?''',
                    (body['title'],body['title_zh'],body['description'],body['theme'],cover,album))
                self.db.execute('UPDATE access_album_libraries SET revision=revision+1 WHERE album_id=?',(album,))
                self.db.execute('DELETE FROM album_assets WHERE album_id=?',(album,))
            self.db.executemany('INSERT INTO album_assets(album_id,asset_id,position) VALUES(?,?,?)',[(album,asset,pos) for pos,asset in enumerate(ids)])
            self.access._audit(member['account_id'],'album.save.'+str(album),library)
            return self._present(self._row(album,library),library)


    def archived(self,token,library,page):
        """The albums this library has put away, so an archive can actually be undone.

        Owner-only, and deliberately a separate read rather than a flag on the member list: an
        archived album is meant to be invisible to members, and a conditional capability on one
        route is easier to get wrong than a route that simply requires the owner.

        No revision is returned, because restoring does not take one — an archived album cannot be
        edited, so there is no concurrent change for a revision to protect against.
        """
        with self.access._transaction():
            self.access._require(token,library,'library.albums.manage')
            total=self.db.execute('''SELECT count(*) FROM albums a
                JOIN access_album_libraries owned ON owned.album_id=a.id
                WHERE owned.library_id=? AND a.status='archived' ''',(library,)).fetchone()[0]
            rows=self.db.execute('''SELECT a.id,substr(a.title,1,160),substr(a.title_zh,1,160),
                substr(a.theme,1,32),a.cover_asset_id FROM albums a
                JOIN access_album_libraries owned ON owned.album_id=a.id
                WHERE owned.library_id=? AND a.status='archived'
                ORDER BY a.id DESC LIMIT 10 OFFSET ?''',(library,(page-1)*10)).fetchall()
            return {'library_id':library,'page':page,'page_size':10,'total':total,
                    'items':[{'id':str(r[0]),'title':r[1],'title_zh':r[2] or '','theme':r[3],
                              'cover_asset_id':str(r[4]) if r[4] is not None else ''} for r in rows]}

    def archive(self,token,library,album,body,archived):
        """Hide an album from the library, or bring it back.

        Archiving writes `albums.status='archived'`, which every read already excludes: the list
        selects `status='draft'` and `_row` refuses anything else. So no migration is needed and
        **nothing is deleted** — the album, its selected assets and its cover all survive, which
        makes this reversible by design. That is the property the owner asked for: an album
        created by mistake can be put away and brought back, and deletion is not offered at all.

        The revision is checked exactly as `save` checks it, so two owners cannot archive and
        edit the same album concurrently and silently lose one of the changes.
        """
        # Only archiving is revision-bound. Restoring deliberately is not: the revision exists
        # to stop two writers losing each other's edit, and an archived album cannot be edited
        # at all — every read refuses it — so there is no concurrent edit to lose. Requiring one
        # would in fact make restore impossible, because the client can only read a revision from
        # the list, and archiving removes the album from it.
        if archived and not re.fullmatch('[0-9a-f]{64}',body.get('revision','')):
            raise TransportError(400,'Invalid revision')
        with self.access._transaction(write=True):
            member=self.access._require(token,library,'library.albums.manage')
            row=self._row_any(album,library)
            if row is None:
                raise AccessDenied('Access denied')
            # Refuse a no-op rather than silently reporting success, so the caller learns the
            # album was already in the state they asked for.
            if archived and row[7]!='draft':
                raise TransportError(409,'Album is not in this library')
            if not archived and row[7]!='archived':
                raise TransportError(409,'Album is not archived')
            if archived and not hmac.compare_digest(body['revision'],self._revision(row[:8],library)):
                raise TransportError(409,'Album changed; review again')
            self.db.execute('UPDATE albums SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                            ('archived' if archived else 'draft',album))
            self.db.execute('UPDATE access_album_libraries SET revision=revision+1 WHERE album_id=?',(album,))
            self.access._audit(member['account_id'],
                               'album.'+('archive' if archived else 'restore')+'.'+str(album),library)
            # Not `_present`: an archived album is refused by `_row`, which is the point.
            return {'id':str(album),'library_id':library,
                    'status':'archived' if archived else 'draft','archived':bool(archived)}


def _call(runtime,action,*args):
    with runtime.connection_factory() as db:
        deadline=time.monotonic()+3
        db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        try: return getattr(Albums(AccessService(db,clock=runtime.clock)),action)(*args)
        finally: db.set_progress_handler(None,0)


@router.get('/library-albums')
async def list_albums(request: Request):
    token,_=credentials_from_request(request,allow_query=True)
    query=_query(request,{'library','page'})
    return JSONResponse(await run_in_threadpool(_call,_runtime(request,allow_query=True),'list',token,
        query['library'],_integer(query.get('page','1'),100000)))


@router.post('/admin/albums')
async def create_album(request: Request):
    token,_=credentials_from_request(request,allow_query=True)
    query=_query(request,{'library'})
    body=await _body(request,FIELDS|{'mutation_id'})
    return JSONResponse(await run_in_threadpool(_call,_runtime(request,allow_query=True),'save',token,query['library'],None,body))


@router.put('/admin/albums/{album_id}')
async def update_album(album_id: str,request: Request):
    token,_=credentials_from_request(request,allow_query=True)
    query=_query(request,{'library'})
    body=await _body(request,FIELDS|{'revision'})
    return JSONResponse(await run_in_threadpool(_call,_runtime(request,allow_query=True),'save',token,query['library'],_integer(album_id,2**63-1),body))


@router.get('/admin/albums/archived')
async def archived_albums(request: Request):
    # The recovery surface: without it, archiving would hide an album with no way back.
    token,_=credentials_from_request(request,allow_query=True)
    query=_query(request,{'library','page'})
    return JSONResponse(await run_in_threadpool(_call,_runtime(request,allow_query=True),'archived',
        token,query['library'],_integer(query.get('page','1'),100000)))


@router.post('/admin/albums/{album_id}/archive')
async def archive_album(album_id: str,request: Request):
    # Put an album away without deleting anything, so a mistake is recoverable.
    token,_=credentials_from_request(request,allow_query=True)
    query=_query(request,{'library'})
    body=await _body(request,{'revision'})
    return JSONResponse(await run_in_threadpool(_call,_runtime(request,allow_query=True),'archive',
        token,query['library'],_integer(album_id,2**63-1),body,True))


@router.post('/admin/albums/{album_id}/restore')
async def restore_album(album_id: str,request: Request):
    # The other half of archive: without it, archiving would be a one-way door. No revision is
    # required, because an archived album cannot be edited and so cannot be concurrently changed.
    token,_=credentials_from_request(request,allow_query=True)
    query=_query(request,{'library'})
    body=await _body(request,set())
    return JSONResponse(await run_in_threadpool(_call,_runtime(request,allow_query=True),'archive',
        token,query['library'],_integer(album_id,2**63-1),body,False))
