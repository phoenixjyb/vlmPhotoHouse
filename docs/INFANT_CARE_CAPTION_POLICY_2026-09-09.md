# Owner-reviewed baby-care wording — source only

The owner confirmed that neutral descriptions mentioning a diaper or no clothing
are acceptable for the four baby-photo failures recorded in
[caption continuation](CAPTION_CONTINUATION_2026-09-09.md). Their wording-policy
decision is now resolved; retry/deployment acceptance remains outstanding.

This source change provides an opt-in exception through the operator-only
`CAPTION_INFANT_CARE_ASSET_IDS` environment variable: a comma-separated list of
explicit reviewed asset IDs. Its default is empty. Invalid configuration grants
no exception. No real IDs are embedded in the implementation, and a task/client
payload cannot turn this on. Configuration must target the approved assets in the
same reviewed database; do not copy the allowlist into another library/database.

For selected assets only:

- The initial prompt explicitly permits factual, nonsexual baby-care wording.
- Validation permits `diaper`, `no clothing`, `without clothing`, `尿布` and
  `没穿衣服`, while leaving other validation rules unchanged.
- Chinese corrective translation excludes these permitted words from its avoid
  list; the existing speculative/activity restrictions remain.
- Corrective prompts retain the scoped exception. Final replacement validation
  uses the same policy as initial validation.
- Saved bilingual captions use model version `bilingual-v1-infant-care-v1` for
  traceability. Existing history/manual-edit protection is unchanged.

## Local validation

- 17 policy/prompt tests passed with the app startup package isolated.
- 15 selection/persistence tests passed against the actual caption-handler method,
  actual SQLAlchemy models, temporary SQLite and a synthetic provider. Heavy app
  module initialization was excluded using AST method extraction; network binds,
  connections and subprocess launches were forbidden. No tests were skipped.
- New cases cover explicit/default/malformed scope, bilingual baby-care terms,
  unchanged other checks, translation avoid lists, final replacement validation,
  stored policy version, history preservation, and rejection of client/task flags.

The normal full application test invocation is not available in this Mac checkout's
runtime environment. These are isolated source checks, not a full app, Windows,
deployed-model or photo-quality acceptance result.

## Deployment gate

No live files, services, environment, queued tasks or model runtime were changed.
The four failures have not been retried under the new policy. A separately approved
API/worker-only release cutover is required to load this implementation and its
private allowlist. Keep Qwen3 loaded and preserve the full continuation queue.
Coordinate stopping at a task boundary; inspect any running-task state rather than
blindly resetting it. After deployment, add four distinct, receipted retry tasks,
retain the original failures, and verify four saved bilingual results and history.
Do not deploy the separate mobile-security worktree as part of this change.
