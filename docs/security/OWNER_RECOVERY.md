# Offline first-owner recovery and library reopening

This bounded workflow recovers one existing bootstrap owner and one library from a
fully quarantined database. It is implemented in `backend/app/access/owner_recovery.py`
and exposed through explicit commands in `scripts/provision_access.py`. No HTTP API,
wire contract, migration, model, media writer or service control is added.
Only synthetic databases and in-process clients have been exercised.

## Preconditions and exact effect

An independently authorized local operator must review the owner's identity,
post-backup changes/revocations, exact source/code, selected library and its mapped
assets, private matching backup, and stopped application/worker state. The plan
requires opaque `quiescence_reference` and `reconciliation_reference` IDs, in addition
to the existing authority/restore review references. References and digests record
review; they do not authenticate an operator or prove that workers stopped. An
archive cannot reconstruct history that was lost after the backup.

Use a [quarantined migration candidate](DATABASE_PREPARATION.md) or the result of the
[reviewed quarantine service](OFFLINE_RECOVERY.md). The entire database must have
accounts disabled, libraries closed, sessions revoked, unused invitations cancelled,
and no admission/KDF claims. The selected UUID must be the recorded bootstrap
operator and have an approved, nonexpiring owner membership in the selected library.
A viewer, revoked owner, expiring owner, alternate operator or missing record is
refused. This does not infer ownership from a phone number or restored password.

Read-only planning seals a 15-minute plan to the full logical database snapshot,
selected owner/library, references and effect counts. Review verifies a physically
separate matching backup and restores it into memory. Application requires the
exact separately reviewed plan and review digests, and repeats validation after
protected password entry under a SQLite `BEGIN IMMEDIATE` reservation.

| Atomic change | Result |
| --- | --- |
| Password | Prompt twice with echo disabled; refuse fallback, mismatch, invalid length and reuse of the password in the restored record. Hash/verification run sequentially outside the database write lock. Historical passwords absent from the backup cannot be checked. |
| Owner/library | Enable only the selected account and open only the selected library. Existing mapped assets in that library become available to that owner through protected reads. No new account, operator, library or asset mapping is created. |
| Memberships | Advance every membership revision; revoke every membership except the selected owner/library pair. This includes the same owner's memberships in other libraries. Remove all original-access grants everywhere. Revision overflow is refused. |
| Old access artifacts | Keep all old sessions revoked and unused invitations cancelled; rotate the admission/plan key again. No login session or invitation is created by recovery. |
| Audit/receipt | Commit the password, access changes, audit event and durable receipt together. Final barrier/key checks run after receipt and audit writes. |

All other accounts remain disabled and all other libraries remain closed. Membership
roles/mapping history are retained, but approval and original grants are deliberately
revoked. The recovered owner must log in normally with the fresh password. The owner
can then issue a new phone-bound invitation to a **new account** using existing app
behavior. A consumed invitation cannot be reused; old invitations remain invalid.

This is the first-owner recovery path, not bulk restored-account recovery. It cannot
recover an already-existing disabled viewer by issuing another invitation, restore
other owners/libraries, or reconcile lost history automatically. Those require a
separate bounded credential/audience recovery design. Do not work around this by
editing account states or reusing restored passwords. For an empty pre-access
candidate, use reviewed `plan-owner`/asset provisioning instead.

## Operator commands

Keep request, plan, backup and candidate files in a trusted private directory outside
Git/media roots. Every database/JSON path must be explicit and absolute. The request
has exactly four fields (synthetic example, not a real target):

```json
{
  "operator_account_id": "00000000-0000-4000-8000-000000000001",
  "library_id": "synthetic-family",
  "quiescence_reference": "review-stopped-workers",
  "reconciliation_reference": "review-owner-and-history"
}
```

```sh
"$PHOTOHOUSE_PYTHON" -B scripts/provision_access.py plan-recovery \
  --database "$PHOTOHOUSE_CANDIDATE" --request "$PHOTOHOUSE_REQUEST" --out "$PHOTOHOUSE_PLAN"
"$PHOTOHOUSE_PYTHON" -B scripts/provision_access.py validate-recovery \
  --database "$PHOTOHOUSE_CANDIDATE" --plan "$PHOTOHOUSE_PLAN"
"$PHOTOHOUSE_PYTHON" -B scripts/provision_access.py review-recovery \
  --database "$PHOTOHOUSE_CANDIDATE" --backup "$PHOTOHOUSE_BACKUP" \
  --plan "$PHOTOHOUSE_PLAN" --reviewed-plan-digest "$PHOTOHOUSE_PLAN_DIGEST" \
  --authority-reference "$PHOTOHOUSE_AUTHORITY_REF" --restore-reference "$PHOTOHOUSE_RESTORE_REF"
```

After independent review, the explicit `apply-recovery` command takes the same
arguments as `review-recovery`, plus `--review-digest "$PHOTOHOUSE_REVIEW_DIGEST"`.
It prompts for a fresh password; there is no password argument, environment setting,
request-file field or remote reset endpoint. Generic provisioning `apply` cannot
apply a recovery plan, and recovery cannot apply owner/asset provisioning plans.
The existing `receipt` command queries the committed result by exact plan ID/digest.
See [operator tool](OPERATOR_TOOL.md) for private-file checks and exit semantics.

Failure or expiry during password work, stale/replaced target/backup, receipt/audit
failure, entropy failure, replay and concurrent application refuse unsafe writes.
Transactional failures roll back the password, key and all access changes. A lost
success message does not mean application failed: inspect the durable receipt before
retrying. Never restore an old serving file merely to retry a password operation.

## Validation and remaining delivery gates

Focused tests cover planning without writes, the full owner/audience effect,
old-password/token/invitation denial, fresh-owner login/new-account invitation,
protected prompt behavior, stale state after password work, expiry, revision bounds,
identity/backup checks, generic-apply refusal, receipt/audit/entropy rollback, old
plan invalidation, concurrent application, final access barriers and CLI review/apply/
receipt lookup. The real in-process app permits the newly logged-in owner's selected
library/gallery/captions and denies another library, original Range access and old
thumbnail credentials before media open. Protected resource denial remains HTTP 401
under the current wire contract; the retired-route boundary uses 403.

The [current handoff](ANDROID_READINESS_RETURN.md) records exact commits and results.
This is not Windows execution, production-scale recovery, ACL/reparse/crash-durability
validation or physical-phone evidence. Trusted local administrators/filesystem writers
can bypass these tools. No automatic restore detection, service stop, deployment,
cutover/rollback, certificate reload, ingress isolation or live access is implemented.
The first operational stage still needs an independently reviewed synthetic host/
HTTPS/audience plan and subsequent physical-device acceptance.
