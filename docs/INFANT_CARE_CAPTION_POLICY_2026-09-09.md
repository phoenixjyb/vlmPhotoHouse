# Owner-reviewed baby-care wording

Follow-up: the owner approved an API/worker-only cutover. Release `8832bf8` was
deployed successfully at 16:57:33 China time; see the deployment checkpoint below.
The earlier source-only validation and deployment prerequisites are retained here
as historical evidence, not the current deployment status.

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

## Deployment gate (pre-cutover snapshot)

No live files, services, environment, queued tasks or model runtime were changed.
The four failures have not been retried under the new policy. A separately approved
API/worker-only release cutover is required to load this implementation and its
private allowlist. Keep Qwen3 loaded and preserve the full continuation queue.
Coordinate stopping at a task boundary; inspect any running-task state rather than
blindly resetting it. After deployment, add four distinct, receipted retry tasks,
retain the original failures, and verify four saved bilingual results and history.
Do not deploy the separate mobile-security worktree as part of this change.

## Windows deployment checkpoint

- Source commit: `8832bf8f395f2356e1979c460708da08a9d28598`, on local branch
  `codex/infant-care-caption-policy`; not pushed to GitHub.
- Separate release: `photohouse-8832bf8-infant-care`, leaving the previous release
  available for rollback. The source archive SHA-256 was checked before extraction.
- Existing Windows app environment reused through a junction; no environment/model
  downloads, model copies or database migrations. Only the new release's private
  configuration contains the four approved asset IDs.
- All 17 policy tests and 15 handler/SQLite tests passed in the actual Windows
  environment with full app-module imports, synthetic data, a mocked provider and
  GPU disabled for the test process. This closes the earlier isolated-import test
  limitation, but is not full backend regression or image-quality acceptance.
- A fresh consistent database backup passed `quick_check` before queue deferral.
  20,809 unstarted continuation tasks were receipted and temporarily deferred.
  The active task completed; a SQLite write reservation guarded the exact old API
  process stop with zero running or due tasks. No task was force-reset.
- The existing SYSTEM-owned API task action was changed to the new release with
  migrations disabled. Its triggers, settings and principal were unchanged. The
  Qwen scheduled task and live Qwen process were unchanged.
- New API/database/worker health and InsightFace CUDA/LVFace configuration passed.
  The UI returned HTTP 200. No mobile-security worktree code was deployed.
- All 20,809 original schedules were restored. Four priority-50 retry tasks,
  `470095`–`470098`, were queued under `infant-care-retry-20260909`, while the
  original failed tasks were preserved as historical evidence.

Windows evidence remains in the release directory: `windows-tests.json`,
`before-cutover.sqlite`, `queue-hold.json`, `api-task-before.xml`,
`api-cutover-receipt.json`, `infant-retry-intent.json`,
`infant-retry-committed.json`, and `queue-resume.json`. Read receipts together with
live task state; do not replay cutover/queue operations from an intent file alone.

## Four-photo acceptance and resumed processing

At **17:00:25 China time**, retry tasks `470095`–`470098` all finished without
errors. New caption records `86169`–`86172` each had model
`qwen3-vl-http|bilingual-en-zh-cn`, policy version
`bilingual-v1-infant-care-v1`, and zero validation issues under the approved scoped
policy. This verifies the live configuration and saved outputs, not only startup.

The main continuation batch independently showed **131 finished, one running,
20,806 pending and eight failed**; it had advanced beyond the cutover boundary.
Those eight other failures predated this cutover and remain flagged for review.
All originally deferred pending schedules were restored; no hold remained.
The GPU sample was 63 C. The Qwen process remained the pre-cutover process.

The post-cutover database comparison found zero changes to existing caption text,
model labels or manual-edit flags, and zero changes to original path/hash identity.
The four original failed task records remain preserved, alongside their successful
retries. Old generated captions are superseded only through the normal successful
replacement transaction. Windows evidence: `four-retry-verification.json`.

The four-photo retry outcome is complete. The full-library caption backlog,
remaining failure review and visual factual-accuracy acceptance are not complete.
