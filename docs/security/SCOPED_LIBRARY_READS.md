# Scoped gallery and caption reads — slice 7

Local synthetic checkpoint after `0013a8a`, 2026-09-09. Continues
[the additive schema repair](LEGACY_READ_SCHEMA.md).

Three reviewed GET replacements are mounted in the closed application:

| Route | Selection | Required access |
| --- | --- | --- |
| `/assets` | `library`, optional `page` (1–100000), `page_size` (1–100) | Current active session and approved, unexpired membership in an active library |
| `/assets/detail/{asset_id}` | `library` | Same membership plus mapped active parent asset |
| `/assets/{asset_id}/captions` | `library` | Same membership plus mapped active parent asset before child query |

Library selection is not authority. Every query uses `access_asset_libraries`;
count and pagination happen after scoping. Deleted/unassigned/foreign objects are
indistinguishably denied. NULL legacy asset status remains visible if mapped.
Metadata contains ID, media kind, dimensions, duration, date and a relative scoped
thumbnail URL. Paths, hashes, GPS, model names and processing errors are omitted.
The original-byte grant is reported separately; even owners lack it by default.

Captions include current, non-superseded text, user-edited status and dates; at most
20 rows and 8192 characters per text, with explicit `has_more`/`truncated` flags.
No language is inferred from the model name. HTML in caption text remains JSON
text; clients must render it as text. No model, filesystem or vector index is used.
Unknown/duplicate parameters and query credentials are rejected. Search, albums,
writes, jobs and voice remain closed.

Membership and data share one SQLite read snapshot. A request already authorized
before concurrent revocation may finish; the next request rechecks current policy.
This is not a claim that already-disclosed data can be recalled.

## Evidence

Nine additional real-ASGI tests use fully Alembic-migrated temporary SQLite:
scoped counts/paging, safe response shape, foreign/deleted/unmapped IDs, caption
parent guards, current account/session/library/membership denial matrix before data
SQL, cookie reads and revocation, strict request bounds, and concurrent revocation.

Observed: **120 security tests passed in 16.064 seconds**, no skips/xfails.
The inventory contains **150 entries**, of which **21** are active; runtime route
identity and source completeness checks agree. One prior test expectation changed
from 403 to 401 because normalized `/ui/../assets` now reaches the protected gallery
replacement; it still returns no data without a session.

Changed files: `backend/app/access/library.py`, `backend/app/access/boundary.py`,
`backend/app/main.py`, `docs/security/route_capabilities.json`,
`tests/security/test_library_reads.py`, `tests/security/test_closed_application.py`,
and this document.

Next: a cookie-based web sign-in/invitation flow and scoped read-only gallery with
stale-response cancellation and safe caption rendering. Production connection/TLS
setup, live migrations, backup/recovery, Windows media handling, standalone service
authorization and real mobile acceptance remain separate, unverified gates.
