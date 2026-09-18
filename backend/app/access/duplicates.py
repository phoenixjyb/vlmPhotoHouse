"""Member-visible exact-duplicate groups; read-only and library-scoped.

An exact duplicate is two or more active assets in the **same library** with the same
`hash_sha256`. On the deployed family library that is 3,081 groups covering 6,189 of 27,842
active assets, and the cause is ordinary rather than a defect: the same trip was imported twice
under two naming schemes — a phone export and the camera's own filenames — so both copies are
real files in real folders.

This view exists so a member can understand why one photo appears twice. It deliberately does
not exist so anything can be deleted: **deletion is excluded**, nothing here writes, and no
route removes or suppresses a copy. A family that decided to keep both copies is not wrong.

Two things are deliberately absent:

* **No path and no filename.** The protected asset projection carries none, and the legacy
  `/duplicates` route returned full filesystem paths. The folder names would explain *why* a
  pair exists, but nothing here acts on that, so the leak is not worth the explanation.
* **No content hash.** The group is identified by its lowest asset ID, which is stable and
  paging-friendly, rather than by the hash — a hash would let a caller test whether a known
  image is in the library.

Near-duplicates (perceptual similarity, legacy `/duplicates/reduction/*`) are a separate and
later contract: they need the `phash` task's output and an explicit threshold decision.
"""
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import FIELDS, LibraryRoute, _asset, _integer, _query
from .service import AccessService
from .transport import _runtime, credentials_from_request

router = APIRouter(route_class=LibraryRoute)
PAGE_SIZE = 25
# One group must not be able to return an unbounded number of copies: a pathological import
# could otherwise turn a single page into an arbitrary response. The count is still reported.
MAX_COPIES = 25

def _visible(alias):
    """One predicate, so the outer query and the repeat-detection subquery cannot drift apart.

    The alias is a parameter because the subquery needs its own: reusing the outer `a` shadowed
    it and left the subquery with no `b` to reference at all.
    """
    return (f' FROM assets {alias} JOIN access_asset_libraries scope'
            f' ON scope.asset_id={alias}.id'
            f" WHERE scope.library_id=? AND ({alias}.status IS NULL OR {alias}.status='active')")


VISIBLE = _visible('a')

# The same predicate, restricted to hashes that repeat *within this library*. Grouping by the
# library's own copies rather than globally keeps the count meaningful for the audience: a photo
# that is in this library once is not a duplicate here just because another library has it.
DUPLICATED = (' AND a.hash_sha256 IS NOT NULL AND a.hash_sha256 IN ('
              'SELECT b.hash_sha256' + _visible('b') +
              ' AND b.hash_sha256 IS NOT NULL GROUP BY b.hash_sha256 HAVING count(*) > 1)')


class Duplicates:
    def __init__(self, access):
        self.access, self.db = access, access.db

    def groups(self, token, library, page):
        """Duplicate groups in this library, one entry per repeated hash.

        The group is identified by its **lowest asset ID**. That is stable across pages without
        exposing the hash, and it orders the list deterministically so paging cannot skip or
        repeat a group while the library is unchanged.
        """
        with self.access._transaction():
            self.access._require(token, library, 'library.read')
            total = self.db.execute(
                'SELECT count(*) FROM (SELECT a.hash_sha256' + VISIBLE + DUPLICATED +
                ' GROUP BY a.hash_sha256)', (library, library)).fetchone()[0]
            heads = self.db.execute(
                'SELECT min(a.id)' + VISIBLE + DUPLICATED +
                ' GROUP BY a.hash_sha256 ORDER BY min(a.id) LIMIT ? OFFSET ?',
                (library, library, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
            ids = [row[0] for row in heads]
            items = []
            for group_id in ids:
                # Resolve the group's own hash from its head, then list that hash's copies in
                # this library. Bounded, and ordered so a group always renders the same way.
                digest = self.db.execute('SELECT hash_sha256 FROM assets WHERE id=?',
                                         (group_id,)).fetchone()[0]
                copies = self.db.execute('SELECT ' + FIELDS + VISIBLE +
                    ' AND a.hash_sha256=? ORDER BY a.id LIMIT ?',
                    (library, digest, MAX_COPIES)).fetchall()
                count = self.db.execute('SELECT count(*)' + VISIBLE + ' AND a.hash_sha256=?',
                                        (library, digest)).fetchone()[0]
                items.append({'group_id': str(group_id), 'copy_count': count,
                              'copies_truncated': count > MAX_COPIES,
                              'copies': [_asset(row, library) for row in copies]})
            return {'library_id': library, 'page': page, 'page_size': PAGE_SIZE,
                    'total': total, 'max_copies_per_group': MAX_COPIES, 'items': items}


def _call(runtime, action, *args):
    with runtime.connection_factory() as db:
        deadline = time.monotonic() + 3
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        try:
            return getattr(Duplicates(AccessService(db, clock=runtime.clock)), action)(*args)
        finally:
            db.set_progress_handler(None, 0)


@router.get('/duplicates')
async def duplicates(request: Request):
    # Member-visible, like the tag catalog and the people directory: read-only, scoped to one
    # library, and nothing here changes or hides a photo.
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page'})
    return JSONResponse(await run_in_threadpool(_call, _runtime(request, allow_query=True),
        'groups', token, query['library'], _integer(query.get('page', '1'), 100000)))
