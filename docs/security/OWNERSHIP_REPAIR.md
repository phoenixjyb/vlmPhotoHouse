# Explicit offline suppressed-person ownership repair

Local source workflow, 2026-09-16. This closes the missing repair-command gap behind
[library management](LIBRARY_MANAGEMENT.md); it is not its Windows cutover or a
device-acceptance gate. No HTTP endpoint, automatic ownership inference, asset
activation, face relabelling, media write, membership change, queue operation or
model job is part of this operation.

## Observed failure this addresses

A saved person can be owned, visible and correct while a small number of its face
references still sit on suppressed assets that were never mapped to any library.
The current `People._exclusive()` ownership check then fails, so the protected
picker disables that identity and it cannot be renamed or used as an assignment
target. Telling the operator why the choice is unavailable is a UI change; it does
not make the identity assignable. This document describes the only reviewed way to
change that state.

## Scope and review

An independently authorized database operator must privately inventory the exact
target person, its remaining suppressed/unmapped assets, the destination library
and an existing active operator who is also that library's approved owner. Do not
infer family ownership from names, folders or face similarity. **Unmapped is not
proof of ownership**: the owner must authorize the exact selected asset set and
accept the ownership change below.

Use a private JSON request with exactly these fields (IDs below are synthetic):

```json
{
  "library_id": "family-a",
  "operator_account_id": "00000000-0000-4000-8000-000000000001",
  "person_id": 42,
  "asset_ids": [101, 102, 103],
  "quiescence_reference": "reviewed-maintenance-record",
  "provenance_reference": "reviewed-ownership-record"
}
```

The selection is 1–500 unique sorted integer IDs and must equal, exactly, the
still-suppressed and still-unmapped assets holding that person's remaining
references. An incomplete or padded selection is refused rather than adjusted.
The target must already be visible through mapped active faces, so the repair never
creates first visibility.

## Authority and effects

The database must already have the protected management schema `d8e5b2f7a904`.
Stop and independently verify **all** database writers before planning/apply: both
servers, schedulers, intake, caption and face workers, and administrative write
sessions. The tool checks rollback-journal mode and refuses recorded running tasks
or pending face work (detection, embedding, clustering, reclustering, label
propagation). Those checks do not prove external processes are stopped. Pending
caption tasks are preserved and their worker must still be stopped.
`quiescence_reference` records the private shutdown evidence and
`provenance_reference` records the ownership decision; neither is authorization.
`--all-writers-stopped` acknowledges that review.

One transaction performs exactly three effects:

1. one `access_asset_libraries` insert per selected asset, for the destination
   library;
2. one `access_person_libraries` insert claiming the target person for the same
   library, with the reviewed operator and initial revision 1;
3. the operation audit entry and the durable provisioning receipt.

During the sealed apply the connection authorizer accepts inserts only into
`access_asset_libraries`, `access_person_libraries`, `access_provisioning_receipts`
and `access_audit`, and rejects every update, delete, other table or trigger-driven
write. Inserts use ordinary `INSERT` with exact uniqueness and foreign-key checks;
`REPLACE`, `IGNORE` and ad-hoc SQL are never used. A failed trigger, a stale audit
row or any unexpected write aborts the whole operation.

The repair does **not** change `assets.status`, face labels or assignments, persons
metadata, embedding artifacts, media, memberships, originals grants, albums or
inference queues. The selected assets stay suppressed.

## Lasting audience and eligibility effects

The mapping is whole-asset ownership, not a target-face-only permission. Mapped
assets remain suppressed now, but the mapping persists: a later change to the asset
status could expose them to library readers, and to members who already hold
original permission. Reactivation or restore must be reviewed separately.

Claiming the person also makes it eligible for rename and as an assignment target
again, and admits it to the scoped worker's owned-person pool for later, separately
qualified matching. The tool enqueues nothing and changes no labels, centroids or
artifacts; existing sealed face-job cohort plans must be reconsidered separately.

Because exclusivity is computed per person over that person's full reference set, a
selection that would leave **another** person exclusive is refused as well. Other
people sharing these assets keep their current restriction and change no
capability, but their asset-ownership references do change; do not describe them as
wholly unaffected. Do not create a duplicate person as a silent workaround.

## Private command workflow

Follow [operator-tool](OPERATOR_TOOL.md) path, ACL, authority and backup rules.
Keep the request, plan, database, backup and restored copies outside Git and media
roots; they contain private family/authentication data.

```sh
"$PHOTOHOUSE_PYTHON" scripts/provision_access.py plan-person-repair \
  --database "$PHOTOHOUSE_DATABASE" --request "$PHOTOHOUSE_REQUEST" --out "$PHOTOHOUSE_PLAN"
"$PHOTOHOUSE_PYTHON" scripts/provision_access.py validate \
  --database "$PHOTOHOUSE_DATABASE" --plan "$PHOTOHOUSE_PLAN"
"$PHOTOHOUSE_PYTHON" scripts/provision_access.py review \
  --database "$PHOTOHOUSE_DATABASE" --backup "$PHOTOHOUSE_BACKUP" \
  --plan "$PHOTOHOUSE_PLAN" --reviewed-plan-digest "$PHOTOHOUSE_PLAN_DIGEST" \
  --authority-reference "$PHOTOHOUSE_AUTHORITY_REF" --restore-reference "$PHOTOHOUSE_RESTORE_REF"
"$PHOTOHOUSE_PYTHON" scripts/provision_access.py apply \
  --database "$PHOTOHOUSE_DATABASE" --backup "$PHOTOHOUSE_BACKUP" \
  --plan "$PHOTOHOUSE_PLAN" --reviewed-plan-digest "$PHOTOHOUSE_PLAN_DIGEST" \
  --authority-reference "$PHOTOHOUSE_AUTHORITY_REF" --restore-reference "$PHOTOHOUSE_RESTORE_REF" \
  --review-digest "$PHOTOHOUSE_REVIEW_DIGEST" --all-writers-stopped
```

Replay of an applied plan is refused. Use `receipt` with the exact plan UUID and
digest after an interruption; never blindly retry.

## Refusals

The plan is refused for: an unreviewed schema revision, foreign keys disabled, a
non-rollback-journal database, recorded running tasks or pending face work, an
operator who is not the library's active approved owner, unknown or duplicated
selection, a target that is already owned or already mapped, an asset that is not
suppressed, a foreign or missing reference, a selection that does not exactly cover
the target's unmapped references, a target with no mapped active face, any person
whose capability set would change except the target, and budget overruns (10,000
memberships, 200,000 rows, 64 MiB or 30 seconds per state scan).

## Verification and remaining gates

Synthetic coverage in `tests/security/test_suppressed_ownership_repair.py` uses a
temporary database and forbids socket, subprocess and shell I/O. It covers the
target-only grant with unchanged legacy rows, the all-writer confirmation, replay
denial, exact-set and collateral-ownership refusal, the other-identity unlock
refusal, foreign and missing references, staleness after a new unassigned face,
pending face work with a preserved caption queue, the active-mapped-face
precondition, stale audience/backup/expiry/schema refusal, complete rollback on a
failing trigger and on a partial mapping failure, trigger-driven side-effect
denial, and a concurrent apply that commits once. Local, synthetic evidence only.

Before any live apply: obtain the owner's exact-scope decision, a separate
maintenance approval, a verified full backup with a rehearsed restore into a
separate private scratch database, checks that public suppression still denies
listing/search/detail/captions/Stories/thumbnails/originals/face crops and legacy
routes, confirmation that no new membership, original grant, automatic assignment
or model job is introduced, and a sealed readback of the receipt and the exact
ownership rows after a single apply. Then the owner privately signs in, confirms
the person is selectable, checks the face and explicitly performs the normal
face-assignment API operation; device and family acceptance are separate evidence
and are not implied by a successful repair.
