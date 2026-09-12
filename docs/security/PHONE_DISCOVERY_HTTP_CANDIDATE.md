# PH-PHONE-DISCOVERY-HTTP-CANDIDATE-01

2026-09-12. Candidate protected discovery transport over the existing
`DiscoveryReads` service. **Not Android-approved, frozen, deployed or wired into
the default app.** The previous protected-phone and anonymous-home contracts are
unchanged. Prepared viewer images/video remain a separate capability slice.

## Source and composition

Base `9881769baf8182536a0e9fbbe39648d534167970`; branch
`codex/phone-discovery-http-candidate`, worktree
`_worktrees/phone-discovery-http-candidate` in the PhotoHouse workspace.
The source is separate from the Windows preparation job's pinned `ee5c06f` files.

Only `app.phone_discovery_candidate.create_candidate(discovery_runtime=...)`
composes the candidate routes. Supply a `DiscoveryRuntime` with the existing
`AccessRuntime`, an explicitly reviewed provider and **one shared** `ReadBudget`.
There is no module-level candidate application or runtime configuration discovery.
The factory composes the existing account/library/media/UI routers and exactly two
new operations. `CandidateBoundary` checks method, route template **and endpoint
identity**; shadowing or adding an unrelated handler does not grant access.
The default `app.main.create_app()` and its boundary remain byte-identical.

The connection factory must create/close a dedicated SQLite connection inside the
worker thread, with foreign keys on, no pending transaction and a reviewed short
busy timeout (the fixture uses 250 ms). A read-only/query-only connection is used
by the synthetic discovery fixture. There is no automatic schema migration or
trusted-index builder. Shared budgets are cooperative; provider/connection/OS I/O
cannot be preempted merely by setting the cancellation flag.

## Candidate operations

| Method and path | Inputs | Success |
| --- | --- | --- |
| `GET /libraries/{library_id}/discovery/v1/facets` | Optional `facet=people\|tags\|locations`, `page=1`, `page_size=50`, `binding` | One facet page, ordered pins, coverage and opaque binding |
| `POST /libraries/{library_id}/discovery/v1/search` | Exact JSON keys `binding`, `filters`, `page`, `page_size`, `fingerprint` | Matching asset page and normalized-query fingerprint |

GET pages range 1–5,000; POST pages 1–100,000; page sizes 1–100. A later facet
page requires binding. Search always requires binding and a `fingerprint` key:
use JSON `null` on page 1; later pages require the first response's fingerprint.
Search order is descending numeric asset ID. Empty filters browse all visible
mapped assets, including assets outside the reviewed metadata index. Metadata
filters only match indexed assets with supporting values. Counts never imply
caption/tag completeness.

GET accepts at most four unique named query fields and 1,024 query bytes.
Malformed percent encodings, duplicate/unknown parameters, noncanonical positive
page integers and framed request bodies are rejected. POST accepts no query or
content encoding. Use `application/json` with optional UTF-8 charset. The received
body is limited to 20 KiB and two seconds, independently of Content-Length;
provided lengths must agree. JSON rejects duplicate keys at any depth, nonfinite
constants, invalid UTF-8/surrogates, more than 1,024 structure nodes or depth six.
Filters remain limited to 16 KiB in the service; caption text to 512 UTF-8 bytes.
The schema expresses structure; these byte limits and cross-field semantic rules
also apply and are enforced by the implementation.

All numeric asset/person/tag/place IDs and index revisions are **decimal strings**
in `[1, 9223372036854775807]`; no floats, signs or leading zeros. Library IDs are
opaque strings, not coerced to integers. Page/count fields remain bounded JSON
integers. Binding/fingerprint are opaque 64-character lowercase hexadecimal
strings, bound to current session/account/membership/index/scope. They are not
credentials or authorization grants.

Filters support people/tags `{ids:[string],match:"any"|"all"}`, location ID arrays,
media arrays (`image`, `video`, `other`), inclusive recorded dates `{from,to}`
(each ISO date or null, at least one non-null), and literal normalized caption
text. ID lists must be unique, nonempty and at most 20. Cross-category predicates
combine with AND. Unknown/disabled filters or unreviewed facet IDs fail. Themes
and topics remain explicitly unavailable without a reviewed taxonomy.

Responses add `version: 1` to the established service projection. Facets report
`enabled`, coverage, catalog/index counts, index completeness, date bounds,
ordered pinned people, facet pagination and provenance. Search returns bounded
asset metadata, protected thumbnail URLs, paging, binding/fingerprint and current
`originals_allowed`. Descriptive dimensions outside 1–1,000,000 and invalid
negative/oversized durations are projected to null. No prepared media or original
URL is synthesized. `originals_allowed` reports existing policy; discovery does
not grant it. Responses are capped at 512 KiB or the supplied smaller budget.

The [JSON Schema](phone-discovery-http-candidate-schema.json) lists every allowed
response field and separate request definitions. The [actual producer examples](phone-discovery-http-candidate-examples.json)
cover facet pages, all filters, a maximum 64-bit ID, search pagination and denials.

## Authentication, freshness and errors

Native clients use the existing explicit `Authorization: Bearer` transport and
omit Origin/cookies. Browser reads use the existing HttpOnly cookie plus a positive
same-origin signal. Browser POST requires the exact configured Origin and matching
CSRF token. Mixed bearer/cookie, duplicate credentials, foreign origins, untrusted
Host or non-HTTPS requests are rejected. Existing privacy headers are applied on
success and failure: no-store/no-cache, no-referrer, nosniff and same-origin CORP.
No CORS grant or proxy trust was added.

The transport checks current membership before parsing discovery-specific inputs.
The service reauthorizes in the actual source-read transaction after body receipt,
before provider lookup or metadata/counts. A revoke during body upload is denied.
Current scope/source digest and membership/session/index binding are checked before
results; changing filters or page size changes the search fingerprint. As already
documented for the service, a read admitted before a concurrent revoke may finish
from its authorized snapshot; the next request refuses.

Candidate route errors contain exactly `error` and a generic `detail`, never the
input, SQL, path or provider exception. Existing boundary denials retain the frozen
`{"detail":"Access denied"}` shape (for example unsupported method/unmatched URL).

| Status | Candidate error | Client action |
| --- | --- | --- |
| 400 | `invalid_request` | Correct input/transport; do not retry unchanged |
| 401 | `access_denied` | Clear protected results and reconcile session/membership |
| 403 | `access_denied` | Correct browser origin/CSRF/credential mode |
| 408 | `request_timeout` | Body receipt timed out |
| 409 | `discovery_changed` | Discard dependent pages and obtain fresh facets/binding |
| 413 | `request_too_large` | Reduce body/declared length |
| 429 | `discovery_busy` | Honor `Retry-After: 2` |
| 499 | `request_cancelled` | Connection/request cancelled; no result to adopt |
| 503 | `discovery_unavailable` | No current usable index/runtime, budget exhausted or private internal failure |

Disconnect observation starts after body consumption. It signals the service's
cooperative budget and releases the watcher; it does not interrupt arbitrary
blocking I/O. Clients must cancel and discard stale requests on logout, account or
library change, binding replacement and background lifecycle transitions.

## Evidence and reproduction

- 17 focused candidate HTTP tests passed.
- 151 selected regression tests passed, no skips: candidate/internal discovery,
  account transport, closed application, library/member reads, runtime adapter and
  inventory.
- 164 method/path inventory entries complete. Inventory coverage does not repair
  the explicitly retained legacy/standalone authorization failures.
- 14 freshly regenerated synthetic producer examples matched the committed bytes
  semantically and conformed to Draft 2020-12 schema. Three valid and seven invalid
  ID boundary cases plus five invalid response shapes were checked.

```sh
python -m unittest discover -s tests/security -p 'test_phone_discovery_http.py' -v
python scripts/security_inventory.py
# Test-only dependency jsonschema==4.25.1; no service installation required.
python scripts/check_phone_discovery_http_candidate.py
# Choose a NEW output file. This builder never reads a real database/index.
python scripts/build_phone_discovery_http_fixture.py --output candidate-examples.json
```

Android must independently review candidate source, schema, examples and checksums
before importing a new opt-in contract. No persistent client cache or offline
permission is granted here. Next backend capability review should cover protected
prepared-derivative descriptors/Range reads, revision/hash binding, authorization
on every request, freshness/revocation and logout/library-change cache disposal.
Do not reuse the anonymous home-feed authorization exception for phone access.
