"""Member-visible, read-only tag catalog.

A member sees tag names and how many of *this* library's active assets carry them,
and nothing else. There is no write path here at all: no add, no remove, no rename,
no tag derivation and no per-link provenance.

What is deliberately not exposed, and why:

- **No `source` breakdown** (`cap` / `img` / `cap+img` / `manual` / `rule`). That is
  pipeline provenance — how a caption or an image model produced the tag — not a
  family-facing fact, and legacy's per-source counters are not a member feature.
- **No tag `type`**, for the same reason: it names the derivation, not the content.
- **No global or cross-library counts.** Every count is a count of the caller's own
  visible assets. A library-wide or global total would let a member infer the size of
  an audience they are not in.
- **No probe by id.** A tag that carries nothing in this library is indistinguishable
  from a tag that does not exist, and neither is ever confirmed.

Legacy listing semantics are preserved deliberately: `DELETE /assets/{id}/tags`
removes the `asset_tags` row and records a *separate* `asset_tag_blocks` row only to
stop automatic re-adding, so a blocked pair has no link and never inflates a count.
Counting from `asset_tags` alone therefore matches legacy `/tags`, which also ignores
blocks.

The visibility predicate is the one the gallery uses (`library.SOURCE`): an asset is
visible when `access_asset_libraries` maps it to the library and its status is active
or absent. The catalog query writes that predicate out inline because it groups by
tag, and the tests pin the two definitions together by asserting a foreign library's
tag is invisible rather than by comparing SQL text.
"""
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import FIELDS, SOURCE, LibraryRoute, _asset, _integer, _query
from .service import AccessDenied, AccessService
from .transport import TransportError, _runtime, credentials_from_request

router = APIRouter(route_class=LibraryRoute)
PAGE_SIZE = 25


class Tags:
    def __init__(self, access):
        self.access, self.db = access, access.db

    def catalog(self, token, library, page, query):
        """Library-scoped tag catalog: a name and this library's asset count.

        Gated on `library.read`, so any approved membership may read it rather than
        the owner only. Only tags with at least one link to a visible asset of this
        library appear, ordered most-used first, so the result can only ever confirm
        tags the caller can already see.
        """
        if len(query) > 128 or any(ord(c) < 32 for c in query):
            raise TransportError(400, 'Invalid search')
        pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        with self.access._transaction():
            self.access._require(token, library, 'library.read')
            sql = '''WITH visible AS (SELECT x.tag_id AS tag_id,count(DISTINCT x.asset_id) AS n
                FROM asset_tags x JOIN assets a ON a.id=x.asset_id
                JOIN access_asset_libraries scope ON scope.asset_id=a.id
                WHERE scope.library_id=? AND (a.status IS NULL OR a.status='active')
                GROUP BY x.tag_id)
                SELECT t.id,substr(t.name,1,128),length(t.name),v.n
                FROM tags t JOIN visible v ON v.tag_id=t.id
                WHERE t.name LIKE ? ESCAPE '\\' '''
            parameters = (library, pattern)
            total = self.db.execute('SELECT count(*) FROM (' + sql + ')', parameters).fetchone()[0]
            rows = self.db.execute(
                sql + ' ORDER BY v.n DESC,t.name COLLATE NOCASE,t.id LIMIT 25 OFFSET ?',
                parameters + ((page - 1) * PAGE_SIZE,)).fetchall()
            return {'library_id': library, 'page': page, 'page_size': PAGE_SIZE, 'total': total,
                    'items': [{'id': str(row[0]), 'name': row[1], 'name_truncated': row[2] > 128,
                               'asset_count': row[3]} for row in rows]}

    def assets(self, token, library, tag, page):
        """Visible assets of this library carrying one tag, same shape as the gallery."""
        with self.access._transaction():
            member = self.access._require(token, library, 'library.read')
            if self.db.execute('SELECT 1' + SOURCE +
                    ' AND a.id IN (SELECT asset_id FROM asset_tags WHERE tag_id=?) LIMIT 1',
                    (library, tag)).fetchone() is None:
                raise AccessDenied('Access denied')
            total = self.db.execute('SELECT count(*)' + SOURCE +
                ' AND a.id IN (SELECT asset_id FROM asset_tags WHERE tag_id=?)',
                (library, tag)).fetchone()[0]
            rows = self.db.execute('SELECT ' + FIELDS + SOURCE +
                ' AND a.id IN (SELECT asset_id FROM asset_tags WHERE tag_id=?)'
                ' ORDER BY a.taken_at DESC,a.id DESC LIMIT ? OFFSET ?',
                (library, tag, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
            return {'library_id': library, 'tag_id': str(tag), 'page': page, 'page_size': PAGE_SIZE,
                    'total': total, 'originals_allowed': bool(member['originals']),
                    'items': [_asset(row, library) for row in rows]}


def _call(runtime, action, *args):
    with runtime.connection_factory() as db:
        deadline = time.monotonic() + 3
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        try:
            return getattr(Tags(AccessService(db, clock=runtime.clock)), action)(*args)
        finally:
            db.set_progress_handler(None, 0)


@router.get('/tags')
async def catalog(request: Request):
    # Member-facing catalog. Distinct from the retired legacy /tags on purpose: the
    # legacy response carried per-source counters and a tag type, and the legacy page
    # also offered the write path. Neither is reproduced here.
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page', 'q'})
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'catalog', token,
        query['library'], _integer(query.get('page', '1'), 100000), query.get('q', '')))


@router.get('/tags/{tag_id}/assets')
async def assets(tag_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page'})
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True), 'assets', token,
        query['library'], _integer(tag_id, 2**63-1), _integer(query.get('page', '1'), 100000)))
