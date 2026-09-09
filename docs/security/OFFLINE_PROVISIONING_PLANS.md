# Read-only offline provisioning plans — slice 12

Local synthetic checkpoint after `0cb58cf`, 2026-09-09. This is a review artifact
API with **no apply operation, HTTP route or command that changes access**.

`ExistingDatabase(..., read_only=True)` uses SQLite URI `mode=ro` and query-only
mode. `ProvisioningPlanner` refuses a writable planning connection. The planner
reads the existing migrated database through the explicit adapter and never opens
media, hashes files, creates schema, changes credentials or grants membership.

Two explicit plans are available:

| Plan | Reviewed intent and prerequisites |
| --- | --- |
| `owner(phone=…, library_id=…)` | New phone login and new portable library ID; deliberately create owner **and system operator** later. No original grant or automatic legacy mapping. Existing targets are refused. |
| `assets(library_id=…, operator_account_id=…, asset_ids=[…])` | Select 1–10000 unique active unmapped IDs; selected existing account must currently be operator and approved owner of that active library. Foreign/already mapped, deleted or missing assets are refused. |

Asset plans include the current reader count and existing original-reader count.
Assigning an asset would make it available under those existing library grants;
`originals_granted=false` means the plan creates no new original permission, not
that all existing members lack original access. Changes to the audience, grants,
owner revision, selected asset path/hash/status/mapping invalidate the review.
No path, media hash, raw admission key or password is included in the plan.

Plans use a domain-separated HMAC seal and logical database binding derived from
the existing admission key, with a 15-minute lifetime and explicit expected-state
fingerprints. No key is generated or rotated. `validate()` checks integrity,
expiry and current read-only state; its result always says `applied=false`.
The seal is an integrity check for an offline artifact, **not authentication or
permission to apply it**. Identical database backups share the logical binding;
it does not identify a physical host/file. Application must separately establish
operator authority and confirm the exact target database.

## Synthetic evidence

**157 Python security tests passed in 18.465 seconds**, including eleven planner
tests for no DML/schema writes, unchanged database bytes, real SQLite read-only
mode even if query-only is turned off, explicit targets, duplicate/invalid IDs,
current operator/owner requirements, redaction, tampering/expiry/wrong logical DB,
asset/owner/audience changes and stale bootstrap plans. Inventory remains **152
entries / 23 active routes**; no listener, model or additional public surface exists.

The [owner example](evidence/provisioning-slice12/owner-plan.example.json) and
[asset example](evidence/provisioning-slice12/asset-plan.example.json) were generated
and validated against disposable synthetic SQLite, then that database was removed.
Their phone, account, IDs, timestamps and seals are test fixtures. The fixture uses
an artificial clock; these examples cannot authorize a real operation.

## Next reviewed implementation

Implement an offline apply workflow only after this contract is reviewed:

1. Require an explicit existing database target, an independently authorized local
   operator, an exact reviewed plan digest and a separately verified backup/restore
   procedure. Check exact target identity; never infer it from `.env` or defaults.
2. For bootstrap, collect the new password through a protected prompt, never an
   argument/log/plan. Hash outside the write lock, then revalidate all plan state
   under BEGIN IMMEDIATE before creating the owner/operator/library. No first-signup
   ownership or automatic photo assignment.
3. For mapping, revalidate expiry, seal, actor, audience and every selected unmapped
   asset under the same write reservation used for inserts and audit. Apply the exact
   reviewed IDs atomically; reject partial/stale/replayed plans. Record sufficient
   plan/asset evidence for later review without exposing media paths or credentials.
4. Keep original grants separate. Rehearse failures, concurrent membership/mapping
   changes, replay and offline restoration with synthetic data before any live use.

This planner does not establish those apply/audit/backup gates. There is no CLI apply
fallback or manual SQL recipe in this slice. No Windows/Mac mini, real DB/media,
credential changes, deployment, mobile edits, push or merge occurred.
