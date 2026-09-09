# Closed application and authorized media — slice 4

Continuation: [slice 5 — ORM metadata and real migration rehearsal](ORM_REHEARSAL.md).
The missing-runtime and metadata gates below describe the slice-4 checkpoint.

Status: **local synthetic verification of the actual `app.main` entry point. Not
deployed, not a complete family release, and not an ORM migration rehearsal.**

This continues [account admission and session transport](ACCOUNT_TRANSPORT.md).
Manual owner invitations and phone/password login remain the chosen account model.
A phone number is an unverified login label; signup alone never grants photos.

## What changed

`app.main` now constructs the shared account/media API without reading runtime
settings, opening a database, configuring logging, creating an executor or starting
workers. `app.__init__` no longer configures logging as an import side effect.
The default application has no access/media runtime and denies protected requests.
It does not discover `.env`, create schema, bootstrap an owner, map legacy assets
or fall back to anonymous access when configuration is absent.

`create_app(access_runtime=..., media_runtime=...)` takes explicit integration
objects. Tests supply a fresh temporary SQLite database and synthetic files. The
connection factory must use the same PhotoHouse database, enable foreign keys,
open/close a fresh connection in the worker thread, and never initialize missing
schema. Media roots are explicit server configuration, not request parameters.
No production connection/configuration adapter is supplied by this slice.

`ClosedBoundary` permits only the reviewed method/path/handler combinations.
Unknown routes and unfinished legacy routes return generic 403 without invoking
handlers, storage, providers or jobs. A handler inserted ahead of `/auth/login`
cannot inherit permission from its URL. WebSockets close with policy code 1008.
The public exceptions remain the five code-only UI routes. Framework docs/OpenAPI
and slash redirects are disabled; every HTTP response has no-store/privacy headers.

The old main implementation is preserved byte-for-byte after a three-line guard in
`legacy_main.py`. Importing that module raises **before** any runtime dependency
or initialization. Its unguarded handlers are retained for source audit and the
historical regression ledger; they are not a compatibility server or fallback.
The people/album/voice routers are not mounted by the new entry point.

Two CLI helpers previously imported `SessionLocal` from the HTTP module. They now
obtain sessions from the CLI's existing `_session_factory()` and dispose their
engine when finished. This prevents CLI imports from depending on the retired
HTTP startup. Actual CLI/worker execution was not run under the current boundary.

## Active and retired inventory

The source inventory contains **147 method/path entries**, including deliberately
unreachable historical implementations and separate service applications:

| Surface | Entries | Evidence / remaining boundary |
| --- | --- | --- |
| Active `app.main` | 18 | Exact runtime route-set comparison: seven account, six media GET/HEAD, five UI-shell entries |
| Retired PhotoHouse | 97 | Every old method/path probed against the new application: denied or replaced by one of the three protected media GET paths |
| Standalone LVFace | 12 | Still unprotected; not loaded, called or deployed |
| Standalone diagnostics | 10 | Still unprotected; not loaded, called or deployed |
| Standalone RAM++ | 10 | Still unprotected; not loaded, called or deployed |

This is a deliberate source behavior change: search, lists/counts, captions,
albums, people management, operations, uploads/destruction and voice are **disabled**
in the new entry point. Their authorization/query implementations are not repaired.
The existing web UI currently serves its shell only; it still needs sign-in and
library-aware request integration. Do not deploy this branch over the family UI.

The source scanner still cannot resolve arbitrary metaprogramming. The separate
runtime route-set test and handler-bound default-deny middleware provide additional
checks for the actual application constructed here. A future route must be reviewed
in the inventory, mounted explicitly and admitted by the boundary before use.

## Media behavior

Existing URLs are used by both cookie-authenticated web and native bearer clients:

| Methods and path | Required policy | Query |
| --- | --- | --- |
| GET/HEAD `/assets/{asset_id}/media` | Current approved membership plus explicit original-byte grant | Required `library`; optional `download=true` or `false` |
| GET/HEAD `/assets/{asset_id}/thumbnail` | Current approved membership; active mapped parent asset | Required `library`; optional integer `size` 64–1024, default 256 |
| GET/HEAD `/faces/{face_id}/crop` | Current approved membership; face joined to active mapped parent asset | Required `library`; optional integer `size` 64–1024, default 256 |

Library IDs select a scope; they do not grant it. Unknown, duplicate or credential
query fields are rejected. The account endpoints continue to reject all queries.
Original access is separate even for an owner and includes inline video/image
bytes, downloads and every Range/conditional retry. Download filenames use the
asset ID rather than the private original filename. Unknown media extensions are
sent as an attachment with an octet-stream content type and a `.bin` filename.

`MediaRuntime.open_file()` is the shared service boundary. It validates input and
checks the current session/account, library and membership, then performs a scoped
join. A face crop inherits the parent asset's mapping and active status. Deleted,
missing, unmapped and foreign IDs fail before any media filesystem lookup.
Direct service calls use the same checks, including derivative-size validation.

A short SQLite `BEGIN IMMEDIATE` reservation covers the policy check, scoped lookup,
path resolution and file open. The WAL-mode test proves a competing membership
update cannot commit during open. The reservation ends before streaming so a slow
client cannot hold the database transaction. The response opens only when it is
executed; a session revoked after response construction is denied before stat/open.

Original paths must resolve within a configured original root. Derived paths are
constructed from the validated variant, size and ID and must resolve within the
derived root. Paths escaping through symlinks are denied. After open, regular-file
type, resolved path and device/inode identity are checked again before bytes are
read. The response streams that pinned descriptor, never reopens the filename or
emits a server `pathsend` shortcut. Tests replace a path after headers and still
receive the originally authorized descriptor. Descriptors close on success, bad
ranges, unsatisfiable ranges and client disconnection.

This protects request authorization, not a hostile storage administrator. Roots,
database mappings, filesystem permissions and derivative writers are trusted
operator state. Live Windows path/reparse behavior remains unverified. An already
authorized in-flight response can finish after membership is revoked; the next
request is denied. This does not recall downloaded bytes or guarantee immutable
contents if another process rewrites an already-open file in place.

Thumbnails/crops are **cached files only** in this slice. Missing cached media
returns 404; no original fallback, image decode, model, job or derived write occurs.
Derivative creation needs a later authorized worker service.

Single byte ranges support bounded, open-ended and suffix requests and return
206. Unsatisfiable ranges return 416 with length only after authorization; malformed
or multipart ranges return 400. Metadata produces only a **weak** ETag. Requests
with If-Range conservatively receive full 200 after authorization; they do not use
a metadata hash as a strong validator. If-None-Match does not bypass authorization
or generate a 304 response. Every HEAD/Range/retry follows the same policy and
no-store handling. Real codec playback and native player compatibility are untested.

## Verification and failure ledger

Run from the isolated worktree:

```sh
python3 -m unittest discover -s tests/security -v
python3 scripts/security_inventory.py
python3 tests/security/harness.py
git diff --cached -B -M --check
```

The new tests import the actual package/entry point, execute its lifespan with
storage forbidden, and use its real account/media routes, shared policy, SQLite and
in-process ASGI responses. There is no extracted-handler substitution in active
application acceptance. The 22 new tests cover:

- Cold import without DB/worker/network/logging side effects; absent configuration
  fails closed; retired-module import refusal; exact active route coverage.
- Every retired URL/method against the active boundary, owner attempts at unfinished
  routes, accidental route registration and an unreviewed login shadow.
- Approved web/native originals, downloads, thumbnails, crops and HEAD; Range,
  conditional fallback, 416, cached-only behavior and privacy headers.
- Real unapproved/revoked/expired/cross-library/malformed/unknown-session denials,
  disabled accounts, foreign/deleted/unassigned parent IDs, original grants,
  direct-service calls and denial before filesystem lookup.
- Revocation between response construction and open, between Range requests, and
  serialized with open in WAL mode; symlink escape, descriptor identity and cleanup.

Observed on 2026-09-09: **96 focused security tests passed in 12.972 seconds**, no
skips or xfails; the 147-entry inventory passed; changed Python sources parsed and
`git diff --cached -B -M --check` passed. Move detection recognizes the byte-for-byte
legacy copy and its unchanged historical trailing whitespace. The historical denial
harness still intentionally exits 1.

All rows, accounts, tokens, files and phone labels are synthetic temporary fixtures.
Socket bind/connect and subprocess execution are blocked in active HTTP tests.
No packages, models or services were installed or started. Host Python is 3.14.7;
these checks are source/synthetic evidence, not the Windows runtime environment.

The separate historical harness still returns **84/84 failed requirements and exit
1** when extracting the retired unguarded implementations. This preserves evidence
that they must not be remounted. It is no longer a report of 84 reachable bypasses
in the new `app.main`; active-entrypoint denial is tested separately. The 32
standalone entries remain an actual unresolved source authorization surface.

The old `backend/tests` suite is not claimed green. It imports removed HTTP-owned
executor/session helpers and assumes previously anonymous APIs. Its worker fixtures
and authorized request setup need explicit refactoring. It was not run: SQLAlchemy,
Alembic and the runtime environment are absent, and model/runtime work is forbidden.

## ORM and deployment gates still open

The planned ORM metadata reconciliation and actual Alembic upgrade/revision-ledger
rehearsal are **not complete**. SQLAlchemy and Alembic remain unavailable in the
inspected local runtimes; no installation was performed. Existing migration tests
still use real synthetic SQLite DDL and a minimal Alembic binding double. Access and
admission tables are absent from `db.Base` metadata: do not run autogenerate yet.
The new HTTP app does not invoke `create_all`, fallback migrations or workers.

Further gates include reviewed legacy mapping across every relationship, scoped
search and albums/captions, authorized derivative/worker/voice services, stream and
service-wide resource limits, trusted proxy/TLS configuration, real browser/native
session/media tests, password/owner recovery, and crash-slot recovery for admission.
No live data, Windows/Mac mini access, deployment, push, merge or mobile-repository
change is part of this result.

Next bounded step: obtain a supplied or explicitly authorized isolated ORM test
runtime, reconcile access/admission metadata without creating security tables from
startup, and rehearse upgrade/rollback/revision integrity on synthetic SQLite. Then
add the first scoped gallery/caption reads and web sign-in/library selection, while
keeping every unfinished route denied. Reopening retired handlers is not a shortcut.

## Source handoff

Branch: `codex/mobile-access-foundation`, continuing commit
`03ec1ba1dba92940a530984e79c9d52ae445a421`, based on `origin/master` at
`932263504ac5fcc3ed178e951991619d8ee87049` in the existing isolated worktree.
Original checkout and mobile repository remain untouched.

Changed files:

- `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/legacy_main.py`
- `backend/app/access/__init__.py`, `backend/app/access/transport.py`,
  `backend/app/access/boundary.py`, `backend/app/access/media.py`
- `backend/app/cli.py`
- `scripts/security_inventory.py`, `docs/security/route_capabilities.json`
- `tests/security/test_closed_application.py`, `tests/security/test_access_transport.py`,
  `tests/security/test_current_gaps.py`, `tests/security/test_inventory.py`,
  `tests/security/harness.py`
- `docs/security/ACCOUNT_TRANSPORT.md`, `docs/security/CLOSED_APPLICATION.md`
