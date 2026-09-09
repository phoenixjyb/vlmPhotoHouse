# Account admission and session transport — slice 3

Status: **verified local account adapter; unmounted in `app.main`. Legacy photo
authorization is still open. This branch is not ready for deployment.**

This continues [manual invitations and phone/password accounts](MANUAL_INVITATION_ACCOUNTS.md).
The owner manually sends a code bound to the recipient's phone login and selected
library. Registration requires that code and a password; redemption is the owner's
approval and grants viewer membership. Returning sign-in uses phone + password.
Phone ownership remains unverified. No SMS or WeChat account is needed.

## Bounded result

- `backend/app/access/admission.py` adds durable login/registration counters and
  one shared password-hashing slot in the existing PhotoHouse SQLite database.
- `backend/app/access/transport.py` adds a single account router for both web and
  native clients. Its integration contract accepts an explicit connection factory
  and configured HTTPS origin, without importing runtime settings or opening a
  database at import time. It is not a second mobile API or authentication store.
- Migration `f4c1a8d2e703`, after `e3a9b1c7d402`, adds admission state only. It does
  not create accounts, change credentials, map legacy assets or grant membership.
- The route inventory adds seven entries, explicitly marked
  `account-router-unmounted`. Its original 134 entries and open failures remain.
- Tests mount the actual account router in a minimal in-process FastAPI app and
  use real SQLite transactions, session records and scrypt. This is **not** the
  full PhotoHouse app: no legacy routes, settings, workers or providers are loaded.

The initially proposed ORM/full-app/media slice was narrowed after verifying that
SQLAlchemy and Alembic are unavailable in the inspected local runtimes and the
repository `.venv` is absent. The existing `main.py` calls `ensure_db()` and creates
its executor at import time. Importing it would violate the synthetic-only boundary.
No runtime packages were installed, and no media route was changed in this commit.

## Provisional shared transport contract

Paths below are implemented in the dormant router, not available on the existing
service. Freeze the web/mobile contract only after full-app integration review.

| Method and path | Request / authority | Result |
| --- | --- | --- |
| `POST /auth/register` | JSON `phone`, `password`, `code`, `transport`; valid owner invitation | New account, viewer membership and session atomically; 201 |
| `POST /auth/login` | JSON `phone`, `password`, `transport` | New 24-hour session; 200 |
| `GET /auth/session` | Current cookie or bearer session | Own account ID, phone login and membership state; no photo metadata |
| `POST /auth/logout` | Cookie + CSRF or native bearer | Idempotent session revocation; web cookie deleted |
| `POST /auth/invitations/accept` | Current account session, JSON `code` | Accept another invitation matching the account's phone; no password reset |
| `POST /libraries/{library_id}/invitations` | Current owner of that library, JSON `phone` | One code returned, valid for 24 hours; replaces prior unused codes for that phone/library |
| `POST /libraries/{library_id}/invitations/cancel` | Current owner of that library, JSON `code` | Scoped cancellation, without revealing other libraries' invitation state |

`transport` must be exactly `web` or `native`. Request JSON rejects unknown keys,
duplicate fields, non-string values and invalid Unicode. Account bodies are bounded
to 2 KiB even without Content-Length; compressed bodies are rejected. Account URLs
reject all query strings, including credentials and redirect parameters. There is
no bootstrap, password-reset, first-user-owner or owner-role field in this router.

Web login/registration requires the exact configured Origin. It sets
`__Host-ph_session` with Secure, HttpOnly, SameSite=Strict, Path=/ and a 24-hour
Max-Age, without Domain. The raw session value is not in web JSON. Login and session
readback return a session-bound CSRF value; every cookie-authenticated mutation
requires it in `X-CSRF-Token` and requires the configured Origin. The CSRF value
uses HMAC with the high-entropy session secret and is checked in constant time.
Logout revokes the session before removing the cookie, even if already expired.

Native login returns `access_token`, `token_type: Bearer`, and `expires_in` in
JSON. Native calls submit `Authorization: Bearer ...`. Browser Origin headers are
rejected on native credential flows. Cookie and bearer credentials together,
duplicate authorization/security-cookie values, malformed tokens and cross-site
fetches are rejected. Login refuses existing credentials so it cannot silently
replace the browser's signed-in account; logout precedes account switching.

Each account response sets `Cache-Control: no-store`, `Pragma: no-cache`,
`Referrer-Policy: no-referrer` and `X-Content-Type-Options: nosniff`. Errors never echo
request data or exception text. Invalid account/password/invitation failures share
a generic 401; CSRF/origin failures use 403; admission uses generic 429; unavailable
storage/runtime uses 503. Admission does not reveal which budget was exhausted.
No CORS policy or redirects are added. Header tests prove intended attributes;
they do not prove an actual HTTPS deployment or browser/device compatibility.

`credentials_from_request()` parses transport credentials only. It is **not** an
authorization check or reusable grant. Each operation invokes the existing shared
domain service, which reloads session/account and applicable membership state.
Revoked members may still see their own revoked status; that is not photo access.

## Durable admission and its availability tradeoff

Login and registration share these fixed-window limits, counting successes and
failures before password hashing:

| Dimension | Limit per 10-minute window |
| --- | --- |
| All credential attempts in the database | 60 |
| Immediate peer IP | 20 |
| Canonical phone login across all peers | 6 |
| Password work concurrently across connections/processes | 1 |

These conservative first-family defaults require pilot review. Fixed windows can
permit a burst around a boundary; they are not rolling-window guarantees. An
attacker can temporarily exhaust an account or shared-source budget. No permanent
account disable is applied. Counters survive new connections and runtime instances;
clock rollback does not reset a window. A forward clock jump can expire counters,
so the server clock is part of the trusted deployment configuration.

Only keyed digests of source/phone bucket names are persisted, using a randomly
generated database-local key. No raw password, invitation or session value is
added to admission state. Expired counters are pruned; the global limit bounds new
key growth. Counters commit on denials as well as successes. Domain errors release
the slot in `finally`; a caller cannot steal another request's slot.

**A process crash can leave the password slot occupied and stop new logins and
registrations.** There is deliberately no expiring lease that could start another
128 MiB KDF while the first is still running. Restart does not clear the slot.
Recovery must be an explicit offline operation after confirming all account
workers have stopped; no remotely callable reset or automatic deletion exists.
A reviewed recovery procedure is required before enabling this router.

The adapter uses the ASGI peer address, normalizes IPv4-mapped IPv6, and ignores
client Forwarded/X-Forwarded-For values. A server/proxy that rewrites ASGI peer,
scheme or host must have its own tightly scoped trust configuration. HTTPS and
Host are checked against a configured origin, never inferred from forwarded
headers. No proxy or TLS configuration was modified or verified here.

The factory must open/yield/close a fresh connection to the **same** PhotoHouse
database inside the worker thread, with foreign keys enabled and no pending
transaction. It must not initialize missing schema or fall back to another DB.
The transport performs no such fallback. Non-password account routes still need
general request/concurrency quotas during integration; these credential budgets
are not a service-wide DoS defense.

## Verification and limitations

Observed locally on 2026-09-09, host Python 3.14.7:

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests/security -v` | 74 passed in 32.478 seconds; 29 new admission/transport tests; no skips or xfails |
| `python3 scripts/security_inventory.py` | 141 method/path entries; complete; legacy authorization explicitly OPEN |
| Account test app's actual runtime route set | Exactly matches seven dormant inventory entries; docs/OpenAPI disabled in the harness |
| `python3 tests/security/harness.py` | 84 legacy security requirements still fail; intentional exit 1 |
| Real installed ORM/Alembic, full app, web browser/device, live TLS | Not run / unverified |

The tests exercise invite-only signup, repeat login, replay/cancellation, owner and
cross-library invitation denial, revoked membership readback, disabled/expired
sessions, native logout, web CSRF, cookie attributes, conflicting credentials,
body limits, uniform errors and unavailable-schema denial. Real SQL counters prove
admission before password work. Two connections contend for the same slot; a
persisted crash claim remains closed across reconnection. Network socket
bind/connect and process execution are blocked in HTTP scenarios. All phone labels,
DB rows, account secrets and paths are synthetic temporary fixtures.

Migration tests execute the actual DDL on fresh synthetic SQLite and test rollback,
preservation of existing synthetic assets, and a minimal Alembic binding double.
They do **not** verify the installed Alembic revision runner or SQLAlchemy metadata.
Access and admission tables are still absent from `db.Base` metadata; do not run
autogenerate before reconciliation. The existing startup `create_all` paths must
not become an implicit security migration mechanism.

The unchanged legacy harness still demonstrates unguarded originals/downloads,
thumbnails, face crops, video Range, metadata/counts/search/album/caption reads,
provider calls, destructive operations and voice confirmation omission. Operational
and standalone endpoints remain inventoried and unprotected. Green account tests
do not resolve any of those 84 failures. No claim is made about real media, deployed
services, GPU behavior, installed clients or family acceptance.

## Next implementation step

Reconcile access/admission metadata with the ORM and separate app construction from
database initialization and workers. Rehearse migrations on a synthetic database
using a supplied/authorized local ORM runtime, without installing or touching the
live environment under the current boundary. Build the full-app synthetic harness
and reconcile all runtime routes with the inventory. Then mount the shared adapter
with default-deny handling for every unfinished legacy route and close the first
original/thumbnail/crop/Range paths, checking current library/object authority
before any file stat/open/decode. Reduce the legacy failure ledger only when those
real route checks pass.

Further gates remain: explicit legacy library assignment across all relationships,
search partitioning before top-k, worker/voice authorization, browser sign-in UI,
general quotas, trusted proxy/TLS configuration, crash-slot recovery, password and
owner recovery/change, and mobile contract review. No mobile repository changes,
push, merge, deployment, Windows/Mac mini access or real-data work are authorized
by this local result.

Repository: `vlmPhotoHouse`; branch `codex/mobile-access-foundation`; base
`origin/master` at `932263504ac5fcc3ed178e951991619d8ee87049`. This slice continues
`4764b7fed3862befafda366dbdd2188f402c5b7b` in the existing isolated worktree.
The original checkout and mobile repository remain unchanged.
