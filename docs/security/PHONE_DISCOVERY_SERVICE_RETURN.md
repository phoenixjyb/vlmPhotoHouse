# PH-PHONE-DISCOVERY-SERVICE-01 — return

Status: **PASS_INTERNAL_SERVICE_ONLY**. No new HTTP endpoint exists and no new
wire contract is frozen. Android must not call or freeze the internal replay JSON.

## Exact source and scope

- Branch: `codex/backend-home-tv-feed`.
- Worktree: the existing `_worktrees/backend-home-tv-feed` under the PhotoHouse workspace.
- Base: `8d8e88974b8be515ad5a9ab088b91a94652b1e71`.
- Implementation: `ddfb0fb893d96482eb1b4b1015328c66ec96077c`.
- The separate evidence commit contains this return and its receipts; identify it
  with `git log -1 --format=%H -- docs/security/PHONE_DISCOVERY_SERVICE_RETURN.md`.
- Local commits only; no push, merge, Windows access, deployment, models, real
  database/media, listeners, credentials or Android edits.

New source files:

1. `backend/app/access/discovery.py`
2. `backend/app/access/discovery_provider.py`
3. `tests/security/phone_discovery_fixture.py`
4. `tests/security/test_phone_discovery.py`
5. `docs/security/PHONE_DISCOVERY_SERVICE.md`
6. `docs/security/evidence/phone-discovery-service/replay.py`

The [service guide](PHONE_DISCOVERY_SERVICE.md) describes the internal types,
authorization, metadata rules, transaction semantics and limits. Existing frozen
constructors, runtime mounts, protected routes, shared contracts and schema were
not modified. There is one service/provider write owner in this worktree.

## Verified evidence

- **158/158 selected regression tests passed**, no skips: discovery, account/access
  foundation, transport, library reads, closed application, membership management,
  runtime adapter and route inventory.
- **25/25 focused discovery tests passed again from 15 extracted committed blobs**.
- **10/10 synthetic internal replay checks passed** from that extraction, producing
  exactly the same result hashes as the worktree replay.
- **10 protected-phone and 19 home-discovery frozen input hashes unchanged**.
- Route inventory complete: **162 method/path entries**, zero new routes.
- Guide rendered to HTML; headings, code block and local link checked. No visual
  browser inspection or device acceptance is claimed.

Receipts: [verification](evidence/phone-discovery-service/verification.json),
[source hashes](evidence/phone-discovery-service/source-inputs.json),
[regression log](evidence/phone-discovery-service/regression.log),
[extracted focused log](evidence/phone-discovery-service/extracted-focused.log),
[replay result](evidence/phone-discovery-service/replay-result.json).

From an extraction of the manifest's paths at its `implementation_commit`, using
the existing isolated CPU access-test environment, reproduce with:

```sh
python -m unittest discover -s tests/security -p 'test_phone_discovery.py' -v
python docs/security/evidence/phone-discovery-service/replay.py --source-root "$PWD"
```

The new service checks current `library.read` inside the existing owned
transaction before provider lookup or metadata. Six combined filters, reviewed
library rosters/pins/manual evidence, native string IDs through `2^63-1`, scoped
counts, source freshness, session/member/index bindings, stable paging and shared
row/byte/time/concurrency limits are covered by synthetic tests. It never grants
original access or derives person approval from captions/DNN assignments.

Android's source-projection review correction is included: complete bounded SQL
values use BLOB byte lengths. Invalid/oversized dates become unavailable rather
than valid truncated prefixes; embedded NULs remain visible to validation; an
oversized caption candidate cannot silently select a fallback. Three adversarial
tests cover those cases. The digest describes the bounded semantic projection,
not excluded oversized tails or every byte in the database.

## Remaining gaps and next step

The service is not end-to-end phone discovery. No trusted real index is loaded;
reviewed provider assertions still require an approved producer and operator
review. No new HTTP authentication/CSRF/body/error handling or browser/client
lifecycle exists. Prepared viewer image/video delivery remains separate and must
not be simulated by granting originals. Legacy and standalone authorization gaps
remain explicitly inventoried; this slice does not repair them.

Budget checks are cooperative, not hard memory or preemptive provider/lock/I/O
limits. Future wiring must supply dedicated SQLite connections and one shared
budget, with reviewed busy timeouts. An already-admitted authorized snapshot may
finish after a concurrent revoke/hide/remap; the next request refuses. Production
size, live freshness, deployment and physical device gates remain unverified.

Next proposed capsule: review and freeze protected discovery HTTP/schema around
these service semantics, with exact inventory/handler boundaries, bearer and
cookie/CSRF policy, bounded JSON/error mapping, and producer-to-Android synthetic
replay. Then separately review prepared viewer-media capabilities and client
logout/background/library-change cancellation. Neither capsule is started here.

Android can continue its authorized UI/media work against existing frozen
contracts and independently review this source pin. Keep discovery unavailable
until the new protected transport and contract are reviewed and implemented.
