# Explicit offline people and album ownership import

Local source workflow, 2026-09-15. This closes the missing import-tool gap in
[library management](LIBRARY_MANAGEMENT.md), not its Windows cutover gates.
No HTTP endpoint, automatic ownership inference, password setup, migration,
worker control or media write is part of this operation.

## Scope and review

An independently authorized database operator must privately inventory and select
the exact unowned person and album IDs, their destination library and an existing
active operator who is also that library's approved owner. Do not infer family
ownership from names, folders or face similarity. Existing ownership, even in the
same library, is refused. Never use ad-hoc ownership SQL to repair a refusal.

The database must already have the protected management schema `d8e5b2f7a904`.
First qualify the native migration/backup/restore procedure separately. Stop and
independently verify **all** database writers before planning/import: both servers,
schedulers, intake, caption and face workers, and administrative write sessions.
The tool checks rollback-journal mode, recorded running tasks and pending face
jobs (detection, embedding, clustering, reclustering and label propagation), but
these checks do not
prove that external processes are stopped. Pending caption tasks are preserved;
their worker must still be stopped during import. `quiescence_reference` records the
private shutdown evidence; `--all-writers-stopped` acknowledges that review. Neither
is authorization, process detection or a replacement for the host-side check.

Use a private JSON request with exactly these fields (IDs below are synthetic):

```json
{
  "library_id": "family-a",
  "operator_account_id": "00000000-0000-4000-8000-000000000001",
  "person_ids": [12, 15],
  "album_ids": [7],
  "include_orphan_people": false,
  "include_empty_albums": false,
  "quiescence_reference": "reviewed-maintenance-record"
}
```

Select 1–500 combined unique integer IDs per plan. All existing face references
of a person must map to this library, including references to inactive assets.
An unlinked person requires the explicit orphan flag. Albums must be compatible
drafts with at most 60 unique, ordered, active mapped assets and a valid cover.
An empty album requires the explicit empty flag. Published albums, mixed/unmapped
references and incompatible metadata require a separate decision/correction; the
tool does not silently omit, truncate or rewrite them. Metadata and review budgets
are bounded (200,000 total links, 10,000 memberships, 30 seconds per state scan).
These bounds do not impose caption/story word limits.

## Private command workflow

Follow [operator-tool](OPERATOR_TOOL.md) path, ACL, authority and backup rules.
All variables below must identify separately reviewed private native paths or
references. Keep the request, plan, database, backup and restored copies outside
Git and media roots; they contain private family/authentication data.

```sh
"$PHOTOHOUSE_PYTHON" scripts/provision_access.py plan-management \
  --database "$PHOTOHOUSE_DATABASE" --request "$PHOTOHOUSE_REQUEST" --out "$PHOTOHOUSE_PLAN"
"$PHOTOHOUSE_PYTHON" scripts/provision_access.py validate \
  --database "$PHOTOHOUSE_DATABASE" --plan "$PHOTOHOUSE_PLAN"
"$PHOTOHOUSE_PYTHON" scripts/provision_access.py review \
  --database "$PHOTOHOUSE_DATABASE" --backup "$PHOTOHOUSE_BACKUP" \
  --plan "$PHOTOHOUSE_PLAN" --reviewed-plan-digest "$PHOTOHOUSE_PLAN_DIGEST" \
  --authority-reference "$PHOTOHOUSE_AUTHORITY_REF" --restore-reference "$PHOTOHOUSE_RESTORE_REF" \
  --restore-out "$PHOTOHOUSE_REVIEW_RESTORE"
```

Plan, validate and review never write the selected database. Review binds a
separate matching full logical backup and verifies SQLite restoration; it does
not certify a real-host disaster recovery. Both input databases must be offline
DELETE-journal files without sidecars and no larger than 2 GiB. For full-size
review use the explicit new disk restore output, not the default in-memory copy.

Review the sealed selection/effects and capture the actual plan/review digests.
Plans expire after 15 minutes; changes to records, ownership, membership/audience
or the full backup snapshot require a fresh review. Under separately authorized
application, use the same arguments with `apply`, plus:

```sh
  --review-digest "$PHOTOHOUSE_REVIEW_DIGEST" --all-writers-stopped \
  --restore-out "$PHOTOHOUSE_APPLY_RESTORE"
```

The apply restore must be a different new private file. Application obtains a
write reservation, revalidates the sealed state and backup, and inserts only the
selected ownership rows, one audit event and one durable receipt. A final state
check precedes commit. Legacy names, albums/items, face assignments/counts/vectors,
asset ownership, accounts, memberships, originals permissions and media remain
unchanged. Existing library members gain visibility of imported albums; only
current owners manage people. This does not publish anything to TV, SMB or another
library. The plan reports the current affected reader/manager counts.

For lost output, use the existing `receipt` command with exact plan ID and digest
before deciding whether any further action is needed. A committed plan cannot be
applied twice. Failures roll back the transaction; they do not undo an earlier
successful import. There is no automatic unimport or backup restore command.

## Delivery gates

Synthetic tests cover CLI planning, refusal, restoration review, atomic apply,
visibility and receipt recovery. They do not qualify native Windows ACLs, full-size
timing/memory, process shutdown, the active database or real family acceptance.
Rehearse those before any live import, then verify protected people/album browsing
with the intended owner/member accounts. Set the owner's password privately using
the separately reviewed owner workflow, never in chat or this import request.

Final local validation: 716 security tests in 144.676 seconds, OK with five skips
(four native Windows checks and one legacy-worker dependency check). The 19 focused
import/migration tests pass, including queued face-job refusal, unchanged pending
captions, real apply-time rollback and c7-to-management DDL failure preservation.
The source smoke exercises 14 operator commands, nine database-preparation commands
and seven ASGI checks without opening listeners or accessing live data. No visual
UI code changed in this slice; browser/device acceptance was not repeated.

Automatic clustering, reclustering and label propagation remain incompatible with
manual unassignments and library ownership. Keep them disabled for this release
until scoped worker fixes and tests are qualified. Caption-only operation is a
separate compatibility check and is not changed by this local implementation.
