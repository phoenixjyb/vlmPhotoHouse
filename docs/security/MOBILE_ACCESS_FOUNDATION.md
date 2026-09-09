# Mobile access foundation: route audit, slice 1

Status: **inventory and synthetic failure evidence only; authorization is not
implemented. This branch is not a security deployment candidate.**

Audit baseline: `932263504ac5fcc3ed178e951991619d8ee87049` (`origin/master`, refreshed
2026-09-09). The original checkout was clean on `codex/insightface-cuda-runtime`
at `752ab3bfb2ec48558bae747948185ceabb66a229`. Historical handoff dirty-state notes
were read but did not describe the observed checkout. Work is isolated on
`codex/mobile-access-foundation`; no original-checkout files were edited.

Inputs: repository AGENTS and its complete agent-memory pack; mobile planning
documents `DEVELOPMENT_PLAN.md`, `SECURITY_AND_VOICE.md`, and section A of
`SESSION_CAPSULES.md` from the sibling mobile repository. These are proposed
requirements, not evidence of current protection. The mobile repository is unchanged.

## Required access contract (proposal, version 1)

Registration grants **zero library access**. A verified identity can see only its
own account/request state until a library owner approves membership or the intended
principal explicitly accepts an owner invitation. Never grant ownership to the
first signup. A deliberate operator bootstrap establishes the first owner.

`route_capabilities.json` is the authoritative, per-method inventory. Every row
names its source handler, service surface, proposed capabilities, object scope,
current controls and open gap. Capability lists mean **all** listed requirements;
`voice.command.dispatch` additionally requires the specific intent's authority.
These are review vocabulary, not frozen mobile DTOs or implemented role mappings.

| Capability | Proposed authority |
| --- | --- |
| `public.ui` | Code-only shell, static UI files and redirects. No embedded private data. |
| `library.read` | Verified account with current approved membership in the selected library. |
| `media.original.read` | Separate original-byte grant in addition to library read; includes inline previews and Range. |
| `library.curate`, `library.upload` | Separately approved contributor/owner capabilities; deferred from the read-only mobile release. |
| `library.destroy` | Approved owner, explicit policy and bound confirmation; disabled in the initial release. |
| `system.read`, `system.jobs` | Explicit operator authority. Household owner is not automatically an operator. |
| `service.invoke` | Internal authenticated service identity plus authorized, scoped job and resource admission. |
| `voice.read`, `voice.conversation` | Approved library and voice permission; server-owned account/library/session conversation mapping. |
| `voice.command.dispatch` | Read, operator-status or domain-mutation checks according to intent. Feature enablement is insufficient. |

Operators have no implicit permission to browse family photos. Face/person identity
does not represent a login account. IDs, paths, headers, body roles, client IDs,
transcripts, network reachability and VPN membership never grant authority.

## Inventory coverage and completeness guard

| Surface | Explicit routes | Framework GET/HEAD entries | Middleware entries |
| --- | ---: | ---: | ---: |
| PhotoHouse main app, including all five included routers | 94 | 8 | 0 |
| Standalone LVFace service | 3 | 8 | 1 |
| Standalone RAM++ service | 2 | 8 | 0 |
| Standalone diagnostic server | 2 | 8 | 0 |
| Total | 101 | 32 | 1 |

The 134 entries include legacy unprefixed paths; originals (`download=true` too);
thumbnail cache hit and generation paths; face crops; video bytes and Range through
the same original route; video/segment metadata; all text, tag, vector, person and
video searches; seeds, result rows and aggregates; people/history; album drafts,
story/time groups, item IDs and covers; captions/tags; uploads and deduplication;
destructive operations; ingest, indexes, tasks, metrics, diagnostics; all voice
routes; static UI and redirects; generated schema/docs/OAuth redirect handlers.
There are no implemented registration or membership endpoints to inventory yet.

All five main router includes currently use an empty prefix and the routers have
no prefix. Source paths in the inventory therefore equal mounted paths. The guard
pins constructors, includes and middleware expressions: changes to prefixes,
documentation settings, mounting or registration syntax require review. It scans
tracked and untracked, non-ignored Python source with Git, then strictly parses
HTTP candidates without importing modules. Unrelated old CLI files with invalid
Python are not imported or parsed as HTTP surfaces. No candidate parse error is
silently ignored. Unsupported mount/dynamic registration forms fail the check.

FastAPI's generated docs/schema routes accept GET and HEAD. Current decorated
GET API routes do not implicitly add HEAD in the tested framework. Main-app
OPTIONS/HEAD against media return 405; this is method handling, not authentication.
LVFace's wildcard CORS middleware handles preflight OPTIONS separately. Its
inventory requirement covers protection of the target service; a future reviewed
preflight policy may allow anonymous non-data negotiation. Neither CORS nor a
future HEAD/Range/conditional variant may bypass authorization of actual bytes.

This is a source inventory guard, not proof against arbitrary Python metaprogramming,
external proxy routes or deployment mounts. Before enforcement cutover, reconcile
it against actual `app.routes` in a fully isolated application harness (including
conditional configurations and every registration method). Unknown routes must be
protected by the application policy itself, independently of this checker.

## Existing authorization failures

| Gap | Current source/evidence | Required closure |
| --- | --- | --- |
| G1: no inbound identity or membership | Main middleware logs requests; DB models contain no Account/Library/Membership. Dependencies supply DB sessions, not an authorized principal. | Verified identity, current membership and common fail-closed policy. No pending-user browse. |
| G2: direct media disclosure | `get_asset_media`, `get_asset_thumbnail`, `get_face_crop` resolve global IDs/files without account or parent-library checks. Synthetic originals, downloads and derivatives return 200; Range returns actual bytes with 206. A deleted asset still serves its original. | Authorize parent and capability before stat/open/decode/cache generation; recheck every request. |
| G3: global queries and aggregates | Browse/search, tags, people/history, captions, video metadata and albums query global rows. Album active/draft validation is not authorization. Vector search embeds a seed and searches global top-k before result filtering. | Scope seeds, every result, joins, nested/bulk IDs, covers and counts; partition retrieval before top-k. |
| G4: unrestricted operations and writes | Ingest accepts filesystem roots; tasks/index operations have no operator check. Metadata deletion/curation helpers have no principal. Synthetic probes reach ingest, file-deletion and commit doubles. | Separate operator/domain grants; scoped audited delayed jobs with execution-time reauthorization. |
| G5: voice caller/conversation confusion | Feature/config checks and outbound provider keys do not authenticate callers. Chat delete forwards caller conversation IDs; pending actions are keyed by caller `client_id`, and `_pop_pending_action` accepts an omitted token. All reproduced with provider/storage doubles. | Owned conversation mapping, shared authorized services, mandatory principal/session/library/argument-bound single-use confirmation; v1 read-only intents. |
| G6: disclosures outside media | Rich `/health`, metrics, task errors, schemas and optional service diagnostics are anonymous. Main exception handler returns `str(exc)`; response models expose filesystem paths/GPS/hashes. UI search redirects include query text. | Minimal public liveness if required; protected/redacted diagnostics and typed errors; no unnecessary private paths or query logging. |
| G7: voice correctness/privacy | Voice-photo handlers reference obsolete `Asset.caption_text`, `date_taken`, GPS/file-name fields; several provider failures use HTTP 200. Provider admission and ownership are absent. Source review only here. | Repair or retire obsolete handlers; typed errors, bounds, cancellation, admission and privacy decisions before provider integration. |
| G8: no secure migration/web/session boundary | No reviewed account/library migration, owner bootstrap, revocation, cookie/CSRF or verified bearer adapter. Global upload hash dedup can disclose existing IDs. | Explicit synthetic migration rehearsal and shared web/mobile policy; preserve existing IDs/originals. |

Thumbnail generation misses, real SQL scoping, every mutation and every optional
service were inventoried/source-reviewed, but were not dynamically exercised.
The media tests use cached synthetic bytes, not valid decoded video/image files.
They prove transport disclosure, not player or codec behavior.

## Reproduce locally without a runtime

From this worktree root:

```sh
python3 scripts/security_inventory.py
python3 -m unittest discover -s tests/security -v
python3 tests/security/harness.py
```

The first two commands must pass. The third is the **security denial gate** and
currently exits **1**, printing every failed requirement. Do not suppress its exit
status, mark failures as permanent skips/xfails, or count the green characterization
tests as security acceptance. On implementing protection, replace the relevant
insecure-behavior assertions with real denial/approved-access tests; do not preserve
the vulnerability merely to keep characterization tests passing.

No repository `.venv` is available on this Mac. The standalone suite uses the
already installed host Python, FastAPI, Starlette, HTTPX and Pydantic; no packages
were installed. This deliberately does not invoke the runtime test configuration,
which imports settings, initializes the DB/executor and has a global skip option.
No runtime `.env`, database, model, worker or startup hook is loaded. Selected source
function signatures/decorators/bodies are executed unchanged in a synthetic namespace;
the real FastAPI constructor and Pydantic response schemas are used. ORM calls,
provider calls, ingest and deletion are doubles. Temporary synthetic files are the
only media. Network bind/connect and process launch are blocked during the harness.

Observed local verification on 2026-09-09: Python 3.14.7, FastAPI 0.135.2,
Starlette 1.0.0, HTTPX 0.28.1, Pydantic 2.12.5. Inventory: 134 entries, exit 0.
Focused unittest suite: 21 passed, zero skips/expected failures. Strict denial
runner: 84 failed security requirements, exit 1. These host versions are evidence
of this run, not new production dependency pins or a Windows framework claim.
Full backend tests, real SQL integration, migrations, provider/model execution,
web/browser and native-device acceptance were not run. No services were started,
network ports exposed, credentials changed, Windows/Mac mini hosts accessed, or Git refs pushed.

Seven denied-state labels across eleven reads produce 77 probes. Anonymous/viewer
labels across ingest, deletion and foreign-conversation deletion add six. The
omitted-token confirmation probe brings the total to 84. **All 84 currently fail.**
The invalid bearer strings are synthetic labels, not valid pending/revoked/viewer
tokens. Two asset labels describe intended distinct libraries, which do not exist
in the current schema. Query doubles return both fixture rows and do not evaluate
SQL. These results demonstrate ignored credentials and exposed handlers, not a
completed cross-library/membership/expired-token integration test.

Future acceptance must add verified anonymous/unapproved/revoked/expired/wrong-library
and malformed/expired-token denials, viewer write denial, approved viewer reads,
original-grant separation, nested/bulk foreign IDs, stale tasks, query partitions,
invitation replay, membership races, migration integrity and web CSRF/session tests.

## Next reviewed slice: accounts, membership and shared policy

Review the following design with the coordinator before implementing schema/provider
changes or freezing the mobile contract. No migration or provider choice is made here.

1. Define a verified-principal boundary keyed by exact OIDC issuer/subject, with
   explicit issuer/audience/signature/token-type/expiry validation and fail-closed
   provider failure. A fake adapter may exist only in isolated synthetic tests.
   Choose a maintained provider separately; never implement an OAuth server or
   trust caller-supplied account/library/role fields.
2. Review Account, Library, Membership and invitation/session records. Membership
   has requested/approved/rejected/revoked state, role, explicit grants, expiry,
   revision and approver. Enforce unique issuer/subject and account/library pairs.
   Invitation acceptance must be bound to the intended verified principal,
   expiring and atomically single-use; store token digests. Registration creates
   no memberships or owner. Require an explicit audited bootstrap and reject
   bootstrap races. Prevent last-owner removal without an approved recovery path.
3. Add an explicit migration, rehearsed on newly created synthetic legacy DBs.
   Assign legacy rows to an explicitly supplied library/owner, validate all child
   and many-to-many links (faces/people, captions/tags, albums/covers, tasks and
   index partitions), preserve asset IDs and paths, and fail closed on ambiguity.
   Define backup/restore and rollback behavior; never restore anonymous access on
   migration failure. No startup `create_all`/fallback edits as a substitute.
4. Implement a shared authorization context and policy/query services accepting a
   verified principal and current server-owned membership revision. Deny absent,
   pending, revoked, expired or foreign membership before files/providers/writes.
   Separate original, curation, destructive and operator grants. HTTP routes,
   voice dispatch and delayed jobs must all call the same services; recheck jobs
   when executed. Scope queries and indexes at retrieval, not after global top-k.
5. Prove the policy and migration with two accounts, two libraries, revoked sessions,
   expired memberships, nested/bulk IDs and concurrency/replay tests on synthetic
   SQL. Then close every inventoried legacy route and add runtime route-table
   reconciliation. Use approved reads plus denial-before-side-effect assertions.
   Account deletion/owner transfer and profile/request visibility need contracts.
6. Before any enforcement deployment, integrate the existing web UI with secure
   HttpOnly sessions, CSRF protection and login/pending/expired states. Native
   bearer and web cookie requests use identical policy; images/video authenticate
   each request without query credentials. Provider/TLS selection, revocation and
   refresh semantics, deployment rehearsal and real-device acceptance remain gates.

The next implementation task should stop after the reviewed synthetic
account/membership migration and shared-policy tests. Provider installation,
credentials, Windows/Mac mini access, network exposure and deployment require
separate authority. A partial policy or a new mobile URL prefix cannot close the
existing unauthenticated application.
